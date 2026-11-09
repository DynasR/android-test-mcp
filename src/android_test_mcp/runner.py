"""The single door to the outside world.

Every adb and flutter call goes through one function with this signature:

    runner(argv: Sequence[str], timeout: float, cwd: Path | None) -> RunResult

Tests replace it with a fake that answers canned outputs, so the whole server
is exercised without a device. The real one below never uses a shell: argv is
a list, passed as is to the operating system.
"""
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .errors import DeviceError


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: bytes
    stderr: bytes

    @property
    def text(self) -> str:
        """stdout then stderr, decoded leniently: adb mixes both."""
        return (self.stdout + b"\n" + self.stderr).decode("utf-8", errors="replace")


class RunTimeout(DeviceError):
    """The command outlived its timeout and was killed, with its children."""

    def __init__(self, argv: Sequence[str], timeout: float, stdout: bytes = b"", stderr: bytes = b""):
        super().__init__(f"{argv[0]} did not finish within {timeout:g} s and was stopped.")
        self.stdout, self.stderr = stdout, stderr


Runner = Callable[..., RunResult]

# cmd.exe re-parses the command line of a .bat or .cmd file, and these
# characters would let an argument become a second command. `flutter` is a
# .bat on Windows, so its arguments are checked before the call.
_CMD_METACHARACTERS = set('&|<>^%!"\r\n')


def subprocess_runner(argv: Sequence[str], timeout: float, cwd: Path | None = None) -> RunResult:
    argv = list(argv)
    executable = shutil.which(argv[0])
    if executable is None:
        raise DeviceError(f"{argv[0]} is not on PATH. Install it, or add it to PATH, then restart the server.")
    if executable.lower().endswith((".bat", ".cmd")):
        unsafe = [arg for arg in argv[1:] if _CMD_METACHARACTERS & set(arg)]
        if unsafe:
            raise DeviceError(f"Refusing to pass {unsafe[0]!r} to a batch file: it contains a shell metacharacter.")
    argv[0] = executable
    extra = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32"
             else {"start_new_session": True})
    process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, shell=False, **extra)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        stdout, stderr = process.communicate()
        raise RunTimeout(argv, timeout, stdout, stderr) from None
    return RunResult(process.returncode, stdout, stderr)


def _kill_tree(process: subprocess.Popen) -> None:
    """Killing only the direct child is not enough: `flutter` starts dart,
    gradle and adb, which keep the output pipes open and the call hanging."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.kill()
