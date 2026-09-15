import hashlib
import json
from pathlib import Path

import pytest

from src.config import cache_dir, set_runtime_cache_dir
from src.execution import isolated_audit, stage, note_stage


@pytest.fixture
def root(tmp_path):
    set_runtime_cache_dir(str(tmp_path / "cache"))
    yield tmp_path
    set_runtime_cache_dir(None)


@isolated_audit
def fixture_audit(site_domain, output_dir_arg, fail=False, competitor=False):
    out = Path(output_dir_arg)
    (out / "current.csv").write_text("url\ncurrent\n")
    if competitor:
        (out / "competitor_gap_old.csv").write_text("keyword\nold\n")
    if fail:
        def broken():
            raise RuntimeError("Controlled failure")
        stage("crawl", broken)
    stage("analysis", lambda: 1)
    note_stage("competitors", "skipped", reason="Not requested")


def test_two_audits_never_mix_artifacts_and_preserve_previous(root):
    first = fixture_audit("example.com", str(root / "out"), competitor=True)
    second = fixture_audit("example.com", str(root / "out"))
    assert first["output_dir"] != second["output_dir"]
    assert (Path(first["output_dir"]) / "competitor_gap_old.csv").exists()
    assert not (Path(second["output_dir"]) / "competitor_gap_old.csv").exists()
    manifest = json.loads((Path(second["output_dir"]) / "run_manifest.json").read_text())
    assert manifest["status"] == "completed"
    assert manifest["stages"]["competitors"]["status"] == "skipped"
    for artifact in manifest["artifacts"]:
        content = (Path(second["output_dir"]) / artifact["path"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == artifact["sha256"]
    assert "Status: completed" in (Path(second["output_dir"]) / "run_status.html").read_text()


def test_failed_run_has_manifest_and_does_not_expose_previous_report(root):
    fixture_audit("example.com", str(root / "out"), competitor=True)
    with pytest.raises(RuntimeError, match="Controlled"):
        fixture_audit("example.com", str(root / "out"), fail=True)
    pointer = json.loads((root / "cache" / "active_run.json").read_text())
    out = Path(pointer["output_dir"])
    manifest = json.loads((out / "run_manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["stages"]["crawl"]["status"] == "failed"
    assert "Controlled failure" in manifest["error"]
    assert not (out / "competitor_gap_old.csv").exists()


def test_site_caches_do_not_share_brand_profiles(root):
    @isolated_audit
    def branded(site_domain, output_dir_arg):
        path = Path(cache_dir()) / "brand_profile.json"
        if site_domain == "first.example":
            path.write_text('{"brand_name": "First"}')
        else:
            assert not path.exists()
    branded("first.example", str(root / "out"))
    branded("second.example", str(root / "out"))
