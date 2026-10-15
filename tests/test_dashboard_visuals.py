"""Dashboard visuals: demo render has populated Cluster Map / Overlap / Gaps / Actions, and
the payload builders only ever restate numbers from the pipeline CSVs."""

import importlib.util
import json
import os
import re

import numpy as np
import pandas as pd
import pytest

from src.config import SiteConfig, set_runtime_cache_dir
from src import dashboard
from src.dashboard import OVERLAP_THRESHOLD, build_visuals, generate_dashboard

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_demo_module():
    spec = importlib.util.spec_from_file_location("generate_demo_data", os.path.join(ROOT, "scripts", "generate_demo_data.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _payload(html: str, name: str):
    match = re.search(rf"^const {name}=(.*);$", html, flags=re.M)
    assert match, f"{name} payload missing from dashboard"
    return json.loads(match.group(1))


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("demo")
    out, cache = str(tmp / "output"), str(tmp / "cache")
    try:
        cfg = _load_demo_module().write_demo_dataset(out, cache)
        html_path = generate_dashboard(site_config=cfg, sample_data=True)
        with open(html_path, encoding="utf-8") as f:
            html = f.read()
        yield {"html": html, "vis": _payload(html, "VIS"), "out": out}
    finally:
        set_runtime_cache_dir(None)


def test_demo_has_new_tabs_and_more_menu(demo):
    html = demo["html"]
    for tab in ("overview", "map", "overlap", "gaps", "actions", "explorer"):
        assert f'class="nav-tab' in html and f'data-tab="{tab}"' in html
        assert f'id="tab-{tab}"' in html
    # Secondary views moved behind "More", not deleted.
    for tab in ("agent", "lessons", "ask", "brand", "intent", "freshness"):
        assert f'class="more-item" data-tab="{tab}"' in html
        assert f'id="tab-{tab}"' in html
    assert "SAMPLE DATA" in html
    assert "potential topic overlap, not confirmed cannibalization" in html
    # The old quadrant plotted URL count against itself; it must be gone.
    assert 'id="quadrant"' not in html


def test_demo_payloads_are_populated(demo):
    vis = demo["vis"]
    graph = vis["graph"]
    types = {n["type"] for n in graph["nodes"]}
    edge_types = {e["type"] for e in graph["edges"]}
    assert types == {"cluster", "url"}
    assert {"member", "secondary", "similar", "merge"} <= edge_types
    assert any(n.get("hub") for n in graph["nodes"] if n["type"] == "url")

    overlap = vis["overlap"]["clusters"]
    assert overlap and all(c["z"] and len(c["z"]) == len(c["slugs"]) for c in overlap)
    assert any(c["risk_cells"] for c in overlap)

    gaps = vis["gaps"]
    assert gaps["competitors"] and gaps["counts"]["GAP"] > 0
    assert any(r["panel"].get("idea") for r in gaps["rows"] if r["status"] == "GAP")
    n_comp = [r["n_comp"] for r in gaps["rows"]]
    assert n_comp == sorted(n_comp, reverse=True)

    lanes = {c["key"]: c for c in vis["actions"]}
    assert list(lanes) == ["consolidate", "retitle", "update", "expand", "create"]
    assert all(c["count"] > 0 and c["items"] for c in lanes.values())

    kpis = {k["key"]: k["value"] for k in vis["kpis"]}
    assert kpis["clusters"] > 0 and kpis["overlap"] > 0 and kpis["gaps"] > 0
    assert vis["findings"][0]["status"] == "fix"


def test_numbers_trace_to_csvs(demo):
    vis, out = demo["vis"], demo["out"]
    sim = pd.read_csv(os.path.join(out, "similarity_scores.csv"))
    flagged = sim[sim["similarity"] >= OVERLAP_THRESHOLD]
    assert len(vis["pairs"]) == len(flagged) == {k["key"]: k["value"] for k in vis["kpis"]}["overlap"]
    for c in vis["overlap"]["clusters"]:
        rows = sim[sim["cluster_id"] == c["cid"]]
        assert c["n_pairs"] == len(rows)
        assert c["avg_sim"] == pytest.approx(rows["similarity"].mean(), abs=1e-4)
    gap_topics = set()
    for name in os.listdir(out):
        if name.startswith("competitor_gap_"):
            df = pd.read_csv(os.path.join(out, name))
            gap_topics |= set(df["keyword"])
    assert {r["topic"] for r in vis["gaps"]["rows"]} == gap_topics
    fresh = pd.read_csv(os.path.join(out, "content_freshness.csv"))
    stale = fresh["freshness"].str.contains("Stale|Decaying")
    assert {c["key"]: c["count"] for c in vis["actions"]}["update"] == int(stale.sum())


def test_overlap_scatter_y_is_not_derived_from_x(demo):
    # Summary scatter plots pages-in-topic (x) against average pair similarity (y):
    # topics with the same page count must be able to differ on y.
    by_size = {}
    for c in demo["vis"]["overlap"]["clusters"]:
        by_size.setdefault(c["url_count"], set()).add(c["avg_sim"])
    assert any(len(v) > 1 for v in by_size.values())


def _tiny_inputs():
    urls = [
        "https://ex.com/services/crm",          # money page
        "https://ex.com/blog/crm-tips",         # overlaps the service page
        "https://ex.com/blog/crm-guide",        # near-duplicate of crm-tips
        "https://ex.com/blog/old-post",         # stale only
    ]
    url_map = pd.DataFrame({"url": urls, "main_cluster": [0, 0, 0, 0], "secondary_clusters": ["", "", "", ""]})
    clusters = pd.DataFrame({"cluster_id": [0], "cluster_name": ["CRM"], "keywords": ["crm"]})
    similarity = pd.DataFrame([
        {"cluster_id": 0, "url_a": urls[0], "url_b": urls[1], "type_a": "service", "type_b": "blog",
         "similarity": 0.85, "conversion_risk": True, "action": "REVIEW"},
        {"cluster_id": 0, "url_a": urls[1], "url_b": urls[2], "type_a": "blog", "type_b": "blog",
         "similarity": 0.95, "conversion_risk": False, "action": "REVIEW"},
        {"cluster_id": 0, "url_a": urls[2], "url_b": urls[3], "type_a": "blog", "type_b": "blog",
         "similarity": 0.40, "conversion_risk": False, "action": "OK"},
    ])
    freshness = pd.DataFrame({"url": [urls[3]], "lastmod": ["2024-01-01"], "age_days": [600],
                              "freshness": ["Decaying (12+ months)"]})
    return url_map, clusters, similarity, freshness


def _build(**overrides):
    url_map, clusters, similarity, freshness = _tiny_inputs()
    args = dict(url_map=url_map, clusters=clusters, similarity=similarity, merges=pd.DataFrame(),
                intent=pd.DataFrame(), freshness=freshness, competitor_table=[], competitor_names=[],
                content_ideas=pd.DataFrame(), thin=pd.DataFrame(), site_config=SiteConfig(name="Ex", domain="ex.com"))
    args.update(overrides)
    return build_visuals(**args)


def test_build_visuals_buckets_and_statuses():
    vis = _build()
    statuses = {u["slug"]: u["status"] for u in vis["urls"]}
    assert statuses == {"/services/crm": "fix", "/blog/crm-tips": "fix", "/blog/crm-guide": "fix", "/blog/old-post": "update"}
    lanes = {c["key"]: c["count"] for c in vis["actions"]}
    assert lanes["retitle"] == 1      # money-page pair
    assert lanes["consolidate"] == 1  # 95% pair
    assert lanes["update"] == 1
    assert lanes["create"] == 0
    assert [k["value"] for k in vis["kpis"] if k["key"] == "gaps"] == [None]
    cluster = vis["clusters"]["0"]
    assert cluster["flagged"] == 2 and cluster["risk"] == 1 and cluster["n_pairs"] == 3
    # Below-threshold pairs appear in the heatmap but never as flagged pairs.
    assert len(vis["pairs"]) == 2
    z = vis["overlap"]["clusters"][0]["z"]
    assert sorted(v for row in z for v in row if v is not None) == [0.4, 0.4, 0.85, 0.85, 0.95, 0.95]


def test_graph_caps_similarity_edges(monkeypatch):
    monkeypatch.setattr(dashboard, "MAX_SIMILARITY_EDGES", 1)
    meta = _build()["graph"]["meta"]
    assert meta["similar_edges"] == 1 and meta["similar_total"] == 2 and meta["truncated"]


def test_non_sample_render_has_no_badge():
    from src.dashboard_html import build_html
    html = build_html(
        site_config=SiteConfig(name="Ex", domain="ex.com"), treemap_data={"labels": [], "values": [], "ids": [], "keywords": []},
        cannib_chart_data={"labels": [], "values": []}, cannib_detail=[], content_types={}, all_clusters=[],
        url_table=[], stats={"total_urls": 0, "total_clusters": 0, "cannib_flags": 0, "skipped": 0,
                             "skipped_listings": 0, "noise": 0, "thin_local": 0, "thin_tools": 0, "thin_other": 0},
        thin_tools=[], thin_local=[], thin_other=[], top_cannib_summary=[], visuals=_build(),
    )
    assert "SAMPLE DATA" not in html
    assert _payload(html, "VIS")["graph"]["nodes"]


def test_vector_map_reads_npz_embedding_cache(tmp_path):
    from src.config import save_site_config
    from src.vector_map import build_vector_map
    set_runtime_cache_dir(str(tmp_path / "cache"))
    try:
        save_site_config(SiteConfig(name="T", domain="ex.com", output_dir=str(tmp_path / "out")))
        os.makedirs(tmp_path / "out", exist_ok=True)
        chunks = pd.DataFrame({"url": [f"https://ex.com/p{i // 2}" for i in range(12)],
                               "cluster_id": [i // 6 for i in range(12)]})
        chunks.to_pickle(tmp_path / "cache" / "chunks_df.pkl")
        rng = np.random.default_rng(0)
        np.savez(tmp_path / "cache" / "embeddings.pkl.npz", embeddings=rng.normal(size=(12, 8)).astype(np.float32),
                 fingerprint="x")
        result = build_vector_map()
        assert len(result["points"]) == 6
        assert os.path.exists(tmp_path / "out" / "vector_map.json")
        # Mismatched cache must not be used.
        np.savez(tmp_path / "cache" / "embeddings.pkl.npz", embeddings=np.zeros((3, 8), dtype=np.float32), fingerprint="x")
        assert build_vector_map()["points"] == []
    finally:
        set_runtime_cache_dir(None)
