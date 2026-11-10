"""type_text: lock 2 on the characters, lock 4 on the field, verified after.

`adb shell` joins its arguments into ONE command line run by the device's
shell, so an argv list does not protect typed text: `;`, `&`, `$(...)` would
run on the device. The charset check is tested alone first, then through the
tool: a refused text, or an absent or ambiguous field, types nothing."""
import pytest
from mcp import Client

from android_test_mcp.errors import Refused
from android_test_mcp.policy import MAX_TEXT, check_text

from helpers import PHYSICAL, call, text

pytestmark = pytest.mark.anyio

EMU = {"serial": "emulator-5554"}


def test_the_safe_characters_pass():
    sample = "Hello World 42 a.b,c-d_e@f:g/h+i=j"
    assert check_text(sample) == sample


@pytest.mark.parametrize("bad", [";", "&", "|", "$", "`", "'", '"', "\\", "(", ")", "<", ">", "*", "?",
                                 "!", "#", "~", "%", "{", "[", "\n", "\t"])
def test_shell_and_control_characters_are_refused_by_name(bad):
    with pytest.raises(Refused) as refusal:
        check_text(f"abc{bad}def")
    assert repr(bad) in str(refusal.value)
    assert "device shell" in str(refusal.value)


def test_the_first_bad_character_is_named():
    with pytest.raises(Refused, match=r"';'"):
        check_text("ok;then&more")


def test_non_ascii_is_refused_because_it_cannot_be_typed():
    with pytest.raises(Refused) as refusal:
        check_text("café")
    assert "'é'" in str(refusal.value) and "ASCII" in str(refusal.value)


def test_length_is_capped():
    assert check_text("a" * MAX_TEXT)
    with pytest.raises(Refused, match=str(MAX_TEXT)):
        check_text("a" * (MAX_TEXT + 1))


def test_empty_text_is_refused():
    with pytest.raises(Refused):
        check_text("")


# --- through the server

async def test_typing_into_a_field_found_by_its_hint(make_server, world):
    result = await call(make_server(), "type_text", {**EMU, "text": "night train", "into": "Search songs"})
    answer = result.structured_content
    device = world.devices["emulator-5554"]
    assert device.taps == [(540, 360)]
    assert device.typed == "night train"
    assert answer["into"] == "Search songs" and answer["verified"] is True
    assert answer["keyboard_shown"] is False


async def test_long_text_goes_in_chunks_of_16_with_spaces_encoded(make_server, world):
    """Some IMEs truncate long `input text` strings. A space at a chunk
    boundary must not be split into '%' and 's'."""
    typed = "0123456789abcde f" + "x" * 20 + " end"
    result = await call(make_server(), "type_text", {**EMU, "text": typed})
    device = world.devices["emulator-5554"]
    assert not result.is_error, text(result)
    assert device.typed == typed
    assert all(len(arg.replace("%s", " ")) <= 16 for arg in device.text_arguments)
    assert all(" " not in arg for arg in device.text_arguments)
    assert len(device.text_arguments) == 3
    assert result.structured_content["chunks"] == 3


async def test_without_into_nothing_is_tapped(make_server, world):
    result = await call(make_server(), "type_text", {**EMU, "text": "abc"})
    assert not result.is_error
    assert world.devices["emulator-5554"].taps == []
    assert result.structured_content["into"] is None


async def test_a_hidden_value_is_not_verified_but_not_an_error(make_server, world):
    world.devices["emulator-5554"].echo_typing = False
    result = await call(make_server(), "type_text", {**EMU, "text": "secret1", "into": "Search songs"})
    answer = result.structured_content
    assert not result.is_error
    assert answer["verified"] is False
    assert "not visible" in answer["note"]


async def test_text_already_on_screen_does_not_verify_the_typing(make_server, world):
    """'Songs' is a title on the screen: finding it after typing proves nothing."""
    world.devices["emulator-5554"].echo_typing = False
    result = await call(make_server(), "type_text", {**EMU, "text": "Songs", "into": "Search songs"})
    assert result.structured_content["verified"] is False


async def test_a_refused_text_taps_and_types_nothing(make_server, world):
    result = await call(make_server(), "type_text", {**EMU, "text": "x; reboot", "into": "Search songs"})
    assert result.is_error
    assert "';'" in text(result)
    assert world.commands("text") == [] and world.devices["emulator-5554"].taps == []


async def test_an_absent_field_types_nothing(make_server, world):
    result = await call(make_server(), "type_text", {**EMU, "text": "abc", "into": "Password"})
    assert result.is_error
    assert "No element labelled 'Password'" in text(result)
    assert world.commands("text") == [] and world.devices["emulator-5554"].taps == []


async def test_an_ambiguous_field_types_nothing(make_server, world):
    result = await call(make_server(), "type_text",
                        {**EMU, "text": "abc", "into": "back", "match": "contains"})
    assert result.is_error
    assert "'Backups'" in text(result)
    assert world.commands("text") == [] and world.devices["emulator-5554"].taps == []


async def test_a_physical_device_gets_nothing_typed(make_server, world):
    result = await call(make_server(), "type_text", {"serial": PHYSICAL, "text": "abc"})
    assert result.is_error
    assert world.commands("text") == []


async def test_the_keyboard_state_is_reported(make_server, world):
    world.devices["emulator-5554"].keyboard = True
    result = await call(make_server(), "type_text", {**EMU, "text": "abc", "into": "Search songs"})
    assert result.structured_content["keyboard_shown"] is True


async def test_type_text_is_not_read_only(make_server):
    async with Client(make_server()) as client:
        tool = {t.name: t for t in (await client.list_tools()).tools}["type_text"]
    assert not tool.annotations.read_only_hint and tool.annotations.destructive_hint
