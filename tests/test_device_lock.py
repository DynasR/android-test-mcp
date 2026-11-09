"""Lock 1: only emulators, unless a physical device was named at start.

Checked alone first (the verdict function), then through every tool that
touches a device: a refused device must see no command other than the reads
needed to identify it."""
import pytest

from android_test_mcp.policy import Policy

from fakes import DEMO, FakeDevice
from helpers import PHYSICAL, call, text

pytestmark = pytest.mark.anyio

IDENTIFY = {"devices", "getprop"}


def verdict(serial, reports_emulator, allowed_devices=()):
    return Policy.create(devices=allowed_devices).device_verdict(serial, reports_emulator)


def test_an_emulator_is_allowed_by_default():
    assert verdict("emulator-5554", True) == (True, "emulator")


def test_a_physical_device_is_refused_by_default():
    allowed, reason = verdict(PHYSICAL, False)
    assert not allowed
    assert "--allow-device" in reason


def test_a_physical_device_named_at_start_is_allowed():
    assert verdict(PHYSICAL, False, [PHYSICAL])[0]


def test_naming_one_physical_device_does_not_allow_another():
    assert not verdict("ZY22FFF", False, [PHYSICAL])[0]


def test_an_emulator_serial_must_be_confirmed_by_the_device():
    allowed, reason = verdict("emulator-5554", False)
    assert not allowed
    assert "qemu" in reason


@pytest.mark.parametrize("serial", ["emulator-5554x", "my-emulator-5554", "emulator-", "192.168.1.20:5555"])
def test_only_the_exact_emulator_serial_form_counts(serial):
    assert not verdict(serial, True)[0]


# --- through the server

DEVICE_CALLS = [
    ("launch_app", {"package": DEMO}),
    ("screenshot", {}),
    ("ui_elements", {}),
    ("tap", {"label": "Backups"}),
]


@pytest.mark.parametrize("tool, arguments", DEVICE_CALLS)
async def test_every_device_tool_refuses_a_physical_device(make_server, world, tool, arguments):
    result = await call(make_server(), tool, {"serial": PHYSICAL, **arguments})
    assert result.is_error
    assert "not allowed" in text(result)
    assert all(IDENTIFY & set(argv) for argv in world.calls)
    assert world.devices[PHYSICAL].taps == []


async def test_install_refuses_a_physical_device(make_server, world, apk):
    result = await call(make_server(), "install_apk", {"serial": PHYSICAL, "apk_path": str(apk), "package": DEMO})
    assert result.is_error
    assert world.commands("install") == []


async def test_flutter_test_refuses_a_physical_device(make_server, world, project):
    result = await call(make_server(), "run_flutter_test",
                        {"serial": PHYSICAL, "project_dir": str(project), "test_path": "integration_test"})
    assert result.is_error
    assert world.commands("flutter") == []


async def test_a_spoofed_emulator_serial_is_refused(make_server, world):
    """A serial that looks like an emulator, on a device that says it is not one."""
    world.devices["emulator-5556"] = FakeDevice(qemu=False)
    result = await call(make_server(), "tap", {"serial": "emulator-5556", "label": "Backups"})
    assert result.is_error
    assert "qemu" in text(result)
    assert world.devices["emulator-5556"].taps == []


async def test_allow_device_opens_that_device(make_server, world):
    result = await call(make_server(devices=[PHYSICAL]), "tap", {"serial": PHYSICAL, "label": "Backups"})
    assert not result.is_error, text(result)
    assert world.devices[PHYSICAL].taps == [(540, 672)]


async def test_a_device_that_is_not_attached_is_refused(make_server):
    result = await call(make_server(), "screenshot", {"serial": "emulator-5580"})
    assert result.is_error
    assert "list_devices" in text(result)


async def test_an_unauthorized_device_is_refused(make_server, world):
    world.devices["emulator-5554"].state = "unauthorized"
    result = await call(make_server(), "screenshot", {"serial": "emulator-5554"})
    assert result.is_error
    assert "unauthorized" in text(result)


async def test_list_devices_says_which_are_allowed(make_server):
    result = await call(make_server(), "list_devices")
    devices = {d["serial"]: d for d in result.structured_content["result"]}
    assert devices["emulator-5554"]["allowed"] and devices["emulator-5554"]["is_emulator"]
    assert devices["emulator-5554"]["screen_size"] == "1080x2400"
    assert not devices[PHYSICAL]["allowed"] and not devices[PHYSICAL]["is_emulator"]
    assert devices[PHYSICAL]["model"] == "SM-G991B"
