"""set_airplane_mode: the command is not the proof, the setting is."""
import pytest
from mcp import Client

from helpers import PHYSICAL, call, text

pytestmark = pytest.mark.anyio

EMU = {"serial": "emulator-5554"}


async def test_enabling_is_verified_and_the_network_is_gone(make_server, world):
    result = await call(make_server(), "set_airplane_mode", {**EMU, "enabled": True})
    assert result.structured_content == {"airplane_mode": True, "changed": True, "network_seen": False}
    assert ["adb", "-s", "emulator-5554", "shell", "cmd", "connectivity", "airplane-mode", "enable"] in world.calls


async def test_disabling_brings_the_network_back(make_server, world):
    world.devices["emulator-5554"].airplane = True
    result = await call(make_server(), "set_airplane_mode", {**EMU, "enabled": False})
    assert result.structured_content == {"airplane_mode": False, "changed": True, "network_seen": True}
    assert world.commands("disable")


async def test_asking_for_the_current_state_changes_nothing(make_server, world):
    world.devices["emulator-5554"].airplane = True
    result = await call(make_server(), "set_airplane_mode", {**EMU, "enabled": True})
    assert result.structured_content["changed"] is False
    assert result.structured_content["airplane_mode"] is True


async def test_a_setting_that_never_follows_is_an_error(make_server, world):
    world.devices["emulator-5554"].airplane_follows = False
    result = await call(make_server(), "set_airplane_mode", {**EMU, "enabled": True})
    assert result.is_error
    assert "airplane_mode_on" in text(result) and "still 0" in text(result)


async def test_an_unreadable_connectivity_dump_gives_null(make_server, world):
    world.devices["emulator-5554"].connectivity = "Can't find service: connectivity\n"
    result = await call(make_server(), "set_airplane_mode", {**EMU, "enabled": True})
    assert not result.is_error
    assert result.structured_content["network_seen"] is None


async def test_a_physical_device_is_left_alone(make_server, world):
    result = await call(make_server(), "set_airplane_mode", {"serial": PHYSICAL, "enabled": True})
    assert result.is_error
    assert world.commands("airplane-mode") == []
    assert world.devices[PHYSICAL].airplane is False


async def test_airplane_mode_is_an_idempotent_action(make_server):
    async with Client(make_server()) as client:
        tool = {t.name: t for t in (await client.list_tools()).tools}["set_airplane_mode"]
    assert not tool.annotations.read_only_hint and tool.annotations.idempotent_hint
