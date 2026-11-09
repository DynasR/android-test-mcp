"""The real runner, on harmless child processes (Python itself)."""
import sys
import time

import pytest

from android_test_mcp.errors import DeviceError
from android_test_mcp.runner import RunTimeout, subprocess_runner


def test_output_comes_back_as_bytes_untouched():
    result = subprocess_runner([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\x89PNG\\r\\n')"],
                               timeout=30)
    assert result.returncode == 0
    assert result.stdout == b"\x89PNG\r\n"


def test_arguments_are_not_interpreted_by_a_shell(tmp_path):
    marker = tmp_path / "created"
    argument = f"x; echo hacked > {marker} & echo hacked > {marker}"
    result = subprocess_runner([sys.executable, "-c", "import sys; print(sys.argv[1])", argument], timeout=30)
    assert result.stdout.decode().strip() == argument
    assert not marker.exists()


def test_a_command_that_outlives_its_timeout_is_stopped():
    started = time.monotonic()
    with pytest.raises(RunTimeout):
        subprocess_runner([sys.executable, "-c", "print('started', flush=True); import time; time.sleep(60)"],
                          timeout=1)
    assert time.monotonic() - started < 20


GRANDCHILD = (
    "import subprocess, sys\n"
    "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(40)'])\n"
    "print('started', flush=True)\n"
    "import time; time.sleep(40)\n"
)


def test_children_holding_the_output_are_stopped_too():
    """flutter starts dart and gradle, which inherit the output pipes: killing
    only the direct child would leave the call hanging until they exit."""
    started = time.monotonic()
    with pytest.raises(RunTimeout):
        subprocess_runner([sys.executable, "-c", GRANDCHILD], timeout=2)
    assert time.monotonic() - started < 20


def test_a_missing_program_is_a_clear_error():
    with pytest.raises(DeviceError, match="not on PATH"):
        subprocess_runner(["android-test-mcp-no-such-program"], timeout=5)


@pytest.mark.skipif(sys.platform != "win32", reason="batch files are a Windows concern")
def test_a_batch_file_never_receives_a_shell_metacharacter(tmp_path):
    batch = tmp_path / "flutter.bat"
    batch.write_text("@echo %*\r\n")
    with pytest.raises(DeviceError, match="metacharacter"):
        subprocess_runner([str(batch), "test", "a&calc.dart"], timeout=30)
    assert subprocess_runner([str(batch), "test", "app_test.dart"], timeout=30).stdout.strip() == b"test app_test.dart"
