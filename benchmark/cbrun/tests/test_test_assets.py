"""Hidden-test assets: manifest validation, fetching, staging and rejudge copies."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest

from coding_bench_harbor import test_assets
from coding_bench_harbor.test_assets import TestAsset, TestAssetError

BODY = b"official release bytes\n"
SHA = hashlib.sha256(BODY).hexdigest()


def write_manifest(final: Path, assets: list[dict]) -> None:
    final.mkdir(parents=True, exist_ok=True)
    (final / "test_assets.json").write_text(json.dumps({"assets": assets}), encoding="utf-8")


def asset(path: str = "tests/assets/tool.bin", **over) -> dict:
    item = {"path": path, "url": "https://example.org/tool.bin", "sha256": SHA, "size": len(BODY)}
    item.update(over)
    return item


def fake_fetch(calls: list[str]):
    def fetch(a: TestAsset, target: Path) -> None:
        calls.append(a.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(BODY)

    return fetch


def test_no_manifest_means_no_assets(tmp_path: Path) -> None:
    assert test_assets.load(tmp_path) == []
    assert test_assets.materialize(tmp_path, tmp_path / "out") == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"path": "/abs/tool.bin"},
        {"path": "tests/../../escape"},
        {"url": "http://example.org/tool.bin"},
        {"sha256": "ABC"},
        {"size": 0},
        {"size": True},
    ],
)
def test_invalid_entries_are_rejected(tmp_path: Path, bad: dict) -> None:
    write_manifest(tmp_path, [asset(**bad)])
    with pytest.raises(TestAssetError):
        test_assets.load(tmp_path)


def test_duplicate_path_is_rejected(tmp_path: Path) -> None:
    write_manifest(tmp_path, [asset(), asset()])
    with pytest.raises(TestAssetError, match="twice"):
        test_assets.load(tmp_path)


def test_materialize_places_each_asset(tmp_path: Path) -> None:
    final = tmp_path / "final"
    write_manifest(final, [asset("tests/a.bin"), asset("tests/sub/b.bin")])
    calls: list[str] = []
    assert test_assets.materialize(final, tmp_path / "out", fake_fetch(calls)) == 2
    assert calls == ["tests/a.bin", "tests/sub/b.bin"]
    assert (tmp_path / "out/tests/sub/b.bin").read_bytes() == BODY


def test_committed_copy_at_asset_path_is_an_error(tmp_path: Path) -> None:
    final = tmp_path / "final"
    write_manifest(final, [asset("tests/a.bin")])
    out = tmp_path / "out"
    (out / "tests").mkdir(parents=True)
    (out / "tests/a.bin").write_bytes(b"stale")
    with pytest.raises(TestAssetError, match="already exists"):
        test_assets.materialize(final, out, fake_fetch([]))


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def test_download_verifies_digest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(test_assets.urllib.request, "urlopen", lambda *a, **k: FakeResponse(BODY))
    target = tmp_path / "x/tool.bin"
    test_assets.download(TestAsset("tool.bin", "https://e/x", SHA, len(BODY)), target)
    assert target.read_bytes() == BODY


def test_download_rejects_other_bytes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(test_assets.urllib.request, "urlopen", lambda *a, **k: FakeResponse(b"x" * len(BODY)))
    target = tmp_path / "tool.bin"
    with pytest.raises(TestAssetError, match="sha256"):
        test_assets.download(TestAsset("tool.bin", "https://e/x", SHA, len(BODY)), target)
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_download_rejects_oversized_body(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(test_assets.urllib.request, "urlopen", lambda *a, **k: FakeResponse(BODY + b"more"))
    with pytest.raises(TestAssetError, match="more than"):
        test_assets.download(TestAsset("t", "https://e/x", SHA, len(BODY)), tmp_path / "t")


def test_rejudge_tests_dir_refetches_assets(tmp_path: Path, monkeypatch) -> None:
    from cbrun import rejudge

    tests = tmp_path / "final"
    write_manifest(tests, [asset("tests/a.bin")])
    (tests / "tests").mkdir()
    (tests / "tests/a.bin").write_bytes(b"stale copy")
    (tests / "tests/F01_x.py").write_text("x = 1\n", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(rejudge, "test_asset_fetcher", lambda: fake_fetch(calls))
    staged = rejudge._tests_with_assets(tests, tmp_path / "staged")
    assert calls == ["tests/a.bin"]
    assert (staged / "tests/a.bin").read_bytes() == BODY
    assert (staged / "tests/F01_x.py").is_file()


def test_rejudge_tests_dir_without_assets_is_used_as_is(tmp_path: Path) -> None:
    from cbrun import rejudge

    assert rejudge._tests_with_assets(tmp_path, tmp_path / "staged") == tmp_path


def test_staged_bundle_fetches_only_when_asked(tmp_path: Path) -> None:
    from cbrun.recipe import stage_benchmark_bundle

    case = tmp_path / "case099"
    (case / "public").mkdir(parents=True)
    (case / "public/Full_PRD.md").write_text("p" * 300, encoding="utf-8")
    (case / "public/Interface_Contract.md").write_text("c" * 80, encoding="utf-8")
    final = case / "milestones/final"
    write_manifest(final, [asset("tests/a.bin")])
    (final / "test_manifest.json").write_text("{}", encoding="utf-8")
    with stage_benchmark_bundle(case, final) as bundle:
        assert (bundle / "final/test_assets.json").is_file()
        assert not (bundle / "final/tests/a.bin").exists()
    calls: list[str] = []
    with stage_benchmark_bundle(case, final, fetch_test_assets=fake_fetch(calls)) as bundle:
        assert (bundle / "final/tests/a.bin").read_bytes() == BODY
    assert calls == ["tests/a.bin"]



def test_image_prefix_separates_checkouts(monkeypatch) -> None:
    from cbrun.images import agent_tag, deliverable_tag
    from cbrun.recipe import RecipeLockError, env_recipe_tag

    monkeypatch.delenv("CBRUN_IMAGE_PREFIX", raising=False)
    assert deliverable_tag("case019") == "codingbench-benchmark/case019:deliverable"
    assert env_recipe_tag("case019") == "codingbench-env/case019:recipe-env"
    monkeypatch.setenv("CBRUN_IMAGE_PREFIX", "official-")
    assert deliverable_tag("case019") == "official-codingbench-benchmark/case019:deliverable"
    assert env_recipe_tag("case019") == "official-codingbench-env/case019:recipe-env"
    assert agent_tag("case019").startswith("official-codingbench-benchmark/")
    monkeypatch.setenv("CBRUN_IMAGE_PREFIX", "Bad/Prefix")
    with pytest.raises(RecipeLockError):
        deliverable_tag("case019")


def test_download_retries_transient_errors(tmp_path: Path, monkeypatch) -> None:
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("HTTP Error 504: Gateway Time-out")
        return FakeResponse(BODY)

    monkeypatch.setattr(test_assets.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(test_assets.time, "sleep", lambda s: None)
    test_assets.download(TestAsset("t", "https://e/x", SHA, len(BODY)), tmp_path / "t")
    assert calls["n"] == 3
    assert (tmp_path / "t").read_bytes() == BODY


def test_download_gives_up_with_the_last_error(tmp_path: Path, monkeypatch) -> None:
    def down(*a, **k):
        raise OSError("HTTP Error 504: Gateway Time-out")

    monkeypatch.setattr(test_assets.urllib.request, "urlopen", down)
    monkeypatch.setattr(test_assets.time, "sleep", lambda s: None)
    with pytest.raises(TestAssetError, match="504"):
        test_assets.download(TestAsset("t", "https://e/x", SHA, len(BODY)), tmp_path / "t")
