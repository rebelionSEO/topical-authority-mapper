import numpy as np
import pandas as pd
import pytest

from src.config import SiteConfig, save_site_config, set_runtime_cache_dir
from src.embedding import compute_embeddings
from src.output import detect_cannibalization, export_all
from src.enhancements import compute_similarity_scores, detect_cluster_merges, score_brand_voice, _similarity_action
from src.brand_voice import _parse_brand_text, save_brand_profile, load_or_create_brand_profile


@pytest.fixture
def workspace(tmp_path):
    set_runtime_cache_dir(str(tmp_path / "cache"))
    save_site_config(SiteConfig(name="Test", domain="example.com", output_dir=str(tmp_path)))
    yield tmp_path
    set_runtime_cache_dir(None)


class Encoder:
    def __init__(self):
        self.calls = 0

    def encode(self, texts, **kwargs):
        self.calls += 1
        return np.array([[len(text), ord(text[0])] for text in texts], dtype=np.float32)


def test_cache_tracks_text_order_model_and_recovers_corruption(tmp_path):
    path = str(tmp_path / "embeddings.pkl")
    encoder = Encoder()
    def encode(texts, identity="test-v1"):
        return compute_embeddings(texts, model=encoder, cache_path=path, model_id=identity)
    original = encode(["a", "bb"])
    np.testing.assert_array_equal(encode(["a", "bb"]), original)
    assert encoder.calls == 1
    np.testing.assert_array_equal(encode(["bb", "a"]), original[::-1])
    encode(["cc", "a"])
    encode(["cc", "a"], "test-v2")
    assert encoder.calls == 4
    (tmp_path / "embeddings.pkl.npz").write_bytes(b"invalid")
    encode(["cc", "a"], "test-v2")
    assert encoder.calls == 5


def test_legacy_pickle_is_not_loaded(tmp_path):
    path = tmp_path / "embeddings.pkl"
    path.write_bytes(b"not a pickle")
    encoder = Encoder()
    compute_embeddings(["a"], model=encoder, cache_path=str(path), model_id="test")
    assert encoder.calls == 1


def test_noise_is_not_cannibalization_and_no_destructive_advice():
    mapping = pd.DataFrame({"url": list("abcdefghi"), "main_cluster": [-1]*3 + [0]*6})
    clusters = pd.DataFrame({"cluster_id": [0], "cluster_name": ["CRM"]})
    result = detect_cannibalization(mapping, clusters)
    assert result.cluster_id.tolist() == [0]
    assert "not confirmed" in result.iloc[0].recommendation
    assert "consolidate aggressively" not in result.iloc[0].recommendation


def test_empty_outputs_replace_previous_run(workspace):
    (workspace / "skipped_urls.csv").write_text("url,reason\nold,stale\n")
    (workspace / "recommendations.csv").write_text("cluster_id\n99\n")
    clusters = pd.DataFrame(columns=["cluster_id", "cluster_name", "keywords"])
    mapping = pd.DataFrame(columns=["url", "main_cluster"])
    export_all(clusters, mapping, detect_cannibalization(mapping, clusters), [])
    assert pd.read_csv(workspace / "skipped_urls.csv").empty
    assert pd.read_csv(workspace / "recommendations.csv").empty
    chunks = pd.DataFrame({"url": ["a"], "cluster_id": [-1], "chunk_text": ["text"]})
    compute_similarity_scores(chunks, np.array([[1., 0.]]))
    detect_cluster_merges(clusters, chunks, np.array([[1., 0.]]))
    score_brand_voice(chunks)
    for name in ["similarity_scores", "cluster_merge_suggestions", "brand_voice_scores"]:
        assert pd.read_csv(workspace / f"{name}.csv").empty


def test_brand_profiles_are_isolated(workspace):
    save_brand_profile({"brand_name": "first"})
    assert load_or_create_brand_profile()["brand_name"] == "first"
    set_runtime_cache_dir(str(workspace / "second"))
    assert load_or_create_brand_profile()["brand_name"] == ""
    first = _parse_brand_text("Tone\nprofessional")
    second = _parse_brand_text("Tone\nfriendly")
    assert "professional" in first["tone"]
    assert "professional" not in second["tone"]


def test_different_intents_are_not_automatically_critical():
    assert _similarity_action(0.2, "blog", "service").startswith("OK")
    assert _similarity_action(0.95, "blog", "service").startswith("REVIEW")


def test_cluster_names_do_not_use_numeric_code_examples():
    from src.clustering import extract_cluster_keywords
    chunks = pd.DataFrame({"cluster_id": [0], "chunk_text": ["13 21 34 " * 50 + "Python programming functions and lists"]})
    result = extract_cluster_keywords(chunks)
    assert not any(char.isdigit() for char in result.iloc[0].cluster_name)


@pytest.mark.parametrize("count", [1, 2, 3, 4, 6])
def test_small_sites_cluster_without_failure(count):
    from src.clustering import reduce_dimensions, cluster_embeddings
    vectors = np.random.default_rng(42).normal(size=(count, 12)).astype(np.float32)
    labels = cluster_embeddings(reduce_dimensions(vectors))
    assert len(labels) == count


def test_pipeline_generates_current_analysis_and_dashboard(workspace, monkeypatch):
    from src import main, enhancements, report, vector_map
    monkeypatch.delenv("TAM_LLM_PROVIDER", raising=False)
    urls = [f"https://example.com/article-{i}" for i in range(4)]
    source = workspace / "input.txt"
    source.write_text("\n".join(urls))
    chunks = pd.DataFrame({"url": urls, "chunk_id": [0]*4,
        "chunk_text": ["Customer relationship automation workflow guide and sales reporting analytics " * 30]*4})
    monkeypatch.setattr(main, "ingest_urls", lambda _: (chunks.copy(), []))
    monkeypatch.setattr(main, "compute_embeddings", lambda texts, cache_path: compute_embeddings(
        texts, model=Encoder(), cache_path=cache_path, model_id="fixture"))
    monkeypatch.setattr(main, "reduce_dimensions", lambda values: values)
    monkeypatch.setattr(main, "cluster_embeddings", lambda values: np.zeros(len(values), dtype=int))
    def freshness(**kwargs):
        from pathlib import Path
        from src.config import output_dir
        pd.DataFrame(columns=["url", "lastmod", "age_days", "freshness"]).to_csv(
            Path(output_dir()) / "content_freshness.csv", index=False)
    monkeypatch.setattr(enhancements, "score_content_freshness", freshness)
    monkeypatch.setattr(report, "generate_pdf", lambda **kwargs: "PDF renderer excluded from offline test")
    monkeypatch.setattr(vector_map, "build_vector_map", lambda **kwargs: None)
    result = main.run(input_file=str(source), output_dir_arg=str(workspace), skip_history=True)
    from pathlib import Path
    workspace = Path(result["output_dir"])
    for filename in ["dashboard.html", "exec_summary.html", "site_health.json", "qa_report.json",
                     "potential_topic_overlap.csv", "similarity_scores.csv", "cluster_merge_suggestions.csv",
                     "brand_voice_scores.csv"]:
        assert (workspace / filename).exists(), filename
    assert len(pd.read_csv(workspace / "similarity_scores.csv")) == 6
    assert "Potential overlap" in (workspace / "dashboard.html").read_text()
    from src.retrieval import RetrievalIndex
    index = RetrievalIndex.from_cache()
    assert index is not None and index.n_urls == 4
