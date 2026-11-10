"""Lock 4: loud taps.

Checked alone on parsed hierarchies (which element, or which error), then
through the tap tool: an absent or ambiguous target sends no tap at all, and
the answer says whether the screen changed."""
import pytest

from android_test_mcp.errors import AmbiguousTarget, TargetNotFound
from android_test_mcp.ui import find_target, parse_hierarchy, summarize

from fakes import HOME, SETTINGS, hierarchy, node
from helpers import call, text

pytestmark = pytest.mark.anyio

home = parse_hierarchy(HOME)


def test_flutter_labels_are_read_from_content_desc():
    assert find_target(home, "Backups").bounds == (48, 600, 1032, 744)


def test_a_text_field_is_found_by_its_hint():
    target = find_target(home, "Search songs")
    assert target.clickable and target.bounds == (48, 300, 1032, 420)


def test_exact_does_not_match_a_longer_label():
    """'Back' must not reach 'Backups'."""
    assert find_target(home, "Back").bounds == (0, 96, 144, 240)


def test_contains_that_matches_two_elements_is_ambiguous():
    with pytest.raises(AmbiguousTarget) as refusal:
        find_target(home, "back", "contains")
    message = str(refusal.value)
    assert "'Back'" in message and "'Backups'" in message and "Nothing was tapped" in message


def test_the_classic_trap_of_a_label_sentence_above_the_button_is_ambiguous():
    """'add a song' is both the empty-state sentence and the button."""
    with pytest.raises(AmbiguousTarget):
        find_target(home, "add a song", "contains")


def test_contains_reaches_a_multi_line_flutter_label():
    assert find_target(home, "Settings", "contains").clickable


def test_exact_needs_the_whole_label():
    with pytest.raises(TargetNotFound):
        find_target(home, "Settings")


def test_an_absent_label_is_an_error():
    with pytest.raises(TargetNotFound, match="ui_elements"):
        find_target(home, "Delete account")


def test_an_element_without_area_is_not_a_target():
    with pytest.raises(TargetNotFound, match="no area"):
        find_target(home, "Offscreen banner")


def test_an_empty_label_matches_nothing():
    with pytest.raises(TargetNotFound):
        find_target(home, "", "contains")


def test_two_nodes_with_the_same_box_are_one_target_and_the_clickable_one_wins():
    screen = parse_hierarchy(hierarchy(
        node(desc="Save", bounds="[10,10][110,60]"),
        node(desc="Save", bounds="[10,10][110,60]", clickable=True),
    ))
    assert find_target(screen, "Save").clickable


def test_the_signature_follows_what_is_visible():
    assert parse_hierarchy(HOME).signature == parse_hierarchy(HOME).signature
    assert parse_hierarchy(HOME).signature != parse_hierarchy(SETTINGS).signature


def test_the_signature_sees_a_change_that_keeps_the_layout():
    """A counter going from 1 to 2 changes no node and no box, only a label."""
    def counter(value):
        return parse_hierarchy(hierarchy(node(desc=f"Songs: {value}", bounds="[0,0][500,100]"))).signature
    assert counter(1) != counter(2)


def test_the_signature_ignores_the_focus():
    """Focus moves without the screen changing; it must not count as a change."""
    focused = HOME.replace('focused="false"', 'focused="true"', 1)
    assert focused != HOME
    assert parse_hierarchy(focused).signature == parse_hierarchy(HOME).signature


def test_summary_lists_labelled_elements_and_counts_the_others():
    summary = summarize(home)
    labels = [element["label"] for element in summary["elements"]]
    assert "Backups" in labels and "Search songs" in labels and "Settings\nTab 2 of 3" in labels
    assert "Offscreen banner" not in labels
    assert summary["unlabelled_clickable"] == 1


# --- through the server

TAP = {"serial": "emulator-5554"}


async def test_an_absent_target_sends_no_tap(make_server, world):
    result = await call(make_server(), "tap", {**TAP, "label": "Delete account"})
    assert result.is_error
    assert "No element labelled 'Delete account'" in text(result)
    assert world.devices["emulator-5554"].taps == []


async def test_an_ambiguous_target_sends_no_tap_and_lists_the_candidates(make_server, world):
    result = await call(make_server(), "tap", {**TAP, "label": "back", "match": "contains"})
    assert result.is_error
    assert "'Backups'" in text(result)
    assert world.devices["emulator-5554"].taps == []


async def test_a_tap_that_opens_a_screen_reports_the_change(make_server, world):
    result = await call(make_server(), "tap", {**TAP, "label": "Settings", "match": "contains"})
    answer = result.structured_content
    assert answer["screen_changed"] is True
    assert answer["at"] == [540, 2316]
    assert world.devices["emulator-5554"].current == "settings"


async def test_a_tap_that_changes_nothing_says_so(make_server, world):
    result = await call(make_server(), "tap", {**TAP, "label": "Backups"})
    answer = result.structured_content
    assert not result.is_error
    assert answer["screen_changed"] is False
    assert "did not change" in answer["note"]
    assert world.devices["emulator-5554"].taps == [(540, 672)]


async def test_a_raised_keyboard_is_reported_as_the_likely_cause(make_server, world):
    world.devices["emulator-5554"].keyboard = True
    result = await call(make_server(), "tap", {**TAP, "label": "Backups"})
    answer = result.structured_content
    assert answer["keyboard_shown"] is True
    assert "keyboard" in answer["note"]


async def test_ui_elements_reports_the_keyboard(make_server, world):
    world.devices["emulator-5554"].keyboard = True
    result = await call(make_server(), "ui_elements", TAP)
    assert result.structured_content["keyboard_shown"] is True
    assert result.structured_content["unlabelled_clickable"] == 1


async def test_a_failed_dump_is_retried(make_server, world):
    world.devices["emulator-5554"].failing_dumps = 2
    result = await call(make_server(), "ui_elements", TAP)
    assert not result.is_error, text(result)
    assert len(world.commands("uiautomator")) == 3


async def test_a_screen_whose_semantics_are_not_published_yet_is_read_again(make_server, world):
    world.devices["emulator-5554"].pending_semantics = 1
    result = await call(make_server(), "tap", {**TAP, "label": "Backups"})
    assert not result.is_error, text(result)
    assert world.devices["emulator-5554"].taps == [(540, 672)]


async def test_a_hierarchy_that_never_comes_is_an_error(make_server, world):
    world.devices["emulator-5554"].failing_dumps = 99
    result = await call(make_server(), "tap", {**TAP, "label": "Backups"})
    assert result.is_error
    assert "could not be read" in text(result)
    assert world.devices["emulator-5554"].taps == []


async def test_a_screen_unreadable_after_the_tap_is_not_reported_as_a_failed_tap(make_server, world):
    """Seen live on 2026-11-10: tapping a file in the Files app opened another
    app; uiautomator could not read the screen during the switch, and the tool
    answered with an error although the tap had been sent. The tap happened:
    say so, and say that whether the screen changed is unknown."""
    device = world.devices["emulator-5554"]
    device.failing_dumps_after_tap = 99
    result = await call(make_server(), "tap", {**TAP, "label": "Settings", "match": "contains"})
    assert not result.is_error, text(result)
    answer = result.structured_content
    assert answer["tapped"] == "Settings\nTab 2 of 3"
    assert answer["screen_changed"] is None
    assert "could not be read" in answer["note"] and "ui_elements" in answer["note"]
    assert device.taps == [(540, 2316)]


async def test_a_screen_unreadable_for_a_moment_after_the_tap_still_reports_the_change(make_server, world):
    device = world.devices["emulator-5554"]
    device.failing_dumps_after_tap = 2
    result = await call(make_server(), "tap", {**TAP, "label": "Settings", "match": "contains"})
    assert not result.is_error, text(result)
    assert result.structured_content["screen_changed"] is True
    assert result.structured_content["note"] == ""


async def test_a_stale_dump_is_never_read_as_the_current_screen(make_server, world):
    """If a dump fails, the file of the previous dump must not answer for it."""
    server = make_server()
    first = await call(server, "ui_elements", TAP)
    assert not first.is_error
    device = world.devices["emulator-5554"]
    device.current, device.failing_dumps = "settings", 99
    second = await call(server, "ui_elements", TAP)
    assert second.is_error
    assert "Backups" not in text(second)
