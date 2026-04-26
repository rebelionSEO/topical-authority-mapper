"""Pre-render QA pass on the pipeline outputs.

Runs after the analysis is complete and before dashboard/PDF render. Catches:

  - Empty / null required fields
  - Out-of-range numbers (similarity > 1, percentages > 100, negative counts)
  - Totals that don't reconcile (sum of categories != total)
  - Cluster/competitor names that are pure stopword noise or sentence fragments
  - Stale files left over from a previous run (older than the run start)
  - Missing files that downstream renderers expect
  - Suspicious content-idea topics (gibberish / single chars / pure stopwords)

Writes output/qa_report.json with severity-grouped findings and prints a one-screen
summary. By default, CRITICAL findings cause render to abort (dashboard.py / report.py
will skip rendering); WARN findings are printed but non-blocking.

CLI:
    python -m src.qa          # run QA standalone, print report
    python -m src.qa --strict # exit non-zero if any WARN+ found
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

import pandas as pd

from src.config import cache_dir, output_dir

logger = logging.getLogger(__name__)


# Words that are suspicious if they appear ALONE in a cluster name or topic
_STOPWORDS = {
    "the", "a", "an", "of", "for", "with", "and", "or", "to", "in", "on", "at",
    "by", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "should", "could",
    "this", "that", "these", "those", "it", "its", "their", "your", "our",
    "more", "most", "some", "any", "all", "use", "used", "using", "page", "post",
}


@dataclass
class Finding:
    severity: str  # "CRITICAL" | "WARN" | "INFO"
    check: str
    message: str
    file: Optional[str] = None
    sample: Optional[list] = None


@dataclass
class QAReport:
    started_at: float = field(default_factory=time.time)
    checks_run: int = 0
    findings: list = field(default_factory=list)

    def add(self, severity: str, check: str, message: str, file: Optional[str] = None, sample: Optional[list] = None) -> None:
        self.findings.append(Finding(severity=severity, check=check, message=message, file=file, sample=sample))

    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "CRITICAL")

    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "WARN")

    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "INFO")

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "checks_run": self.checks_run,
            "summary": {
                "critical": self.critical_count(),
                "warn": self.warn_count(),
                "info": self.info_count(),
            },
            "findings": [asdict(f) for f in self.findings],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _exists(path: str) -> bool:
    return os.path.exists(path)


def _read_csv(path: str) -> Optional[pd.DataFrame]:
    if not _exists(path):
        return None
    try:
        return pd.read_csv(path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return None


def _is_garbage_string(s: str, min_len: int = 4) -> bool:
    """Return True if a topic/cluster name looks like noise."""
    if not isinstance(s, str):
        return True
    s = s.strip()
    if len(s) < min_len:
        return True
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9']+", s)]
    if not words:
        return True
    # All stopwords / short tokens
    if all(w in _STOPWORDS or len(w) <= 2 for w in words):
        return True
    return False


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_required_files(report: QAReport, out_dir: str) -> None:
    """Core CSVs that downstream renderers need."""
    report.checks_run += 1
    required = ["clusters.csv", "url_mapping.csv", "cannibalization.csv", "skipped_urls.csv"]
    missing = [f for f in required if not _exists(os.path.join(out_dir, f))]
    if missing:
        report.add("CRITICAL", "required_files", f"Missing required output files: {', '.join(missing)}")


def check_clusters(report: QAReport, out_dir: str) -> None:
    """Cluster names should be real phrases, not noise."""
    report.checks_run += 1
    df = _read_csv(os.path.join(out_dir, "clusters.csv"))
    if df is None or df.empty:
        report.add("WARN", "clusters", "clusters.csv is empty — no topics were formed")
        return

    if df["cluster_id"].duplicated().any():
        dupes = df[df["cluster_id"].duplicated()]["cluster_id"].tolist()
        report.add("CRITICAL", "clusters.duplicates", f"Duplicate cluster_id rows: {dupes}", file="clusters.csv")

    bad_names = []
    for _, row in df.iterrows():
        name = str(row.get("cluster_name", ""))
        if _is_garbage_string(name):
            bad_names.append({"cluster_id": int(row["cluster_id"]), "name": name})

    if bad_names:
        pct = len(bad_names) / len(df) * 100
        sev = "CRITICAL" if pct >= 30 else "WARN"
        report.add(
            sev, "clusters.noisy_names",
            f"{len(bad_names)} of {len(df)} cluster names ({pct:.0f}%) look like noise (stopword-only / too short)",
            file="clusters.csv", sample=bad_names[:5],
        )


def check_cannibalization(report: QAReport, out_dir: str) -> None:
    report.checks_run += 1
    df = _read_csv(os.path.join(out_dir, "cannibalization.csv"))
    if df is None:
        return
    if df.empty:
        return

    # url_count must match the number of pipe-delimited URLs
    mismatched = []
    for _, row in df.iterrows():
        urls = str(row.get("urls", "")).split(" | ") if row.get("urls") else []
        actual = len([u for u in urls if u.strip()])
        declared = int(row.get("url_count", 0))
        if actual != declared:
            mismatched.append({"cluster_id": int(row["cluster_id"]), "declared": declared, "actual": actual})
    if mismatched:
        report.add(
            "WARN", "cannibalization.url_count_mismatch",
            f"{len(mismatched)} clusters where url_count doesn't match the URL list length",
            file="cannibalization.csv", sample=mismatched[:5],
        )


def check_skipped_totals(report: QAReport, out_dir: str) -> None:
    """No silent NaN counts in the skipped URLs CSV."""
    report.checks_run += 1
    df = _read_csv(os.path.join(out_dir, "skipped_urls.csv"))
    if df is None:
        return
    if df.empty:
        return
    if "url" in df.columns:
        empty_urls = df["url"].isna().sum()
        if empty_urls > 0:
            report.add("WARN", "skipped.empty_urls", f"{empty_urls} skipped rows have no URL", file="skipped_urls.csv")


def check_similarity(report: QAReport, out_dir: str) -> None:
    report.checks_run += 1
    df = _read_csv(os.path.join(out_dir, "similarity_scores.csv"))
    if df is None or df.empty:
        return
    out_of_range = df[(df["similarity"] < 0) | (df["similarity"] > 1)]
    if not out_of_range.empty:
        report.add(
            "CRITICAL", "similarity.out_of_range",
            f"{len(out_of_range)} similarity scores outside [0, 1]",
            file="similarity_scores.csv", sample=out_of_range.head(3).to_dict("records"),
        )
    self_pairs = df[df["url_a"] == df["url_b"]]
    if not self_pairs.empty:
        report.add(
            "WARN", "similarity.self_pairs",
            f"{len(self_pairs)} similarity rows compare a URL to itself",
            file="similarity_scores.csv",
        )


def check_brand_voice(report: QAReport, out_dir: str) -> None:
    report.checks_run += 1
    df = _read_csv(os.path.join(out_dir, "brand_voice_scores.csv"))
    if df is None or df.empty:
        return
    out_of_range = df[(df["brand_score"] < 0) | (df["brand_score"] > 100)]
    if not out_of_range.empty:
        report.add(
            "CRITICAL", "brand_voice.out_of_range",
            f"{len(out_of_range)} brand_score values outside [0, 100]",
            file="brand_voice_scores.csv", sample=out_of_range.head(3).to_dict("records"),
        )


def check_competitor_gaps(report: QAReport, out_dir: str) -> None:
    """Each competitor_gap_*.csv must have valid status enum + non-garbage topics."""
    report.checks_run += 1
    if not os.path.isdir(out_dir):
        return
    valid_status_keywords = ("GAP", "ADVANTAGE", "SHARED", "COVER")
    for fname in sorted(os.listdir(out_dir)):
        if not (fname.startswith("competitor_gap_") and fname.endswith(".csv")):
            continue
        path = os.path.join(out_dir, fname)
        df = _read_csv(path)
        if df is None or df.empty:
            report.add("WARN", "competitor_gaps.empty", f"{fname} is empty", file=fname)
            continue
        if not {"keyword", "status"}.issubset(df.columns):
            report.add("CRITICAL", "competitor_gaps.schema", f"{fname} missing required columns (keyword, status)", file=fname)
            continue
        bad_status = df[~df["status"].str.upper().str.contains("|".join(valid_status_keywords), na=False)]
        if not bad_status.empty:
            report.add(
                "WARN", "competitor_gaps.bad_status",
                f"{fname} has {len(bad_status)} rows with unexpected status values",
                file=fname, sample=bad_status.head(3).to_dict("records"),
            )
        garbage = []
        for _, row in df.iterrows():
            kw = str(row.get("keyword", ""))
            if _is_garbage_string(kw, min_len=3):
                garbage.append(kw)
        if garbage:
            pct = len(garbage) / len(df) * 100
            sev = "WARN" if pct < 25 else "CRITICAL"
            report.add(
                sev, "competitor_gaps.noisy_topics",
                f"{fname}: {len(garbage)} topics ({pct:.0f}%) look like noise",
                file=fname, sample=garbage[:5],
            )


def check_content_ideas(report: QAReport, out_dir: str) -> None:
    report.checks_run += 1
    path = os.path.join(out_dir, "content_ideas.csv")
    df = _read_csv(path)
    if df is None or df.empty:
        return

    required = ["priority", "title", "gap_topic", "content_type", "intent", "target_audience",
                "suggested_keywords", "key_questions", "est_word_count", "covered_by", "num_competitors"]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        report.add(
            "CRITICAL", "content_ideas.schema",
            f"content_ideas.csv missing columns: {missing_cols}", file="content_ideas.csv",
        )
        return

    valid_priority = {"P1", "P2", "P3"}
    bad_priority = df[~df["priority"].isin(valid_priority)]
    if not bad_priority.empty:
        report.add("CRITICAL", "content_ideas.priority", f"{len(bad_priority)} rows with invalid priority", file="content_ideas.csv")

    out_of_range_words = df[(df["est_word_count"] < 200) | (df["est_word_count"] > 10000)]
    if not out_of_range_words.empty:
        report.add(
            "WARN", "content_ideas.word_count_out_of_range",
            f"{len(out_of_range_words)} ideas with implausible word count (<200 or >10000)",
            file="content_ideas.csv", sample=out_of_range_words.head(3)[["title", "est_word_count"]].to_dict("records"),
        )

    # Empty required-text fields
    text_cols = ["title", "gap_topic", "suggested_keywords", "key_questions", "covered_by"]
    for col in text_cols:
        empties = df[df[col].isna() | (df[col].astype(str).str.strip() == "")]
        if not empties.empty:
            report.add("CRITICAL", f"content_ideas.{col}_empty", f"{len(empties)} rows with empty {col}", file="content_ideas.csv")

    # num_competitors must match covered_by count
    mismatched = []
    for _, row in df.iterrows():
        covered = [c.strip() for c in str(row.get("covered_by", "")).split(",") if c.strip()]
        declared = int(row.get("num_competitors", 0))
        if len(covered) != declared:
            mismatched.append({"title": row["title"], "declared": declared, "actual": len(covered)})
    if mismatched:
        report.add(
            "WARN", "content_ideas.num_competitors_mismatch",
            f"{len(mismatched)} ideas where num_competitors doesn't match covered_by count",
            file="content_ideas.csv", sample=mismatched[:3],
        )

    # Garbage topics (the rule-based generator can't fix garbage input)
    garbage = []
    for _, row in df.iterrows():
        if _is_garbage_string(row["gap_topic"], min_len=4):
            garbage.append({"title": row["title"], "gap_topic": row["gap_topic"]})
    if garbage:
        sev = "WARN" if len(garbage) <= 3 else "CRITICAL"
        report.add(
            sev, "content_ideas.noisy_topics",
            f"{len(garbage)} content ideas built on noisy gap topics — review or drop before publishing",
            file="content_ideas.csv", sample=garbage[:5],
        )


def check_freshness(report: QAReport, out_dir: str, run_started_at: float) -> None:
    """Catch stale files left over from a previous run."""
    report.checks_run += 1
    if not os.path.isdir(out_dir):
        return
    stale = []
    for fname in os.listdir(out_dir):
        # Only check generated CSVs / HTML / PDF
        if not fname.endswith((".csv", ".html", ".pdf", ".json")):
            continue
        path = os.path.join(out_dir, fname)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime + 60 < run_started_at:  # 60s grace for clock skew
            stale.append({"file": fname, "age_seconds": round(run_started_at - mtime)})
    if stale:
        report.add(
            "WARN", "freshness.stale_files",
            f"{len(stale)} output files predate this run — likely leftover from a previous site",
            sample=stale[:5],
        )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def run_qa(run_started_at: Optional[float] = None) -> QAReport:
    """Run all QA checks against the current output dir. Returns the report."""
    out = output_dir()
    started = run_started_at if run_started_at is not None else time.time() - 1
    report = QAReport(started_at=started)

    check_required_files(report, out)
    check_clusters(report, out)
    check_cannibalization(report, out)
    check_skipped_totals(report, out)
    check_similarity(report, out)
    check_brand_voice(report, out)
    check_competitor_gaps(report, out)
    check_content_ideas(report, out)
    check_freshness(report, out, started)

    # Persist
    out_path = os.path.join(out, "qa_report.json")
    try:
        with open(out_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
        logger.info("Wrote QA report -> %s", out_path)
    except OSError as e:
        logger.warning("Could not write QA report: %s", e)

    return report


def print_summary(report: QAReport) -> None:
    """One-screen summary printed to stdout."""
    print()
    print("=" * 60)
    print(f"QA REPORT — {report.checks_run} checks run")
    print("=" * 60)
    print(f"  CRITICAL: {report.critical_count()}")
    print(f"  WARN:     {report.warn_count()}")
    print(f"  INFO:     {report.info_count()}")
    print()

    if not report.findings:
        print("  All checks passed. Safe to render.")
        print("=" * 60)
        return

    by_sev = {"CRITICAL": [], "WARN": [], "INFO": []}
    for f in report.findings:
        by_sev.setdefault(f.severity, []).append(f)

    for sev in ("CRITICAL", "WARN", "INFO"):
        for f in by_sev.get(sev, []):
            tag = f"[{sev}]"
            loc = f" ({f.file})" if f.file else ""
            print(f"  {tag} {f.check}{loc}")
            print(f"        {f.message}")
            if f.sample:
                preview = ", ".join(str(s) for s in f.sample[:3])
                if len(preview) > 200:
                    preview = preview[:197] + "..."
                print(f"        e.g.: {preview}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Run QA validation on pipeline outputs.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any WARN+ findings.")
    parser.add_argument("--quiet", action="store_true", help="Skip console summary.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    report = run_qa()
    if not args.quiet:
        print_summary(report)
    if args.strict and (report.critical_count() or report.warn_count()):
        sys.exit(1)
    if report.critical_count():
        sys.exit(2)


if __name__ == "__main__":
    main()
