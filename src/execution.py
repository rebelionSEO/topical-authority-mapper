"""Isolated audit directories and durable, machine-readable execution status."""

import functools
import hashlib
import inspect
import json
import os
import re
import shutil
import tempfile
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.config import OUTPUT_DIR, cache_root, set_runtime_cache_dir

_current = ContextVar("audit_manifest", default=None)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as f:
        temp = f.name
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    try:
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class Manifest:
    def __init__(self, out, run_id, domain, parameters):
        self.out = Path(out)
        from src import config
        source = Path(__file__).parent
        digest = hashlib.sha256()
        for path in sorted(source.rglob("*.py")):
            digest.update(str(path.relative_to(source)).encode())
            digest.update(path.read_bytes())
        self.data = {"schema_version": 1, "run_id": run_id, "domain": domain,
                     "started_at": timestamp(), "finished_at": None, "status": "running",
                     "parameters": parameters, "stages": {}, "artifacts": [], "coverage": {}}
        self.data["analysis_config"] = {"embedding_model": config.EMBEDDING_MODEL,
            "chunk_size_words": config.CHUNK_SIZE_WORDS, "max_chars_per_page": config.MAX_CHARS_PER_PAGE,
            "min_words_threshold": config.MIN_WORDS_THRESHOLD,
            "min_cluster_size": config.HDBSCAN_MIN_CLUSTER_SIZE, "source_sha256": digest.hexdigest()}
        for name in ("ingestion", "embeddings", "clustering", "freshness", "intent", "similarity",
                     "cluster_merges", "brand_voice", "competitors", "content_ideas", "qa",
                     "health", "executive_summary", "dashboard", "pdf", "snapshot"):
            self.data["stages"][name] = {"status": "pending"}
        self.save()

    def _render_status(self):
        import html
        rows = "".join(f"<tr><td>{html.escape(name)}</td><td>{html.escape(record['status'])}</td>"
                       f"<td>{html.escape(str(record.get('error') or record.get('reason') or ''))}</td></tr>"
                       for name, record in self.data["stages"].items())
        details = html.escape(json.dumps(self.data["coverage"], indent=2))
        configuration = html.escape(json.dumps({"parameters": self.data["parameters"],
                                                "analysis": self.data["analysis_config"]}, indent=2, default=str))
        page = ("<!doctype html><meta charset='utf-8'><title>Audit execution</title>"
                "<style>body{font:16px system-ui;max-width:1000px;margin:40px auto;padding:20px}"
                "td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}pre{white-space:pre-wrap}</style>"
                f"<h1>Audit: {html.escape(self.data['domain'])}</h1><p>Status: {self.data['status']}</p>"
                f"<p>Run: {self.data['run_id']} · Started: {self.data['started_at']}</p>"
                f"<h2>Coverage</h2><pre>{details}</pre><h2>Analyses</h2>"
                f"<details><summary>Configuration</summary><pre>{configuration}</pre></details>"
                f"<table><tr><th>Analysis</th><th>Status</th><th>Details</th></tr>{rows}</table>"
                "<p><a href='run_manifest.json'>Full execution record</a> · <a href='dashboard.html'>Dashboard</a></p>")
        (self.out / "run_status.html").write_text(page, encoding="utf-8")

    def save(self):
        write_json(self.out / "run_manifest.json", self.data)
        self._render_status()

    def finish(self, error=None):
        for record in self.data["stages"].values():
            if record["status"] == "pending":
                record.update(status="skipped", reason="Not reached or not requested")
        stages = self.data["stages"].values()
        degraded = any(s["status"] in ("failed", "unavailable", "partial") for s in stages)
        self.data.update(finished_at=timestamp(), status="failed" if error else "partial" if degraded else "completed")
        if error:
            self.data["error"] = f"{type(error).__name__}: {error}"
        self._render_status()
        self.data["artifacts"] = [
            {"path": p.name, "size_bytes": p.stat().st_size,
             "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(self.out.iterdir()) if p.is_file() and p.name != "run_manifest.json"
        ]
        self.save()


def stage(name, operation, *args, **kwargs):
    manifest = _current.get()
    if manifest is None:
        return operation(*args, **kwargs)
    record = {"status": "running", "started_at": timestamp()}
    manifest.data["stages"][name] = record
    manifest.save()
    try:
        result = operation(*args, **kwargs)
        record["status"] = "completed"
        if hasattr(result, "empty"):
            record.update(rows=len(result), status="unavailable" if result.empty and name in ("freshness", "brand_voice", "cluster_keywords") else "completed")
        if name == "pdf" and (not result or not str(result).endswith(".pdf")):
            record.update(status="unavailable", reason="PDF renderer unavailable; HTML report retained")
        return result
    except BaseException as exc:
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        record["finished_at"] = timestamp()
        manifest.save()


def note_stage(name, status, **details):
    manifest = _current.get()
    if manifest:
        manifest.data["stages"][name] = {"status": status, **details}
        manifest.save()


def coverage(**values):
    manifest = _current.get()
    if manifest:
        manifest.data["coverage"].update(values)
        manifest.save()


def isolated_audit(operation):
    """Every invocation gets new output/cache paths; only validated caches are reused."""
    signature = inspect.signature(operation)

    @functools.wraps(operation)
    def wrapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        params = bound.arguments
        from urllib.parse import urlsplit
        from collections import Counter
        source = params.get("sitemap_url") or ""
        if not source and params.get("input_file") and Path(params["input_file"]).is_file():
            with open(params["input_file"]) as f:
                hosts = Counter(urlsplit(line.strip()).netloc for line in f if line.strip() and not line.startswith("#"))
            source = "https://" + hosts.most_common(1)[0][0] if hosts else ""
        domain = params.get("site_domain") or urlsplit(source).netloc or "unknown"
        domain = domain.lower().strip().removeprefix("https://").removeprefix("http://").rstrip("/")
        slug = re.sub(r"[^a-z0-9]+", "_", domain).strip("_")[:70] or "site"
        slug += "_" + hashlib.sha256(domain.encode()).hexdigest()[:8]
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:12]
        root = Path(cache_root()).absolute()
        base = Path(params.get("output_dir_arg") or OUTPUT_DIR).absolute()
        out = base / "audits" / slug / run_id
        cache = root / "audits" / slug / run_id
        shared = root / "shared" / slug
        out.mkdir(parents=True)
        cache.mkdir(parents=True)
        from src.config import SiteConfig, save_site_config
        save_site_config(SiteConfig(name=params.get("site_name") or domain, domain=domain,
                                   output_dir=str(out)), cache_dir_path=str(cache))
        for name in ("embeddings.pkl.npz", "brand_profile.json"):
            if (shared / name).is_file() and not (params.get("debug") and name == "embeddings.pkl.npz"):
                shutil.copy2(shared / name, cache / name)
        manifest = Manifest(out, run_id, domain, dict(params))
        token = _current.set(manifest)
        set_runtime_cache_dir(str(cache))
        # Standalone report/retrieval commands resolve this audit, including failures.
        write_json(root / "active_run.json", {"run_id": run_id, "cache_dir": str(cache), "output_dir": str(out)})
        params["output_dir_arg"] = str(out)
        result = None
        try:
            result = operation(**params)
        except BaseException as exc:
            manifest.finish(exc)
            raise
        else:
            manifest.finish()
            print(f"Audit status: {manifest.data['status']} — {out / 'run_status.html'}")
            shared.mkdir(parents=True, exist_ok=True)
            for name in ("embeddings.pkl.npz", "brand_profile.json"):
                if (cache / name).is_file():
                    with tempfile.NamedTemporaryFile(dir=shared, delete=False) as f:
                        temp = Path(f.name)
                    shutil.copyfile(cache / name, temp)
                    os.replace(temp, shared / name)
            if result and result.get("snapshot_path"):
                shutil.copy2(out / "run_manifest.json", Path(result["snapshot_path"]) / "output" / "run_manifest.json")
                shutil.copy2(out / "run_status.html", Path(result["snapshot_path"]) / "output" / "run_status.html")
            return {"run_id": run_id, "output_dir": str(out), "cache_dir": str(cache),
                    "status": manifest.data["status"], **(result or {})}
        finally:
            _current.reset(token)
            set_runtime_cache_dir(str(root))

    return wrapped
