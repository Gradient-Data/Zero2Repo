"""Host-wide queue for the setup phase of trials run side by side.

A trial's setup (building its images, starting its container, installing the
agent CLI) downloads a lot. When many trials start together they all download
at once and each one slows to a crawl. Each trial therefore takes one of a fixed
number of host-wide slots for its setup and gives it back when the agent is
about to start, so at most that many trials set up at a time and the rest wait
in line.

A slot is an ``flock`` on one file under ``INIT_SLOT_DIR``. The kernel drops the
lock when its process dies, so a crashed trial never holds a slot. Every cbrun
process on the host shares the directory; processes started with different slot
counts share the slots they have in common.
"""

from __future__ import annotations

import fcntl
import sys
import tempfile
import time
from pathlib import Path
from typing import IO

INIT_SLOT_DIR = Path(tempfile.gettempdir()) / "cbrun-init-slots"
DEFAULT_INIT_SLOTS = 3
POLL_SEC = 2.0


class InitSlot:
    """One of *slots* host-wide places for a trial's setup phase."""

    def __init__(self, slots: int, *, label: str) -> None:
        if slots < 1:
            raise ValueError(f"init slots must be at least 1, got {slots}")
        self.slots = slots
        self.label = label
        self._handle: IO[str] | None = None

    def acquire(self) -> None:
        """Block until a slot is free and take it."""
        INIT_SLOT_DIR.mkdir(parents=True, exist_ok=True)
        waited = False
        start = time.monotonic()
        while True:
            for index in range(self.slots):
                handle = open(INIT_SLOT_DIR / f"slot-{index}.lock", "w")
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    handle.close()
                    continue
                self._handle = handle
                if waited:
                    print(
                        f"[cbrun] {self.label}: init slot {index} taken after "
                        f"{time.monotonic() - start:.0f}s",
                        file=sys.stderr,
                    )
                return
            if not waited:
                print(
                    f"[cbrun] {self.label}: all {self.slots} init slots busy; waiting",
                    file=sys.stderr,
                )
                waited = True
            time.sleep(POLL_SEC)

    def release(self) -> None:
        """Give the slot back. Releasing a slot not held does nothing."""
        if self._handle is None:
            return
        fcntl.flock(self._handle, fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None
