from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from cbrun import init_queue


@pytest.fixture(autouse=True)
def slot_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(init_queue, "INIT_SLOT_DIR", tmp_path / "slots")
    monkeypatch.setattr(init_queue, "POLL_SEC", 0.05)
    return tmp_path / "slots"


def test_at_most_n_trials_hold_a_slot_and_the_rest_wait_their_turn() -> None:
    lock = threading.Lock()
    holding = 0
    peak = 0
    done = 0

    def trial(i: int) -> None:
        nonlocal holding, peak, done
        slot = init_queue.InitSlot(2, label=f"t{i}")
        slot.acquire()
        with lock:
            holding += 1
            peak = max(peak, holding)
        time.sleep(0.2)
        with lock:
            holding -= 1
            done += 1
        slot.release()

    threads = [threading.Thread(target=trial, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert done == 5
    assert peak == 2


def test_release_is_idempotent_and_frees_the_slot() -> None:
    first = init_queue.InitSlot(1, label="a")
    first.acquire()
    first.release()
    first.release()
    second = init_queue.InitSlot(1, label="b")
    second.acquire()
    second.release()


def test_rejects_fewer_than_one_slot() -> None:
    with pytest.raises(ValueError):
        init_queue.InitSlot(0, label="x")


def test_trial_that_fails_during_setup_gives_its_slot_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cbrun import run_case

    class Stop(Exception):
        pass

    def fake_ensure(case_id, **kwargs):
        raise Stop

    monkeypatch.setattr(run_case, "ensure_agent_image", fake_ensure)
    monkeypatch.setattr(run_case, "require_denylist", lambda case_dir: None)
    case_dir = Path(__file__).resolve().parents[2] / "cases" / "case001"
    with pytest.raises(Stop):
        run_case.run_trial(
            case_dir, backend="codex", model="m", out_dir=tmp_path / "out",
            cache_root=tmp_path / "cache", allow_leakage=True, init_slots=1,
        )
    other = init_queue.InitSlot(1, label="next")
    acquired = threading.Event()

    def take() -> None:
        other.acquire()
        acquired.set()

    threading.Thread(target=take, daemon=True).start()
    assert acquired.wait(timeout=2)
    other.release()


def test_jobs_run_trials_side_by_side_and_keep_matrix_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from cbrun import cli
    from cbrun.results import TrialResult

    lock = threading.Lock()
    running = 0
    peak = 0
    seen_slots: list[int] = []

    def fake_trial(case_dir, *, backend, model, init_slots, **_kwargs):
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
            seen_slots.append(init_slots)
        # Later cases finish first, so completion order differs from case order.
        time.sleep(0.4 - 0.05 * int(case_dir.name[-1]))
        with lock:
            running -= 1
        return TrialResult(case_id=case_dir.name, backend=backend, model=model,
                           reward=1.0, terminal_status="completed")

    monkeypatch.setattr(cli, "run_trial", fake_trial)
    monkeypatch.setenv("CBRUN_CODEX_VERSION", "0.0.1")
    cases = ["case001", "case002", "case003", "case004", "case005"]
    argv = [arg for case in cases for arg in ("--case", case)]
    out = tmp_path / "out"
    rc = cli.main(argv + ["--backend", "codex", "--model", "m", "--jobs", "3",
                          "--init-slots", "2", "--out", str(out)])
    assert rc == 0
    assert peak == 3
    assert seen_slots == [2] * 5
    trials = json.loads((out / "summary.json").read_text())["trials"]
    assert [t["case_id"] for t in trials] == cases
