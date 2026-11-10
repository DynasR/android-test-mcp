"""Helpers shared by the test files."""
import subprocess
import sys
from contextlib import contextmanager

from mcp import Client

from android_test_mcp.server import Timing

# No waiting in tests: polls are immediate, timeouts tiny.
FAST = Timing(adb_timeout_s=5, install_timeout_s=5, launch_timeout_s=0.2, poll_interval_s=0.01,
              tap_settle_s=0, tap_change_timeout_s=0, dump_attempts=3, airplane_timeout_s=0.2)

PHYSICAL = "R58M41ABCDE"


async def call(server, tool, arguments=None):
    async with Client(server) as client:
        return await client.call_tool(tool, arguments or {})


def text(result) -> str:
    return " ".join(getattr(part, "text", "") for part in result.content)


HOLDER = """
import sys
from pathlib import Path
from android_test_mcp.joblock import HeavyJobLock
with HeavyJobLock(Path(sys.argv[1])).hold("flutter test from another session"):
    print("held", flush=True)
    sys.stdin.readline()
"""


@contextmanager
def held_by_another_process(directory):
    """A second process, like a second agent session, holding the heavy lock."""
    holder = subprocess.Popen([sys.executable, "-c", HOLDER, str(directory)], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        yield
    finally:
        holder.stdin.close()
        holder.wait(timeout=30)
