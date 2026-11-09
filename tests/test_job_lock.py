"""Lock 3: one heavy job at a time, across processes.

Checked alone (the lock object, held by this process or by another one),
then through the two heavy tools: refused at once, nothing started."""
import pytest

from android_test_mcp.errors import Busy
from android_test_mcp.joblock import HeavyJobLock
from android_test_mcp.policy import Policy
from android_test_mcp.server import build_server

from fakes import DEMO
from helpers import FAST, call, held_by_another_process, text

pytestmark = pytest.mark.anyio


def test_a_second_holder_in_the_same_process_is_refused(tmp_path):
    lock = HeavyJobLock(tmp_path)
    with lock.hold("first"):
        with pytest.raises(Busy, match="first"):
            with HeavyJobLock(tmp_path).hold("second"):
                pass


def test_a_holder_in_another_process_is_refused_and_named(tmp_path):
    with held_by_another_process(tmp_path):
        with pytest.raises(Busy) as refusal:
            with HeavyJobLock(tmp_path).hold("mine"):
                pass
    assert "flutter test from another session" in str(refusal.value)


def test_the_lock_is_released_when_the_job_ends(tmp_path):
    with HeavyJobLock(tmp_path).hold("first"):
        pass
    with HeavyJobLock(tmp_path).hold("second"):
        pass


def test_the_lock_is_released_when_the_job_fails(tmp_path):
    with pytest.raises(RuntimeError):
        with HeavyJobLock(tmp_path).hold("crashing"):
            raise RuntimeError("boom")
    with HeavyJobLock(tmp_path).hold("next"):
        pass


def test_the_lock_is_released_when_the_holding_process_ends(tmp_path):
    """No stale lock file: the operating system frees the lock of a dead process."""
    with held_by_another_process(tmp_path):
        pass
    with HeavyJobLock(tmp_path).hold("after"):
        pass


# --- through the server

async def test_install_is_refused_while_another_job_runs(make_server, world, evidence_dir, apk):
    with held_by_another_process(evidence_dir):
        result = await call(make_server(), "install_apk",
                            {"serial": "emulator-5554", "apk_path": str(apk), "package": DEMO})
    assert result.is_error
    assert "Another heavy job is running" in text(result)
    assert world.commands("install") == []


async def test_flutter_test_is_refused_while_another_job_runs(make_server, world, evidence_dir, project):
    with held_by_another_process(evidence_dir):
        result = await call(make_server(), "run_flutter_test",
                            {"serial": "emulator-5554", "project_dir": str(project), "test_path": "integration_test"})
    assert result.is_error
    assert "Another heavy job is running" in text(result)
    assert world.commands("flutter") == []


async def test_servers_with_different_evidence_share_the_lock_dir(world, project, tmp_path, apk):
    """Two sessions keep their evidence apart, but share one machine."""
    shared = tmp_path / "machine-wide-lock"
    server = build_server(Policy.create([DEMO], [project]), tmp_path / "session-b", runner=world,
                          timing=FAST, lock_dir=shared)
    with held_by_another_process(shared):
        result = await call(server, "install_apk", {"serial": "emulator-5554", "apk_path": str(apk), "package": DEMO})
    assert result.is_error
    assert world.commands("install") == []


async def test_light_tools_are_not_blocked_by_a_heavy_job(make_server, evidence_dir):
    with held_by_another_process(evidence_dir):
        result = await call(make_server(), "ui_elements", {"serial": "emulator-5554"})
    assert not result.is_error


async def test_the_server_releases_the_lock_after_a_job(make_server, world, apk):
    server = make_server()
    arguments = {"serial": "emulator-5554", "apk_path": str(apk), "package": DEMO}
    first = await call(server, "install_apk", arguments)
    second = await call(server, "install_apk", arguments)
    assert not first.is_error and not second.is_error
    assert len(world.commands("install")) == 2
