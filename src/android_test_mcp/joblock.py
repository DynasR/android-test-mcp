"""Lock 3: one heavy job at a time, across processes.

Installing an APK and running a Flutter test suite each load the machine:
gradle, the dart compiler, the emulator. Two of them at once, from two agents
or two sessions, has been enough to bring a development PC down. So a heavy
job takes an exclusive lock first, and a second one is refused, never queued:
the agent is told who holds the lock and since when.

The lock is an operating-system lock on a file (msvcrt on Windows, flock
elsewhere), not the mere presence of a file: if the process holding it dies,
the system releases it, and no stale lock file can block the next run.
"""
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from .errors import Busy

if sys.platform == "win32":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


class HeavyJobLock:
    LOCK_NAME = ".heavy-job.lock"
    HOLDER_NAME = ".heavy-job.json"

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    @contextmanager
    def hold(self, job: str):
        """Hold the lock for the duration of the block, or raise Busy at once."""
        self.directory.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.directory / self.LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if not _try_lock(fd):
                raise Busy(f"Another heavy job is running ({self._holder()}). Only one install or "
                           "test run at a time: wait for it to finish, then call again.")
            try:
                # The holder is written next to the lock, not in it: on Windows
                # a locked byte cannot be read by the process that is refused.
                (self.directory / self.HOLDER_NAME).write_text(json.dumps(
                    {"job": job, "pid": os.getpid(), "since": time.strftime("%Y-%m-%d %H:%M:%S")}))
                yield
            finally:
                _unlock(fd)
        finally:
            os.close(fd)

    def _holder(self) -> str:
        try:
            holder = json.loads((self.directory / self.HOLDER_NAME).read_text())
            return f"{holder['job']}, process {holder['pid']}, since {holder['since']}"
        except (OSError, ValueError, KeyError):
            return "holder unknown"
