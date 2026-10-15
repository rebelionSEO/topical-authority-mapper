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


# ---------------------------------------------------------------------------
# Visual payloads (Cluster Map, Overlap, Gaps, Actions)
#
# Every number below is read from a pipeline CSV; nothing is estimated. Each
# clickable item carries a "panel" (what's wrong / why it matters / suggested
# action + the CSV it came from) that the dashboard renders in its side panel.
# ---------------------------------------------------------------------------

OVERLAP_THRESHOLD = 0.80          # same cut-off the Duplicates view already uses
NEAR_DUPLICATE_THRESHOLD = 0.92   # same cut-off as enhancements._similarity_action
MAX_GRAPH_URLS = 600              # keeps the force layout interactive in < 2 s
MAX_SIMILARITY_EDGES = 300
MAX_HEATMAP_URLS = 25
MAX_ACTION_ITEMS = 40

_MONEY_TYPES = {"service", "industry", "local-landing", "homepage"}
_PILLAR_HINTS = ("/guide/", "/guides/", "/pillar", "ultimate-guide", "complete-guide")
_PAGE_KIND_LABELS = {
    "service": "Service page",
    "pillar": "Pillar / hub page",
    "blog": "Blog post",
    "case-study": "Case study",
    "other": "Other page",
}
_STATUS_LABELS = {"fix": "Fix", "update": "Update", "ok": "Healthy", "opportunity": "Opportunity", "none": "Unclustered"}


def _page_kind(url: str, page_type: str) -> str:
    """Collapse classify_page_type output into the five groups the map colors by."""
    if page_type == "service":
        return "service"
    if page_type in ("industry-hub", "homepage") or any(h in url.lower() for h in _PILLAR_HINTS):
        return "pillar"
    if page_type in ("blog", "tool-review", "webinar"):
        return "blog"
    if page_type == "case-study":
        return "case-study"
    return "other"


def _is_stale(label) -> bool:
    s = str(label)
    return "Stale" in s or "Decaying" in s


def _bool_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def _pct(value: float) -> str:
    return f"{round(float(value) * 100)}%"


def _parse_cluster_ids(value) -> list[int]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    ids = []
    for part in str(value).replace("|", ",").split(","):
        part = part.strip()
        if not part or part.lower() == "nan":
            continue
        try:
            ids.append(int(float(part)))
        except ValueError:
            continue
    return ids


def _panel(kicker, title, status, what, why, action, facts=None, url=None,
           list_title="", items=None, source=""):
    return {
        "kicker": kicker, "title": title, "status": status,
        "status_label": _STATUS_LABELS.get(status, status.title()),
        "url": url or "", "what": what, "why": why, "action": action,
        "facts": [[k, v] for k, v in (facts or []) if v not in (None, "")],
        "list_title": list_title, "list": items or [], "source": source,
    }


def _pair_advice(pair: dict) -> tuple[str, str, str, str]:
    """(bucket, what, why, action) for a URL pair at or above OVERLAP_THRESHOLD."""
    a, b, pct = pair["a_slug"], pair["b_slug"], _pct(pair["sim"])
    if pair["risk"]:
        money = pair["type_a"] if pair["type_a"] in _MONEY_TYPES else pair["type_b"]
        return (
            "retitle",
            f"{a} and {b} read {pct} alike, and one of them is a {money} page.",
            "An informational page this close to a page that sells can rank in its place, "
            "so searchers land on content that doesn't convert.",
            "Retitle the informational page around a different question and link it to the "
            f"{money} page. Confirm in Search Console that both show for the same queries first.",
        )
    if pair["sim"] >= NEAR_DUPLICATE_THRESHOLD:
        return (
            "consolidate",
            f"{a} and {b} read {pct} alike, close to duplicates.",
            "Near-identical pages split links and ranking signals, so neither ranks as well "
            "as one strong page would.",
            "Consolidate candidate: if both rank for the same queries, merge the weaker page "
            "into the stronger one and 301-redirect it.",
        )
    return (
        "retitle",
        f"{a} and {b} read {pct} alike.",
        "Pages that cover the same angle can end up competing for the same searches.",
        "Differentiate: give each page its own angle, title and target question.",
    )


def build_visuals(
    url_map: pd.DataFrame,
    clusters: pd.DataFrame,
    similarity: pd.DataFrame,
    merges: pd.DataFrame,
    intent: pd.DataFrame,
    freshness: pd.DataFrame,
    competitor_table: list,
    competitor_names: list,
    content_ideas: pd.DataFrame,
    thin: pd.DataFrame,
    site_config: SiteConfig,
) -> dict:
    """Build the data behind the Overview, Cluster Map, Overlap, Gaps and Actions views."""
    from src.enhancements import classify_page_type

    strip = site_config.strip_url
    cluster_names = {int(r["cluster_id"]): str(r["cluster_name"]) for _, r in clusters.iterrows()}
    cluster_keywords = {int(r["cluster_id"]): str(r.get("keywords", "") or "") for _, r in clusters.iterrows()}

    intent_by_url = {}
    if not intent.empty and "primary_intent" in intent.columns:
        intent_by_url = dict(zip(intent["url"], intent["primary_intent"].astype(str)))
    fresh_by_url = {}
    if not freshness.empty and "freshness" in freshness.columns:
        for _, r in freshness.iterrows():
            age = r.get("age_days")
            fresh_by_url[r["url"]] = {
                "label": str(r["freshness"]),
                "lastmod": "" if pd.isna(r.get("lastmod")) else str(r.get("lastmod")),
                "age": None if age is None or pd.isna(age) else int(age),
            }

    # ---- URLs -------------------------------------------------------------
    urls: list[dict] = []
    index_by_url: dict[str, int] = {}
    for _, r in url_map.drop_duplicates("url").iterrows():
        url = str(r["url"])
        cid = int(r["main_cluster"]) if pd.notna(r["main_cluster"]) else -1
        ptype = classify_page_type(url)
        kind = _page_kind(url, ptype)
        fr = fresh_by_url.get(url, {})
        index_by_url[url] = len(urls)
        urls.append({
            "url": url, "slug": strip(url), "cid": cid,
            "cluster": cluster_names.get(cid, "Unclustered" if cid == -1 else f"Cluster {cid}"),
            "page_type": ptype, "kind": kind, "hub": kind in ("service", "pillar"),
            "intent": intent_by_url.get(url, ""),
            "freshness": fr.get("label", ""), "lastmod": fr.get("lastmod", ""), "age": fr.get("age"),
            "stale": _is_stale(fr.get("label", "")),
            "secondary": [c for c in _parse_cluster_ids(r.get("secondary_clusters")) if c != cid and c in cluster_names],
            "pairs": [],
        })

    # ---- Similarity pairs ---------------------------------------------------
    sim = similarity.copy() if similarity is not None else pd.DataFrame()
    if not sim.empty:
        sim["similarity"] = pd.to_numeric(sim["similarity"], errors="coerce")
        sim = sim.dropna(subset=["similarity"])
        sim["conversion_risk"] = _bool_series(sim["conversion_risk"]) if "conversion_risk" in sim.columns else False
        if "cluster_id" not in sim.columns:
            sim["cluster_id"] = sim["url_a"].map(lambda u: urls[index_by_url[u]]["cid"] if u in index_by_url else -1)
        for col in ("type_a", "type_b", "action"):
            if col not in sim.columns:
                sim[col] = ""
        sim = sim.drop_duplicates(subset=["url_a", "url_b"])

    pairs: list[dict] = []
    if not sim.empty:
        flagged = sim[sim["similarity"] >= OVERLAP_THRESHOLD].sort_values(
            ["conversion_risk", "similarity"], ascending=[False, False])
        for _, r in flagged.iterrows():
            a, b = str(r["url_a"]), str(r["url_b"])
            type_a = str(r["type_a"]) if str(r["type_a"]) not in ("", "nan") else classify_page_type(a)
            type_b = str(r["type_b"]) if str(r["type_b"]) not in ("", "nan") else classify_page_type(b)
            pair = {
                "a": a, "b": b, "a_slug": strip(a), "b_slug": strip(b),
                "ai": index_by_url.get(a), "bi": index_by_url.get(b),
                "sim": round(float(r["similarity"]), 4), "risk": bool(r["conversion_risk"]),
                "type_a": type_a, "type_b": type_b, "cid": int(r["cluster_id"]),
                "csv_action": "" if pd.isna(r["action"]) else str(r["action"]),
            }
            bucket, what, why, action = _pair_advice(pair)
            pair["bucket"] = bucket
            pair["panel"] = _panel(
                "Page pair", f"{pair['a_slug']}  ↔  {pair['b_slug']}", "fix", what, why, action,
                facts=[
                    ("Similarity", _pct(pair["sim"])),
                    ("Topic cluster", cluster_names.get(pair["cid"], f"Cluster {pair['cid']}")),
                    ("Page types", f"{type_a} / {type_b}"),
                    ("Money page involved", "Yes" if pair["risk"] else "No"),
                    ("Audit note", pair["csv_action"]),
                ],
                source="similarity_scores.csv (similarity, conversion_risk, action)",
            )
            pi = len(pairs)
            pairs.append(pair)
            for idx in (pair["ai"], pair["bi"]):
                if idx is not None:
                    urls[idx]["pairs"].append(pi)

    # ---- Per-URL status + panel ----------------------------------------------
    for u in urls:
        if u["pairs"]:
            u["status"] = "fix"
        elif u["stale"]:
            u["status"] = "update"
        else:
            u["status"] = "ok"
        overlap_items = []
        for pi in u["pairs"][:8]:
            p = pairs[pi]
            other = p["b_slug"] if p["a"] == u["url"] else p["a_slug"]
            overlap_items.append(f"{other} · {_pct(p['sim'])} alike" + (" · money page" if p["risk"] else ""))
        if u["pairs"]:
            p = pairs[u["pairs"][0]]
            _, what, why, action = _pair_advice(p)
        elif u["stale"]:
            what = f"Last updated {u['lastmod'] or 'over 6 months ago'}" + (f" ({u['age']} days ago)." if u["age"] is not None else ".")
            why = "Outdated pages tend to lose rankings and reader trust over time."
            action = "Update: refresh facts, examples and screenshots, then update the modified date."
        else:
            what = "No overlap or freshness issues in this audit."
            why = "This page has a clear place in its topic cluster."
            action = "No action needed. Link to it from related pages in the same cluster."
        u["panel"] = _panel(
            "Page", u["slug"], u["status"], what, why, action, url=u["url"],
            facts=[
                ("Topic cluster", u["cluster"]),
                ("Page type", _PAGE_KIND_LABELS[u["kind"]] + ("" if u["kind"] == "pillar" else f" ({u['page_type']})")),
                ("Search intent", u["intent"]),
                ("Freshness", f"{u['freshness']} · {u['lastmod']}" if u["freshness"] else ""),
                ("Also relates to", ", ".join(cluster_names[c] for c in u["secondary"])),
                ("Overlapping pages", str(len(u["pairs"])) if u["pairs"] else ""),
            ],
            list_title="Pages it overlaps with" if overlap_items else "",
            items=overlap_items,
            source="url_mapping.csv · similarity_scores.csv · content_freshness.csv · search_intent.csv",
        )

    # ---- Clusters ---------------------------------------------------------------
    merge_rows = []
    if merges is not None and not merges.empty:
        for _, r in merges.iterrows():
            merge_rows.append({
                "a": int(r["cluster_a_id"]), "b": int(r["cluster_b_id"]),
                "a_name": str(r.get("cluster_a_name", "")) or cluster_names.get(int(r["cluster_a_id"]), ""),
                "b_name": str(r.get("cluster_b_name", "")) or cluster_names.get(int(r["cluster_b_id"]), ""),
                "sim": round(float(r["similarity"]), 4), "rec": str(r.get("recommendation", "")),
            })
    for m in merge_rows:
        strong = m["rec"].upper() == "MERGE"
        m["status"] = "fix" if strong else "update"
        m["panel"] = _panel(
            "Cluster merge suggestion", f"{m['a_name']}  +  {m['b_name']}", m["status"],
            f"These two topic clusters are {_pct(m['sim'])} similar overall.",
            "Two clusters this close usually mean one subject is split across two hubs, "
            "which weakens both.",
            ("Consolidate: combine them under one pillar page; keep separate pages only where "
             "search intent differs.") if strong else
            "Review whether these should share one pillar page.",
            facts=[("Centroid similarity", _pct(m["sim"])), ("Recommendation", m["rec"])],
            source="cluster_merge_suggestions.csv",
        )

    pair_stats: dict[int, dict] = {}
    if not sim.empty:
        for cid, g in sim.groupby("cluster_id"):
            pair_stats[int(cid)] = {
                "n_pairs": int(len(g)),
                "avg_sim": round(float(g["similarity"].mean()), 4),
                "flagged": int((g["similarity"] >= OVERLAP_THRESHOLD).sum()),
                "risk": int((g["conversion_risk"] & (g["similarity"] >= OVERLAP_THRESHOLD)).sum()),
            }

    cluster_info: dict[int, dict] = {}
    by_cluster: dict[int, list[int]] = {}
    for i, u in enumerate(urls):
        by_cluster.setdefault(u["cid"], []).append(i)
    for cid, idxs in by_cluster.items():
        ps = pair_stats.get(cid, {"n_pairs": 0, "avg_sim": None, "flagged": 0, "risk": 0})
        known = [urls[i] for i in idxs if urls[i]["freshness"]]
        stale = sum(1 for u in known if u["stale"])
        cm = [m for m in merge_rows if cid in (m["a"], m["b"])]
        if cid == -1:
            status = "none"
        elif ps["flagged"] or any(m["status"] == "fix" for m in cm):
            status = "fix"
        elif (known and stale / len(known) >= 0.5) or cm:
            status = "update"
        else:
            status = "ok"
        name = cluster_names.get(cid, "Unclustered pages" if cid == -1 else f"Cluster {cid}")
        if cid == -1:
            what = f"{len(idxs)} pages did not fit any topic cluster."
            why = "Pages without a topic home get few internal links and little topical authority."
            action = "Review: link each into the closest cluster, or retire it if it has no purpose."
        elif ps["flagged"]:
            what = f"{ps['flagged']} page pairs in this topic read {_pct(OVERLAP_THRESHOLD)}+ alike"
            what += f", {ps['risk']} of them against a money page." if ps["risk"] else "."
            why = "Potential topic overlap: several pages may compete for the same searches. Not confirmed cannibalization."
            action = "Open the Overlap view for this cluster, pick one primary page per search intent, then differentiate or merge the rest."
        elif cm:
            m = max(cm, key=lambda x: x["sim"])
            other = m["b_name"] if m["a"] == cid else m["a_name"]
            what = f"This topic is {_pct(m['sim'])} similar to “{other}”."
            why = "Two hubs for one subject split authority between them."
            action = "Consider merging both clusters under one pillar page."
        elif known and stale / len(known) >= 0.5:
            what = f"{stale} of {len(known)} pages are 6+ months old."
            why = "A topic where most pages are outdated looks abandoned to readers and search engines."
            action = "Update the highest-value pages in this cluster first."
        else:
            what = "No overlap, merge or freshness issues found."
            why = "A healthy cluster: distinct pages around one subject."
            action = "Keep building: add supporting pages and link them to the hub."
        hubs = [urls[i]["slug"] for i in idxs if urls[i]["hub"]]
        cluster_info[cid] = {
            "cid": cid, "name": name, "url_count": len(idxs), "status": status,
            "n_pairs": ps["n_pairs"], "avg_sim": ps["avg_sim"], "flagged": ps["flagged"], "risk": ps["risk"],
            "stale": stale, "fresh_known": len(known),
            "panel": _panel(
                "Topic cluster", name, status, what, why, action,
                facts=[
                    ("Pages", str(len(idxs))),
                    ("Hub pages", ", ".join(hubs[:3])),
                    ("Avg similarity between its pages", f"{_pct(ps['avg_sim'])} across {ps['n_pairs']} pairs" if ps["avg_sim"] is not None else ""),
                    ("Pairs ≥ 80% alike", str(ps["flagged"]) if cid != -1 else ""),
                    ("Stale pages", f"{stale} of {len(known)}" if known else ""),
                    ("Keywords", cluster_keywords.get(cid, "")),
                ],
                list_title="Pages", items=[urls[i]["slug"] for i in idxs[:12]] + (
                    [f"+ {len(idxs) - 12} more"] if len(idxs) > 12 else []),
                source="url_mapping.csv · clusters.csv · similarity_scores.csv · cluster_merge_suggestions.csv",
            ),
        }

    # ---- Graph ---------------------------------------------------------------------
    order = sorted(range(len(urls)), key=lambda i: (
        urls[i]["status"] != "fix", urls[i]["status"] != "update", not urls[i]["hub"], i))
    keep = set(order[:MAX_GRAPH_URLS])
    nodes, edges = [], []
    kept_clusters = sorted({urls[i]["cid"] for i in keep})
    for cid in kept_clusters:
        ci = cluster_info[cid]
        nodes.append({"id": f"c{cid}", "type": "cluster", "cid": cid, "label": ci["name"],
                      "size": ci["url_count"], "status": ci["status"]})
    for i in sorted(keep):
        u = urls[i]
        nodes.append({"id": f"u{i}", "type": "url", "ui": i, "cid": u["cid"], "label": u["slug"],
                      "kind": u["kind"], "hub": u["hub"], "status": u["status"]})
        edges.append({"from": f"c{u['cid']}", "to": f"u{i}", "type": "member"})
        for sc in u["secondary"]:
            if sc in kept_clusters:
                edges.append({"from": f"u{i}", "to": f"c{sc}", "type": "secondary"})
    sim_edges_total = 0
    for p in sorted(range(len(pairs)), key=lambda k: -pairs[k]["sim"]):
        pr = pairs[p]
        if pr["ai"] in keep and pr["bi"] in keep:
            sim_edges_total += 1
            if sim_edges_total <= MAX_SIMILARITY_EDGES:
                edges.append({"from": f"u{pr['ai']}", "to": f"u{pr['bi']}", "type": "similar",
                              "sim": pr["sim"], "risk": pr["risk"], "pi": p})
    for mi, m in enumerate(merge_rows):
        if m["a"] in kept_clusters and m["b"] in kept_clusters:
            edges.append({"from": f"c{m['a']}", "to": f"c{m['b']}", "type": "merge",
                          "sim": m["sim"], "status": m["status"], "mi": mi})
    graph = {
        "nodes": nodes, "edges": edges,
        "meta": {
            "url_nodes": len(keep), "url_total": len(urls),
            "similar_edges": min(sim_edges_total, MAX_SIMILARITY_EDGES), "similar_total": sim_edges_total,
            "threshold": OVERLAP_THRESHOLD,
            "truncated": len(keep) < len(urls) or sim_edges_total > MAX_SIMILARITY_EDGES,
        },
    }

    # ---- Overlap heatmaps --------------------------------------------------------------
    overlap_clusters = []
    if not sim.empty:
        pair_index = {(p["a"], p["b"]): k for k, p in enumerate(pairs)}
        for cid, g in sim.groupby("cluster_id"):
            cid = int(cid)
            members = pd.unique(pd.concat([g["url_a"], g["url_b"]])).tolist()
            truncated = len(members) > MAX_HEATMAP_URLS
            if truncated:
                peak = pd.concat([g[["url_a", "similarity"]].rename(columns={"url_a": "u"}),
                                  g[["url_b", "similarity"]].rename(columns={"url_b": "u"})])
                members = peak.groupby("u")["similarity"].max().sort_values(ascending=False).index[:MAX_HEATMAP_URLS].tolist()
            pos = {u: k for k, u in enumerate(members)}
            n = len(members)
            z = [[None] * n for _ in range(n)]
            pidx = [[None] * n for _ in range(n)]
            risk_cells = []
            for _, r in g.iterrows():
                a, b = r["url_a"], r["url_b"]
                if a not in pos or b not in pos:
                    continue
                i, j = pos[a], pos[b]
                v = round(float(r["similarity"]), 3)
                z[i][j] = z[j][i] = v
                k = pair_index.get((a, b))
                pidx[i][j] = pidx[j][i] = k
                if bool(r["conversion_risk"]) and v >= OVERLAP_THRESHOLD:
                    risk_cells.append([i, j])
            ci = cluster_info.get(cid)
            ps = pair_stats[cid]
            overlap_clusters.append({
                "cid": cid, "name": cluster_names.get(cid, f"Cluster {cid}"),
                "url_count": ci["url_count"] if ci else n,
                "n_pairs": ps["n_pairs"], "avg_sim": ps["avg_sim"],
                "flagged": ps["flagged"], "risk": ps["risk"],
                "stale": ci["stale"] if ci else 0, "fresh_known": ci["fresh_known"] if ci else 0,
                "slugs": [strip(u) for u in members], "z": z, "pairs": pidx,
                "risk_cells": risk_cells, "truncated": truncated,
            })
        overlap_clusters.sort(key=lambda c: (-c["flagged"], -c["risk"], -(c["avg_sim"] or 0)))
    overlap = {"threshold": OVERLAP_THRESHOLD, "clusters": overlap_clusters}

    # ---- Gap matrix ---------------------------------------------------------------------
    ideas = []
    if content_ideas is not None and not content_ideas.empty:
        ideas = content_ideas.fillna("").to_dict("records")
    idea_by_topic = {}
    for k, idea in enumerate(ideas):
        topic = str(idea.get("gap_topic", "")).strip().lower()
        if topic and topic not in idea_by_topic:
            idea_by_topic[topic] = k

    def _idea_panel(idea: dict) -> dict:
        questions = [q.strip() for q in str(idea.get("key_questions", "")).split("|") if q.strip()]
        return _panel(
            "Content idea", str(idea.get("title", "")), "opportunity",
            f"Competitors cover “{idea.get('gap_topic', '')}”" +
            (f" ({idea.get('covered_by')})" if idea.get("covered_by") else "") + "; you don't.",
            "Topics competitors already publish on are proven demand you currently can't capture.",
            f"Create: {idea.get('title', '')}",
            facts=[
                ("Priority", str(idea.get("priority", ""))),
                ("Format", str(idea.get("content_type", ""))),
                ("Audience", str(idea.get("target_audience", ""))),
                ("Length", f"~{idea.get('est_word_count')} words" if idea.get("est_word_count") else ""),
                ("Closest existing cluster", str(idea.get("spoke_cluster", ""))),
            ],
            list_title="Questions the page should answer" if questions else "",
            items=questions[:6],
            source="content_ideas.csv",
        )

    gap_rows = []
    for row in competitor_table:
        covered = [c for c in competitor_names if row["competitors"].get(c)]
        status = row["status"]
        idea_idx = idea_by_topic.get(row["topic"].strip().lower())
        if status == "GAP":
            pstatus = "opportunity"
            what = f"{len(covered)} of {len(competitor_names)} competitors cover “{row['topic']}”; {site_config.name} doesn't."
            why = "Topics competitors already rank for are traffic you can't win without a page."
            if idea_idx is not None:
                idea = ideas[idea_idx]
                action = f"Create: {idea.get('title', '')} ({idea.get('content_type', '')})."
            else:
                action = "Create a page for this topic, or extend the closest existing cluster to cover it."
        elif status == "ADVANTAGE":
            pstatus = "ok"
            what = f"Only {site_config.name} covers “{row['topic']}”."
            why = "Unique topics are a moat: no competitor is fighting you for them."
            action = "Keep it fresh and link to it from related pages."
        else:
            pstatus = "ok"
            what = f"{site_config.name} and {len(covered)} competitor(s) cover “{row['topic']}”."
            why = "Shared topics are table stakes; depth and freshness decide who ranks."
            action = "Check your page is the most complete and up to date."
        panel = _panel("Competitor topic", row["topic"], pstatus, what, why, action,
                       facts=[("Covered by competitors", ", ".join(covered) or "None"),
                              ("Covered by you", "Yes" if row["target"] else "No"),
                              ("Status", status)],
                       source="competitor_gap_*.csv" + (" · content_ideas.csv" if idea_idx is not None else ""))
        if idea_idx is not None:
            panel["idea"] = _idea_panel(ideas[idea_idx])
        gap_rows.append({"topic": row["topic"], "you": bool(row["target"]), "comps": [bool(row["competitors"].get(c)) for c in competitor_names],
                         "n_comp": len(covered), "status": status, "has_idea": idea_idx is not None, "panel": panel})
    status_rank = {"GAP": 0, "SHARED": 1, "ADVANTAGE": 2}
    gap_rows.sort(key=lambda r: (-r["n_comp"], status_rank.get(r["status"], 3), r["topic"]))
    gap_counts = {s: sum(1 for r in gap_rows if r["status"] == s) for s in ("GAP", "SHARED", "ADVANTAGE")}
    gaps = {"competitors": list(competitor_names), "rows": gap_rows, "counts": gap_counts}

    # ---- Action board --------------------------------------------------------------------------
    def _item(title, sub, panel):
        return {"title": title, "sub": sub, "panel": panel}

    consolidate = [_item(f"{m['a_name']} + {m['b_name']}", f"Clusters {_pct(m['sim'])} similar · {m['rec']}", m["panel"])
                   for m in sorted(merge_rows, key=lambda m: (m["status"] != "fix", -m["sim"]))]
    consolidate += [_item(f"{p['a_slug']} ↔ {p['b_slug']}", f"Pages {_pct(p['sim'])} alike", p["panel"])
                    for p in pairs if p["bucket"] == "consolidate"]
    retitle = [_item(f"{p['a_slug']} ↔ {p['b_slug']}",
                     f"{_pct(p['sim'])} alike" + (" · money page involved" if p["risk"] else ""), p["panel"])
               for p in pairs if p["bucket"] == "retitle"]
    stale_urls = sorted([u for u in urls if u["stale"]], key=lambda u: -(u["age"] or 0))
    update = [_item(u["slug"], f"{u['freshness']} · last updated {u['lastmod']}", u["panel"]) for u in stale_urls]
    expand = []
    if thin is not None and not thin.empty:
        prio = {key: p for key, _label, p in _THIN_CATEGORIES}
        label_of = {key: label for key, label, _p in _THIN_CATEGORIES}
        for _, r in thin.sort_values(["category", "word_count"], key=lambda s: s.map(prio) if s.name == "category" else s).iterrows():
            words = int(r["word_count"])
            expand.append(_item(strip(r["url"]), f"{words} words · {label_of.get(r['category'], '')}", _panel(
                "Thin page", strip(r["url"]), "update",
                f"Only {words} words of content.",
                "Very short pages rarely rank and can drag down how search engines judge the site's depth.",
                str(r["recommendation"]), url=r["url"],
                facts=[("Page category", label_of.get(r["category"], "")), ("Word count", str(words))],
                source="skipped_urls.csv (reason)",
            )))
    prio_rank = {"P1": 0, "P2": 1, "P3": 2}
    create = [_item(str(i.get("title", "")),
                    f"{i.get('priority', '')} · {i.get('content_type', '')} · covered by {i.get('covered_by', '')}",
                    _idea_panel(i))
              for i in sorted(ideas, key=lambda i: (prio_rank.get(str(i.get("priority")), 9),
                                                     -int(float(i.get("num_competitors") or 0))))]
    if not create:
        create = [_item(r["topic"], f"Covered by {r['n_comp']} competitor(s)", r["panel"])
                  for r in gap_rows if r["status"] == "GAP"]

    def _column(key, label, status, blurb, items, source):
        return {"key": key, "label": label, "status": status, "blurb": blurb,
                "count": len(items), "items": items[:MAX_ACTION_ITEMS], "source": source}

    actions = [
        _column("consolidate", "Consolidate", "fix",
                "Near-duplicate pages and look-alike clusters that may be better as one.",
                consolidate, "cluster_merge_suggestions.csv · similarity_scores.csv"),
        _column("retitle", "Retitle", "fix",
                "Similar pages that need distinct angles, starting with ones that touch a money page.",
                retitle, "similarity_scores.csv"),
        _column("update", "Update", "update",
                "Pages last modified 6+ months ago.", update, "content_freshness.csv"),
        _column("expand", "Expand", "update",
                "Pages with too little content to rank.", expand, "skipped_urls.csv"),
        _column("create", "Create", "opportunity",
                "New pages for topics competitors cover and you don't.", create,
                "content_ideas.csv" if ideas else "competitor_gap_*.csv"),
    ]

    # ---- KPIs + headline ----------------------------------------------------------------------------
    real_clusters = [c for c in cluster_info.values() if c["cid"] != -1]
    risk_pairs = sum(1 for p in pairs if p["risk"])
    kpis = [
        {"key": "clusters", "label": "Topic clusters", "value": len(real_clusters), "status": "ok", "tab": "map",
         "sub": f"{sum(c['url_count'] for c in real_clusters)} pages grouped by meaning",
         "tip": "Groups of pages about the same subject, found by comparing what each page says."},
        {"key": "overlap", "label": "Overlap issues", "value": len(pairs), "status": "fix" if pairs else "ok", "tab": "overlap",
         "sub": f"page pairs {_pct(OVERLAP_THRESHOLD)}+ alike" + (f" · {risk_pairs} touch a money page" if risk_pairs else ""),
         "tip": "Two pages whose text is at least 80% similar. They may compete for the same searches; this is not confirmed cannibalization."},
        {"key": "gaps", "label": "Competitor gaps", "value": gap_counts["GAP"] if competitor_names else None,
         "status": "opportunity", "tab": "gaps",
         "sub": (f"topics {len(competitor_names)} competitors cover that you don't" if competitor_names
                 else "No competitor data in this run"),
         "tip": "Topics at least one competitor publishes on that this site has no page for."},
    ]
    findings = []
    # Same ordering as the Overlap view's default cluster, so the headline and that view agree.
    worst = max(real_clusters, key=lambda c: (c["flagged"], c["risk"], c["avg_sim"] or 0), default=None)
    if pairs and worst and worst["flagged"]:
        findings.append({"status": "fix", "tab": "overlap", "cid": worst["cid"],
                         "text": f"{len(pairs)} pairs of pages read {_pct(OVERLAP_THRESHOLD)}+ alike. Worst: “{worst['name']}” ({worst['flagged']} pairs).",
                         "sub": "These pages may compete for the same searches" +
                                (f"; {risk_pairs} pairs put an article against a money page." if risk_pairs else ".")})
    if stale_urls:
        findings.append({"status": "update", "tab": "actions",
                         "text": f"{len(stale_urls)} pages haven't been updated in 6+ months.",
                         "sub": "Refreshing them is the cheapest ranking win."})
    if expand:
        findings.append({"status": "update", "tab": "actions",
                         "text": f"{len(expand)} pages are too thin to rank.", "sub": ""})
    if competitor_names and gap_counts["GAP"]:
        findings.append({"status": "opportunity", "tab": "gaps",
                         "text": f"{gap_counts['GAP']} topics competitors cover that you don't.",
                         "sub": f"{sum(1 for r in gap_rows if r['status'] == 'GAP' and r['has_idea'])} already have a content brief."})
    if not findings:
        findings.append({"status": "ok", "tab": "map", "text": "No overlap, freshness or gap issues found in this run.", "sub": ""})

    return {
        "urls": [{k: u[k] for k in ("url", "slug", "cid", "cluster", "kind", "hub", "intent",
                                     "freshness", "status", "panel")} | {"n_pairs": len(u["pairs"])}
                 for u in urls],
        "clusters": {str(cid): {k: v for k, v in c.items()} for cid, c in cluster_info.items()},
        "pairs": [{"panel": p["panel"], "sim": p["sim"], "risk": p["risk"], "cid": p["cid"]} for p in pairs],
        "merges": [{"panel": m["panel"]} for m in merge_rows],
        "graph": graph,
        "overlap": overlap,
        "gaps": gaps,
        "actions": actions,
        "kpis": kpis,
        "findings": findings,
    }


def generate_dashboard(site_config: SiteConfig | None = None, sample_data: bool = False):
    """Build a self-contained interactive HTML dashboard.

    sample_data=True marks the output as synthetic (badge in the header) — used by
    scripts/generate_demo_data.py.
    """
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
    thin["is_listing"] = thin["url"].apply(is_intentionally_thin).astype(bool)
    thin["page_type"] = thin["url"].apply(classify_page_type)
    thin_actionable = thin[~thin["is_listing"]].copy()
    thin_listings = thin[thin["is_listing"]].copy()

    thin_actionable["category"] = thin_actionable["url"].apply(_classify_thin)
    thin_actionable["recommendation"] = [
        _thin_recommendation(r["url"], r["category"]) for _, r in thin_actionable.iterrows()
    ]
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

    # RAG: load the retrieval index once so we can fetch actual chunk text per URL
    # for the cannibalization advisor. The advisor stops guessing from URL patterns
    # and starts judging from real page content.
    rag_index = None
    if llm_on:
        try:
            from src.retrieval import get_index as _get_rag_index
            rag_index = _get_rag_index()
            if rag_index:
                logger.info("RAG retrieval index loaded (%d chunks, %d URLs) — cannib advisor will see actual content",
                            rag_index.n_chunks, rag_index.n_urls)
            else:
                logger.info("RAG index not available — cannib advisor will judge from URL patterns only")
        except Exception:
            logger.exception("Could not load RAG index (cannib advisor degrades to URL-only)")

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

        # Try LLM advisor first — with RAG context if the index is available
        llm_verdict = None
        if llm_on:
            try:
                # RAG: pull a representative chunk per URL in this cluster
                chunks_by_url = None
                if rag_index:
                    chunks_by_url = {}
                    for u in url_details_list:
                        per_url_chunks = rag_index.search_by_url(u["url"], k=1)
                        if per_url_chunks:
                            chunks_by_url[u["url"]] = per_url_chunks[0].text

                llm_verdict = llm_advisor.advise_cannibalization(
                    cluster_name=str(row["cluster_name"]),
                    keywords=keywords_list,
                    urls=url_details_list,
                    chunks_by_url=chunks_by_url,
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
                    u["recommendation"] = v.get("verdict", "REVIEW")
                    u["action"] = v.get("action") or "Review query and intent evidence"
                else:
                    u["recommendation"] = "REVIEW"
                    u["action"] = "Insufficient evidence: no per-URL verdict from advisor"
            winner_slug = llm_verdict.get("winner_url")
        else:
            # Rule-based fallback
            for u in url_details_list:
                u["recommendation"] = "REVIEW"
                u["action"] = "Potential overlap: verify queries and intent. Supporting pages may be complementary."

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

        if not llm_verdict:
            analysis = "Potential topic overlap only. Shared cluster membership does not establish search competition."
            is_real_cannib = None
            has_conversion_risk = False
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

        # Per-competitor breakdown — for each competitor, count topics they cover that
        # we don't (gaps), topics we both cover (shared), topics only we cover (adv).
        per_comp = []
        for cname in competitor_names:
            c_gaps = c_shared = c_advantages = 0
            top_gap_topics = []
            for row in competitor_table:
                comp_has = bool(row["competitors"].get(cname))
                target_has = bool(row["target"])
                if comp_has and not target_has:
                    c_gaps += 1
                    if len(top_gap_topics) < 5:
                        top_gap_topics.append(row["topic"])
                elif comp_has and target_has:
                    c_shared += 1
                elif target_has and not comp_has:
                    c_advantages += 1
            per_comp.append({
                "name": cname,
                "gaps": c_gaps,
                "shared": c_shared,
                "advantages": c_advantages,
                "top_gap_topics": top_gap_topics,
            })

        enh["competitor"] = {
            "rows": competitor_table,
            "names": competitor_names,
            "per_competitor": per_comp,
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

        # Intent by cluster — joins intent + cluster assignment so each cluster reports
        # its dominant intent + breakdown. Useful for spotting clusters that are split
        # between commercial / informational pages (often a cannibalization signal).
        intent_url_map = intent_df.merge(url_map[["url", "main_cluster"]], on="url", how="left")
        cluster_name_lookup = dict(zip(clusters["cluster_id"], clusters["cluster_name"]))
        intent_by_cluster = []
        for cid, group in intent_url_map[intent_url_map["main_cluster"] != -1].groupby("main_cluster"):
            counts = group["primary_intent"].value_counts().to_dict()
            total = int(sum(counts.values()))
            if total == 0:
                continue
            dominant_intent, dominant_n = next(iter(group["primary_intent"].value_counts().items()))
            mix_score = round(1 - (dominant_n / total), 2)  # 0 = pure, 1 = even mix
            intent_by_cluster.append({
                "cluster_id": int(cid),
                "cluster_name": cluster_name_lookup.get(cid, f"Cluster {cid}"),
                "url_count": total,
                "dominant_intent": str(dominant_intent),
                "mix_score": mix_score,
                "informational": int(counts.get("informational", 0)),
                "commercial": int(counts.get("commercial", 0)),
                "transactional": int(counts.get("transactional", 0)),
                "navigational": int(counts.get("navigational", 0)),
            })
        intent_by_cluster.sort(key=lambda r: r["url_count"], reverse=True)
        enh["intent_by_cluster"] = intent_by_cluster

        # Per-intent URL list (top URLs by signal strength) — gives the user concrete
        # examples of what the analyzer thinks each intent looks like on their site.
        intent_urls: dict = {}
        for intent_label in ("informational", "commercial", "transactional", "navigational"):
            sub = intent_df[intent_df["primary_intent"] == intent_label].copy()
            if sub.empty:
                continue
            sig_col = f"{intent_label}_signals"
            if sig_col in sub.columns:
                sub = sub.sort_values(sig_col, ascending=False)
            sub_records = []
            for _, row in sub.head(15).iterrows():
                sub_records.append({
                    "url": site_config.strip_url(row["url"]),
                    "confidence": row.get("confidence", 0),
                    "secondary": row.get("secondary_intent", ""),
                    "signals": int(row.get(sig_col, 0)) if sig_col in sub.columns else 0,
                })
            intent_urls[intent_label] = sub_records
        enh["intent_urls"] = intent_urls

    if not freshness_df.empty:
        enh["freshness"] = freshness_df["freshness"].value_counts().to_dict()

        # Detect data-quality issue: if everything lands in the youngest bucket, the
        # underlying lastmod values are almost certainly the site's deploy timestamp
        # (uniform across pages) rather than per-article publish dates.
        unique_dates = freshness_df["lastmod"].nunique() if "lastmod" in freshness_df.columns else 0
        date_span_days = 0
        if unique_dates > 0:
            try:
                from datetime import datetime as _dt
                ds = pd.to_datetime(freshness_df["lastmod"], errors="coerce").dropna()
                if not ds.empty:
                    date_span_days = int((ds.max() - ds.min()).days)
            except Exception:
                date_span_days = 0
        all_in_one_bucket = len(set(freshness_df["freshness"])) == 1
        if all_in_one_bucket and date_span_days <= 14:
            enh["freshness_finding"] = {
                "title": "Source data limitation detected",
                "summary": (
                    f"All {len(freshness_df)} URLs report the same freshness bucket because the "
                    f"underlying dates span only {date_span_days} days — this is the deploy "
                    "timestamp of the CMS, not per-article publish dates."
                ),
                "evidence": [
                    "Sitemap (sitemap.xml) reports no <lastmod> values per URL.",
                    "HTML pages do not expose <meta property=\"article:published_time\"> or JSON-LD datePublished.",
                    "The only available signal is the HTTP Last-Modified header, which equals the deploy time.",
                ],
                "recommendation": (
                    "Add `article:published_time` and `article:modified_time` meta tags (or JSON-LD "
                    "Article schema with datePublished/dateModified) to blog post + recording templates. "
                    "Without these, search engines can't show 'fresh' badges in SERPs and tools like this "
                    "audit can't surface stale-content opportunities."
                ),
            }

    # Content inventory — counts of URLs by URL pattern. Always useful, especially when
    # freshness data is unavailable.
    inventory_buckets = {
        "Blog posts": [u for u in url_map["url"] if any(p in u for p in ("/post/", "/blog/", "/posts/", "/article/"))],
        "Case studies": [u for u in url_map["url"] if "/case-stud" in u.lower() or "/customer-stories" in u.lower()],
        "Recordings / podcasts": [u for u in url_map["url"] if any(p in u for p in ("/recordings/", "/podcast", "/episode"))],
        "Author / team pages": [u for u in url_map["url"] if any(p in u for p in ("/author/", "/team/", "/people/"))],
        "Policies / legal": [u for u in url_map["url"] if any(p in u for p in ("/policies/", "/legal", "/privacy", "/terms"))],
        "Tools / calculators": [u for u in url_map["url"] if any(p in u for p in ("/tools/", "/calculator", "/calculators"))],
        "Other": [],
    }
    classified = set()
    for k, v in inventory_buckets.items():
        if k != "Other":
            classified.update(v)
    inventory_buckets["Other"] = [u for u in url_map["url"] if u not in classified]
    enh["content_inventory"] = [
        {"category": k, "count": len(v)} for k, v in inventory_buckets.items() if v
    ]

    # Static brand profile — read from the LLM-generated cache so the Brand Voice tab
    # has content even when per-URL scoring (brand_voice_scores.csv) hasn't been run.
    try:
        from src.config import cache_dir as _cache_dir
        brand_profile_path = os.path.join(_cache_dir(), "brand_profile.json")
        if os.path.exists(brand_profile_path):
            import json as _json
            with open(brand_profile_path) as _f:
                profile = _json.load(_f)
            if profile.get("tone") or profile.get("do") or profile.get("audience"):
                enh["brand_profile"] = {
                    "brand_name": profile.get("brand_name", site_config.name),
                    "tone": profile.get("tone", []),
                    "audience": profile.get("audience", ""),
                    "do": profile.get("do", []),
                    "dont": profile.get("dont", []),
                    "example_phrases": profile.get("example_phrases", []),
                    "writing_style": profile.get("writing_style", {}),
                }
    except Exception:
        logger.exception("Failed to load brand profile (non-fatal)")

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

    # Vector map (2D embedding projection per URL) — built by main.py Step 13b-2
    vector_map_data = {"points": [], "cluster_legend": {}}
    vmap_path = os.path.join(out, "vector_map.json")
    if os.path.exists(vmap_path):
        try:
            import json as _json
            with open(vmap_path) as f:
                vector_map_data = _json.load(f)
        except Exception:
            logger.exception("Could not load vector_map.json")

    # Latest agent run + lessons (for the Recommend + Lessons tabs)
    agent_run = None
    agent_lessons_md = ""
    try:
        from src.agent import memory as _agent_mem
        from src.agent import lessons as _agent_lessons
        recent = _agent_mem.recent_runs(site_config.name, limit=1)
        if recent:
            full = _agent_mem.load_run_trace(site_config.name, recent[0]["run_id"])
            if full:
                agent_run = full
        lpath = _agent_lessons.lessons_path(
            site_config.name,
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../runs")),
        )
        if os.path.exists(lpath):
            with open(lpath) as f:
                agent_lessons_md = f.read()
    except Exception:
        logger.exception("Could not load agent run / lessons (non-fatal)")

    # Pre-render sample RAG Q&A for the Ask tab (file:// dashboards can't invoke the CLI live).
    ask_examples = []
    try:
        from src import llm_advisor as _llm
        if _llm.is_enabled():
            from src.site_chat import ask as _ask
            sample_questions = [
                f"What does {site_config.name} say about its main differentiator?",
                "Where does the site's content overlap most with competitors?",
                "Which topics on this site are written for product marketers vs growth teams?",
            ]
            for q in sample_questions:
                a = _ask(q, k=5)
                ask_examples.append({
                    "q": q,
                    "answer": a.answer,
                    "citations": a.citations[:5],
                    "used_chunks": a.used_chunks,
                })
            logger.info("Pre-rendered %d Ask-the-Audit examples", len(ask_examples))
    except Exception:
        logger.exception("Could not pre-render Ask examples (non-fatal)")

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

    visuals = build_visuals(
        url_map=url_map,
        clusters=clusters,
        similarity=_load("similarity_scores.csv"),
        merges=_load("cluster_merge_suggestions.csv"),
        intent=intent_df,
        freshness=freshness_df,
        competitor_table=competitor_table,
        competitor_names=competitor_names,
        content_ideas=content_ideas_df,
        thin=thin_actionable,
        site_config=site_config,
    )

    from src.dashboard_html import build_html
    html = build_html(
        visuals=visuals,
        sample_data=sample_data,
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
        vector_map=vector_map_data,
        ask_examples=ask_examples,
        agent_run=agent_run,
        agent_lessons_md=agent_lessons_md,
    )

    out_path = os.path.join(out, "dashboard.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("Dashboard saved to %s", out_path)
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = generate_dashboard()
    print(f"Dashboard: {path}")
