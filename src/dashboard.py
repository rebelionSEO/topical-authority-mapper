"""Generate an interactive HTML dashboard from analysis outputs."""

import logging
import os
from typing import Optional

import pandas as pd

from src.config import SiteConfig, load_site_config, output_dir

logger = logging.getLogger(__name__)


# Thin-content categorization. Tiered by how actionable the page is — readers should
# fix HIGH-priority items first because they're real content the site is putting out.
# LOW-priority items are catch-all utility/lander pages that may not need text at all.
_BLOG_HINTS = ("/blog/", "/posts/", "/article/", "/articles/", "/news/", "/insights/",
               "/podcast-", "/whats-", "/why-", "/how-")
_SERVICE_HINTS = ("/services/", "/service/", "/solutions/", "/solution/",
                  "/products/", "/product/", "/platform/", "/features/", "/feature/")
_CASE_HINTS = ("/case-stud", "/customer-stories", "/customer-story", "/success-stories")
_GUIDE_HINTS = ("/guides/", "/guide/", "/library/", "/learn/", "/academy/", "/playbook")
_INDUSTRY_HINTS = ("/industries/", "/industry/", "/verticals/", "/for-")
_AUTHOR_HINTS = ("/author/", "/authors/", "/team/", "/people/", "/contributors/", "/staff/")
_TOOL_HINTS = ("/tools/", "/tool/", "tool-review", "/marketing-tools/", "/ai-tools/")
_LOCAL_HINTS = ("/locations/", "/cities/", "-near-me", "/areas/")
_LOCAL_PATH_HINTS = ("services-for-", "services-in-", "marketing-for-", "design-for-", "agency-in-")


# Order matters — first match wins. Each entry: (key, label, priority 1-5)
# Priority 1 = highest (fix first), 5 = lowest (probably don't need fixing).
_THIN_CATEGORIES = [
    ("blog",         "Blog / Article",        1),
    ("case-study",   "Case Study",            1),
    ("service",      "Service / Product Page", 2),
    ("industry",     "Industry / Vertical Page", 2),
    ("guide",        "Guide / Resource Hub",  3),
    ("author",       "Author / Team Page",    4),
    ("tool",         "Tool Review",           4),
    ("local",        "Local / Location",      4),
    ("other",        "Other (low priority)",  5),
]


def _classify_thin(url: str) -> str:
    """Classify a thin URL into a category for grouping. Returns the key from _THIN_CATEGORIES."""
    u = url.lower()
    if any(h in u for h in _BLOG_HINTS):
        return "blog"
    if any(h in u for h in _CASE_HINTS):
        return "case-study"
    if any(h in u for h in _SERVICE_HINTS):
        return "service"
    if any(h in u for h in _INDUSTRY_HINTS):
        return "industry"
    if any(h in u for h in _GUIDE_HINTS):
        return "guide"
    if any(h in u for h in _AUTHOR_HINTS):
        return "author"
    if any(h in u for h in _TOOL_HINTS):
        return "tool"
    if any(h in u for h in _LOCAL_HINTS) or any(h in u for h in _LOCAL_PATH_HINTS):
        return "local"
    return "other"


def _thin_recommendation(url: str, category: str) -> str:
    """Generate a short recommendation for a thin content page."""
    if category == "blog":
        return "Expand to 800+ words OR merge into a related pillar. Blog stubs hurt topical authority — they should be either substantial or gone."
    if category == "case-study":
        return "Add full case study: challenge, strategy, execution, results with metrics + customer quote."
    if category == "service":
        return "Service page must convert: features, benefits, social proof, pricing signal, FAQ, clear CTA. 600-1200 words minimum."
    if category == "industry":
        return "Build out as industry pillar: pain points specific to vertical, named case studies, vertical-specific services, FAQ."
    if category == "guide":
        return "Expand into a comprehensive resource hub with linked subtopics + downloadable asset."
    if category == "author":
        return "Expand: bio, credentials, articles authored, social links — supports E-E-A-T."
    if category == "tool":
        return "Expand to 500+ words: use cases, pricing, pros/cons, comparison to alternatives."
    if category == "local":
        return "Expand with local case studies, testimonials, service area details, unique location-specific content."
    return "Low priority — review whether this URL needs to be indexed at all. If yes, expand or consolidate; if no, noindex."


def _discover_competitor_csvs() -> list[tuple[str, pd.DataFrame]]:
    """Return list of (display_name, dataframe) for every competitor_gap_*.csv in OUTPUT_DIR."""
    results = []
    out = output_dir()
    if not os.path.isdir(out):
        return results
    for fname in sorted(os.listdir(out)):
        if fname.startswith("competitor_gap_") and fname.endswith(".csv"):
            stem = fname[len("competitor_gap_"):-len(".csv")]
            display_name = stem.replace("_", " ").title()
            df = pd.read_csv(os.path.join(out, fname))
            if not df.empty:
                results.append((display_name, df))
    return results


def generate_dashboard(site_config: SiteConfig | None = None):
    """Build a self-contained interactive HTML dashboard."""
    if site_config is None:
        site_config = load_site_config() or SiteConfig(name="Site", domain="")

    out = output_dir()
    clusters = pd.read_csv(os.path.join(out, "clusters.csv"))
    url_map = pd.read_csv(os.path.join(out, "url_mapping.csv"))
    cannib = pd.read_csv(os.path.join(out, "cannibalization.csv"))
    skipped = pd.read_csv(os.path.join(out, "skipped_urls.csv"))

    recs_path = os.path.join(out, "recommendations.csv")
    recs = pd.read_csv(recs_path) if os.path.exists(recs_path) else pd.DataFrame()

    def _load(name):
        p = os.path.join(out, name)
        return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()

    similarity_df = _load("similarity_scores.csv")
    if not similarity_df.empty:
        similarity_df = similarity_df[similarity_df["similarity"] >= 0.80].head(50)
    intent_df = _load("search_intent.csv")
    freshness_df = _load("content_freshness.csv")
    brand_df = _load("brand_voice_scores.csv")
    merge_df = _load("cluster_merge_suggestions.csv")
    if not merge_df.empty:
        merge_df = merge_df.head(30)

    # Discover competitors dynamically by reading any competitor_gap_*.csv files.
    competitor_dfs = _discover_competitor_csvs()
    competitor_names = [name for name, _ in competitor_dfs]

    # Content ideas (generated from competitor gaps)
    ideas_path = os.path.join(out, "content_ideas.csv")
    content_ideas_df = pd.read_csv(ideas_path) if os.path.exists(ideas_path) else pd.DataFrame()

    # Build a unified topic comparison table: rows = unique topics, cols = target + each competitor.
    competitor_table = []
    if competitor_dfs:
        # Collect topic → status map per competitor.
        topic_state: dict[str, dict] = {}
        for comp_name, df in competitor_dfs:
            for _, row in df.iterrows():
                topic = str(row.get("keyword", "")).strip()
                status = str(row.get("status", "")).lower()
                if not topic:
                    continue
                state = topic_state.setdefault(
                    topic,
                    {"topic": topic, "target": False, "competitors": {c: False for c in competitor_names}},
                )
                target_present = "advantage" in status or "shared" in status or "both cover" in status
                comp_present = "gap" in status or "shared" in status or "both cover" in status
                if target_present:
                    state["target"] = True
                if comp_present:
                    state["competitors"][comp_name] = True
        for state in topic_state.values():
            covered_by_comp = any(state["competitors"].values())
            if state["target"] and not covered_by_comp:
                final_status = "ADVANTAGE"
            elif covered_by_comp and not state["target"]:
                final_status = "GAP"
            else:
                final_status = "SHARED"
            state["status"] = final_status
            competitor_table.append(state)

    # Cluster sizes
    cluster_sizes = url_map[url_map["main_cluster"] != -1].groupby("main_cluster").size().reset_index(name="url_count")
    cluster_sizes = cluster_sizes.merge(clusters, left_on="main_cluster", right_on="cluster_id", how="inner")
    cluster_sizes = cluster_sizes.sort_values("url_count", ascending=False)

    top_clusters = cluster_sizes.head(30)
    noise_count = len(url_map[url_map["main_cluster"] == -1])

    cannib_full = cannib[cannib["cluster_id"] != -1].sort_values("url_count", ascending=False)

    content_types = {}
    if not recs.empty and "content_type" in recs.columns:
        content_types = recs["content_type"].value_counts().to_dict()

    from src.enhancements import is_intentionally_thin, classify_page_type
    thin = skipped[skipped["reason"].str.contains("thin", na=False)].copy()
    thin["is_listing"] = thin["url"].apply(is_intentionally_thin)
    thin["page_type"] = thin["url"].apply(classify_page_type)
    thin_actionable = thin[~thin["is_listing"]].copy()
    thin_listings = thin[thin["is_listing"]].copy()

    thin_actionable["category"] = thin_actionable["url"].apply(_classify_thin)
    thin_actionable["recommendation"] = thin_actionable.apply(
        lambda r: _thin_recommendation(r["url"], r["category"]), axis=1
    )
    thin_actionable["word_count"] = thin_actionable["reason"].str.extract(r"(\d+)").astype(float).fillna(0).astype(int)

    # LLM thin-content judgment — drops false positives the regex couldn't catch
    from src import llm_advisor as _llm
    if _llm.is_enabled() and not thin_actionable.empty:
        logger.info("LLM thin-content judgment on %d URLs...", len(thin_actionable))
        thin_urls = thin_actionable["url"].tolist()
        # Batch in chunks of 50
        verdicts: dict = {}
        chunk = 50
        for i in range(0, len(thin_urls), chunk):
            sub = thin_urls[i:i + chunk]
            res = _llm.advise_thin_content(
                site_name=site_config.name, site_domain=site_config.domain,
                industry=site_config.industry, urls=sub,
            )
            if res and isinstance(res, dict):
                for j in (res.get("judgments") or []):
                    u = j.get("url", "").strip()
                    if u:
                        verdicts[u] = {"verdict": j.get("verdict", "ambiguous"), "reason": j.get("reason", "")}
        # Apply verdicts: drop "exclude", annotate the rest
        keep_mask = thin_actionable["url"].apply(lambda u: verdicts.get(u, {}).get("verdict") != "exclude")
        excluded_n = int((~keep_mask).sum())
        if excluded_n:
            logger.info("LLM excluded %d thin URLs as false positives", excluded_n)
        thin_actionable = thin_actionable[keep_mask].copy()
        # Decorate the recommendation with LLM reasoning where available
        def _decorate(row):
            v = verdicts.get(row["url"], {})
            if v and v.get("reason"):
                return f"{row['recommendation']} (advisor: {v['reason']})"
            return row["recommendation"]
        thin_actionable["recommendation"] = thin_actionable.apply(_decorate, axis=1)

    # Group thin pages by category, ordered by priority (1 = fix first).
    cat_lookup = {key: (label, prio) for key, label, prio in _THIN_CATEGORIES}
    thin_groups = []
    for cat_key, label, prio in _THIN_CATEGORIES:
        rows = thin_actionable[thin_actionable["category"] == cat_key]
        if rows.empty:
            continue
        records = []
        for _, r in rows.iterrows():
            records.append({
                "url": r["url"],
                "slug": site_config.strip_url(r["url"]),
                "word_count": int(r["word_count"]),
                "recommendation": r["recommendation"],
            })
        thin_groups.append({
            "category": cat_key,
            "label": label,
            "priority": prio,
            "count": len(records),
            "pages": records,
        })

    # Backwards-compat slices (still used by some old templates / exec summary)
    thin_tools = thin_actionable[thin_actionable["category"] == "tool"].to_dict("records")
    thin_local = thin_actionable[thin_actionable["category"] == "local"].to_dict("records")
    thin_other = thin_actionable[~thin_actionable["category"].isin(["tool", "local"])].to_dict("records")

    # URL detail data
    url_details = url_map.merge(
        clusters.rename(columns={"cluster_id": "main_cluster", "cluster_name": "cluster_name_lookup"}),
        on="main_cluster", how="left"
    )

    treemap_data = {
        "labels": top_clusters["cluster_name"].tolist(),
        "values": top_clusters["url_count"].astype(int).tolist(),
        "ids": top_clusters["cluster_id"].astype(int).tolist(),
        "keywords": top_clusters["keywords"].tolist(),
    }

    cannib_chart = cannib_full.head(25)
    cannib_chart_data = {
        "labels": cannib_chart["cluster_name"].tolist(),
        "values": cannib_chart["url_count"].astype(int).tolist(),
    }

    # Per-URL intent lookup (for richer cannibalization detail)
    intent_by_url: dict = {}
    if not intent_df.empty:
        for _, row in intent_df.iterrows():
            intent_by_url[row["url"]] = {
                "primary": row.get("primary_intent", ""),
                "secondary": row.get("secondary_intent", ""),
                "confidence": row.get("confidence", ""),
            }

    # Per-URL chunk count → rough word-count proxy (each chunk is ~600 words)
    chunks_by_url: dict = {}
    try:
        import pickle as _pickle
        chunks_pkl = os.path.join(os.path.dirname(out), "cache", "chunks_df.pkl")
        if not os.path.exists(chunks_pkl):
            chunks_pkl = os.path.join(out, "../cache/chunks_df.pkl")
    except Exception:
        chunks_pkl = ""

    # Cannibalization detail — now with per-URL "winner" recommendation, intent, page type
    cannib_detail = []
    role_order = {"money": 0, "support": 1, "content": 2}

    def _pick_winner(urls_list: list) -> Optional[int]:
        """Choose the URL most likely to deserve the canonical/winner slot.
        Heuristic: service > case-study > industry > local-landing > blog. Within the same
        page type, prefer URLs whose intent best matches the cluster (commercial > info)."""
        if not urls_list:
            return None
        type_score = {"service": 100, "case-study": 80, "industry": 70,
                      "local-landing": 60, "tool-review": 50, "blog": 30,
                      "webinar": 20, "listing": 0, "homepage": 90}
        intent_bonus = {"transactional": 15, "commercial": 10, "informational": 0, "navigational": -5}
        best_idx, best_score = 0, -1
        for i, u in enumerate(urls_list):
            score = type_score.get(u["type"], 30)
            ib = intent_bonus.get(u.get("intent_primary", ""), 0)
            score += ib
            if score > best_score:
                best_score, best_idx = score, i
        return best_idx

    # LLM advisor — gives much sharper recommendations than the rule-based winner picker.
    # Falls back to rule-based when LLM is disabled.
    from src import llm_advisor
    llm_on = llm_advisor.is_enabled()
    if llm_on:
        logger.info("LLM cannibalization advisor enabled (%d clusters to analyze)", len(cannib_full))

    for cidx, (_, row) in enumerate(cannib_full.iterrows()):
        urls = [u.strip() for u in str(row["urls"]).split(" | ") if u.strip()]
        url_details_list = []
        for u in urls:
            ptype = classify_page_type(u)
            ip = intent_by_url.get(u, {}).get("primary", "")
            url_details_list.append({
                "url": u,
                "slug": site_config.strip_url(u),
                "type": ptype,
                "intent_primary": ip,
                "intent_secondary": intent_by_url.get(u, {}).get("secondary", ""),
                "role": "money" if ptype == "service" else "support" if ptype in ("case-study", "industry", "local-landing") else "content",
            })

        kw_row = clusters[clusters["cluster_id"] == row["cluster_id"]]
        keywords_list = (kw_row.iloc[0]["keywords"].split(", ") if len(kw_row) > 0 else [])

        # Try LLM advisor first
        llm_verdict = None
        if llm_on:
            try:
                llm_verdict = llm_advisor.advise_cannibalization(
                    cluster_name=str(row["cluster_name"]),
                    keywords=keywords_list,
                    urls=url_details_list,
                )
                if llm_verdict:
                    logger.info("  [%d/%d] LLM verdict on '%s': %s",
                                cidx + 1, len(cannib_full), row["cluster_name"],
                                "REAL cannibalization" if llm_verdict.get("is_cannibalization") else "FALSE POSITIVE")
            except Exception:
                logger.exception("LLM cannibalization analysis failed; falling back to rules")
                llm_verdict = None

        winner_slug = None
        if llm_verdict and isinstance(llm_verdict, dict):
            # Apply LLM judgments to per-URL details
            per_url_lookup = {}
            for entry in (llm_verdict.get("per_url") or []):
                key = entry.get("url", "").strip()
                if key:
                    per_url_lookup[key] = entry
                    # Match either by full URL or by slug
                    per_url_lookup[site_config.strip_url(key) if key.startswith("http") else key] = entry
            # Apply
            for u in url_details_list:
                v = per_url_lookup.get(u["slug"]) or per_url_lookup.get(u["url"])
                if v:
                    u["recommendation"] = v.get("verdict", "MERGE")
                    u["action"] = v.get("action") or "Consolidate per LLM advisor"
                else:
                    u["recommendation"] = "MERGE"
                    u["action"] = "Consolidate (no per-URL verdict from advisor)"
            winner_slug = llm_verdict.get("winner_url")
        else:
            # Rule-based fallback
            winner_idx = _pick_winner(url_details_list)
            winner_slug = url_details_list[winner_idx]["slug"] if winner_idx is not None else None
            for i, u in enumerate(url_details_list):
                if i == winner_idx:
                    u["recommendation"] = "WINNER"
                    u["action"] = f"KEEP — strongest candidate (page type: {u['type']}, intent: {u['intent_primary'] or 'n/a'}). Consolidate the others into this URL."
                else:
                    winner_intent = url_details_list[winner_idx]["intent_primary"] if winner_idx is not None else ""
                    same_intent = u["intent_primary"] == winner_intent if winner_intent else True
                    if u["type"] == "service" and url_details_list[winner_idx]["type"] == "service":
                        u["recommendation"] = "REVIEW"
                        u["action"] = "REVIEW — two service pages on the same topic. Pick the one with stronger rankings; consolidate the other."
                    elif same_intent:
                        u["recommendation"] = "MERGE"
                        u["action"] = f"MERGE INTO winner via 301 → {winner_slug}"
                    else:
                        u["recommendation"] = "DIFFERENTIATE"
                        u["action"] = f"DIFFERENTIATE — different intent ({u['intent_primary'] or 'n/a'}) than winner. Re-target with unique angle, or merge."

        # Sort: winner first, then non-exclude, then exclude (false-positives last)
        rec_order = {"WINNER": 0, "REVIEW": 1, "DIFFERENTIATE": 2, "MERGE": 3, "EXCLUDE": 9}
        url_details_list.sort(key=lambda x: rec_order.get(x.get("recommendation", "MERGE"), 3))

        types_present = set(d["type"] for d in url_details_list)
        has_conversion_risk = "service" in types_present and "blog" in types_present

        # Use LLM verdict_summary if available, otherwise build a heuristic analysis
        is_real_cannib = True
        if llm_verdict and isinstance(llm_verdict, dict):
            is_real_cannib = bool(llm_verdict.get("is_cannibalization", True))
            analysis = llm_verdict.get("verdict_summary") or "Cluster analyzed by SEO advisor."
            if not is_real_cannib:
                analysis = "FALSE POSITIVE per advisor — " + analysis
        elif has_conversion_risk:
            blog_count = sum(1 for d in url_details_list if d['type'] == 'blog')
            analysis = (
                f"CONVERSION RISK: {blog_count} blog posts competing against the service page. "
                "The blog(s) may outrank the service page, pushing users away from conversion."
            )
        elif len(urls) > 10:
            analysis = (
                f"SEVERE TOPIC FRAGMENTATION: {len(urls)} pages on the same topic dilutes authority. "
                "Consolidate into 1 pillar + 2-3 angle-specific spokes."
            )
        else:
            analysis = (
                f"{len(urls)} pages overlap on this topic. Winner identified below — merge the rest "
                "into it via 301 redirects."
            )

        keywords = kw_row.iloc[0]["keywords"] if len(kw_row) > 0 else ""

        # Severity now considers LLM verdict — false positives are downgraded
        if not is_real_cannib:
            severity = "false-positive"
        elif row["url_count"] >= 10 or has_conversion_risk:
            severity = "critical"
        elif row["url_count"] >= 6:
            severity = "high"
        else:
            severity = "moderate"

        cannib_detail.append({
            "id": int(row["cluster_id"]),
            "name": row["cluster_name"],
            "count": int(row["url_count"]),
            "urls": url_details_list,
            "keywords": keywords.split(", ")[:6],
            "winner_slug": winner_slug or "",
            "analysis": analysis,
            "has_conversion_risk": has_conversion_risk,
            "is_real_cannibalization": is_real_cannib,
            "advisor_reasoning": (llm_verdict.get("winner_reasoning") if llm_verdict else "") or "",
            "severity": severity,
        })

    all_clusters_data = []
    for _, row in cluster_sizes.iterrows():
        rec_row = recs[recs["cluster_id"] == row["cluster_id"]] if not recs.empty else pd.DataFrame()
        all_clusters_data.append({
            "id": int(row["cluster_id"]),
            "name": row["cluster_name"],
            "urls": int(row["url_count"]),
            "keywords": row["keywords"],
            "content_type": rec_row.iloc[0]["content_type"] if len(rec_row) > 0 else "",
            "tone": rec_row.iloc[0]["tone"] if len(rec_row) > 0 else "",
            "angle": rec_row.iloc[0]["angle"] if len(rec_row) > 0 else "",
            "cta": rec_row.iloc[0]["cta_style"] if len(rec_row) > 0 else "",
            "cannibalized": int(row["cluster_id"]) in cannib["cluster_id"].values,
        })

    url_table = []
    for _, row in url_details.iterrows():
        url_table.append({
            "url": row["url"],
            "cluster": int(row["main_cluster"]) if pd.notna(row["main_cluster"]) else -1,
            "name": row.get("cluster_name_lookup", row.get("cluster_name", "Unclustered")),
            "secondary": row.get("secondary_clusters", ""),
        })

    stats = {
        "total_urls": len(url_map),
        "total_clusters": len(clusters),
        "cannib_flags": len(cannib_full),
        "skipped": len(thin_actionable),
        "skipped_listings": len(thin_listings),
        "noise": noise_count,
        "thin_local": len(thin_local),
        "thin_tools": len(thin_tools),
        "thin_other": len(thin_other),
    }

    top_cannib_summary = cannib_full.head(5)[["cluster_name", "url_count"]].to_dict("records")

    enh = {}
    if competitor_table:
        gaps = sum(1 for r in competitor_table if r["status"] == "GAP")
        advantages = sum(1 for r in competitor_table if r["status"] == "ADVANTAGE")
        shared = sum(1 for r in competitor_table if r["status"] == "SHARED")
        enh["competitor"] = {
            "rows": competitor_table,
            "names": competitor_names,
        }
        enh["comp_stats"] = {"gaps": gaps, "advantages": advantages, "shared": shared}
    if not similarity_df.empty:
        sim_records = similarity_df.to_dict("records")
        for r in sim_records:
            r["url_a"] = site_config.strip_url(r["url_a"])
            r["url_b"] = site_config.strip_url(r["url_b"])
        enh["similarity"] = sim_records
    if not intent_df.empty:
        enh["intent"] = intent_df["primary_intent"].value_counts().to_dict()
    if not freshness_df.empty:
        enh["freshness"] = freshness_df["freshness"].value_counts().to_dict()
    if not brand_df.empty:
        bottom_records = brand_df.head(20).to_dict("records")
        for r in bottom_records:
            r["url"] = site_config.strip_url(r["url"])
        enh["brand"] = {
            "distribution": brand_df["rating"].value_counts().to_dict(),
            "avg_score": round(brand_df["brand_score"].mean(), 1),
            "bottom": bottom_records,
        }
    if not merge_df.empty:
        enh["merges"] = merge_df.to_dict("records")
    if not content_ideas_df.empty:
        ideas_records = content_ideas_df.to_dict("records")
        # Split pipe-delimited fields back into arrays for nicer rendering
        for r in ideas_records:
            r["suggested_keywords"] = [k.strip() for k in str(r.get("suggested_keywords", "")).split("|") if k.strip()]
            r["key_questions"] = [q.strip() for q in str(r.get("key_questions", "")).split("|") if q.strip()]
        enh["content_ideas"] = ideas_records
        enh["content_ideas_stats"] = {
            "total": len(content_ideas_df),
            "p1": int((content_ideas_df["priority"] == "P1").sum()),
            "p2": int((content_ideas_df["priority"] == "P2").sum()),
            "p3": int((content_ideas_df["priority"] == "P3").sum()),
        }

    # Load (or compute) health snapshot for the hero
    health_data: dict = {}
    health_path = os.path.join(out, "site_health.json")
    if os.path.exists(health_path):
        try:
            import json as _json
            with open(health_path) as _f:
                health_data = _json.load(_f)
        except Exception:
            health_data = {}
    if not health_data:
        try:
            from src.site_health import compute_health
            snap = compute_health(site_config=site_config)
            health_data = snap.to_dict()
        except Exception:
            logger.exception("Could not compute site health for dashboard")

    # Spoke cluster lookup for the URL Explorer (rename "Secondary" → "Spoke cluster")
    cluster_name_by_id = {int(r["cluster_id"]): r["cluster_name"] for _, r in clusters.iterrows()}
    for u in url_table:
        sec = str(u.get("secondary", "")).strip()
        # secondary may be a comma-separated list of cluster IDs; pick the first as the spoke
        if sec and sec.lower() != "nan":
            try:
                sec_id = int(float(sec.split(",")[0]))
                u["spoke_cluster"] = cluster_name_by_id.get(sec_id, "")
                u["spoke_id"] = sec_id
            except (ValueError, IndexError):
                u["spoke_cluster"] = ""
                u["spoke_id"] = ""
        else:
            u["spoke_cluster"] = ""
            u["spoke_id"] = ""

    from src.dashboard_html import build_html
    html = build_html(
        site_config=site_config,
        treemap_data=treemap_data,
        cannib_chart_data=cannib_chart_data,
        cannib_detail=cannib_detail,
        content_types=content_types,
        all_clusters=all_clusters_data,
        url_table=url_table,
        stats=stats,
        thin_tools=thin_tools,
        thin_local=thin_local,
        thin_other=thin_other,
        thin_groups=thin_groups,
        top_cannib_summary=top_cannib_summary,
        enhancements=enh,
        health=health_data,
    )

    out_path = os.path.join(out, "dashboard.html")
    with open(out_path, "w") as f:
        f.write(html)
    logger.info("Dashboard saved to %s", out_path)
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = generate_dashboard()
    print(f"Dashboard: {path}")
