"""restart_app: force-stop, then exactly the launch path (focus, crash diagnosis)."""
import pytest

from fakes import DEMO, DEMO_ABI_CRASH
from helpers import PHYSICAL, call, text

pytestmark = pytest.mark.anyio

RESTART = {"serial": "emulator-5554", "package": DEMO}
LAUNCHER = ("com.android.launcher3", "com.android.launcher3")


def verbs(world):
    return [argv[4] for argv in world.calls if argv[3:4] == ["shell"] and argv[4] in ("am", "monkey")]


async def test_restart_stops_then_launches_and_verifies_the_focus(make_server, world):
    world.devices["emulator-5554"].running.add(DEMO)
    result = await call(make_server(), "restart_app", RESTART)
    assert not result.is_error, text(result)
    assert result.structured_content["focused"] is True
    assert world.devices["emulator-5554"].force_stops == [DEMO]
    assert verbs(world) == ["am", "monkey"]


async def test_launch_app_does_not_force_stop(make_server, world):
    await call(make_server(), "launch_app", RESTART)
    assert world.commands("force-stop") == []


async def test_a_package_off_the_list_is_not_stopped(make_server, world):
    result = await call(make_server(), "restart_app", {**RESTART, "package": "com.android.settings"})
    assert result.is_error
    assert "not allowed" in text(result)
    assert world.commands("force-stop") == []


async def test_a_physical_device_is_not_touched(make_server, world):
    result = await call(make_server(), "restart_app", {**RESTART, "serial": PHYSICAL})
    assert result.is_error
    assert world.commands("force-stop") == [] and world.commands("monkey") == []


async def test_an_app_that_is_not_installed_is_not_stopped(make_server, world):
    world.devices["emulator-5554"].packages = {}
    result = await call(make_server(), "restart_app", RESTART)
    assert result.is_error
    assert "install_apk" in text(result)
    assert world.commands("force-stop") == []


async def test_a_process_that_survives_force_stop_is_an_error(make_server, world):
    device = world.devices["emulator-5554"]
    device.running.add(DEMO)
    device.survives_force_stop = True
    result = await call(make_server(), "restart_app", RESTART)
    assert result.is_error
    assert "still running" in text(result)
    assert world.commands("monkey") == []


async def test_a_crash_after_restart_is_diagnosed_like_a_launch(make_server, world):
    device = world.devices["emulator-5554"]
    device.focus_after_launch, device.dies_at_launch, device.crash_buffer = LAUNCHER, True, DEMO_ABI_CRASH
    result = await call(make_server(), "restart_app", RESTART)
    assert result.is_error
    assert f"{DEMO} crashed at launch: java.lang.UnsatisfiedLinkError" in text(result)
    assert "no native code for this device's ABI" in text(result)
