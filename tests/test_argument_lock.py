"""Lock 2: fixed verbs, validated arguments.

Checked alone (the validators decide from their arguments, without adb),
then through the tools: a refused argument must stop the call before any
command that acts reaches the device."""
import pytest
from mcp import Client

from android_test_mcp.errors import Refused
from android_test_mcp.policy import Policy, check_apk_path, check_package_name, check_serial, check_timeout

from fakes import DEMO, make_apk
from helpers import call, text

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("serial", ["", "-s", "emulator-5554 ; reboot", "emulator-5554\n", "a" * 65,
                                    "emulator-5554&calc", "../emulator"])
def test_bad_serials_are_refused(serial):
    with pytest.raises(Refused):
        check_serial(serial)


@pytest.mark.parametrize("serial", ["emulator-5554", "R58M41ABCDE", "192.168.1.20:5555"])
def test_good_serials_pass(serial):
    assert check_serial(serial) == serial


@pytest.mark.parametrize("package", ["", "demo", "com.example.demo;rm", "com..demo", "1com.demo",
                                     "com.example.demo --user 0", "-p"])
def test_bad_package_names_are_refused(package):
    with pytest.raises(Refused):
        check_package_name(package)


def test_a_valid_package_that_is_not_allowed_is_refused():
    with pytest.raises(Refused, match="not allowed"):
        Policy.create([DEMO]).check_package("com.android.settings")


def test_an_allowed_package_passes():
    assert Policy.create([DEMO]).check_package(DEMO) == DEMO


def test_apk_path_must_end_in_apk(tmp_path):
    archive = make_apk(tmp_path / "app.zip")
    with pytest.raises(Refused, match=r"\.apk"):
        check_apk_path(str(archive))


def test_apk_path_must_exist(tmp_path):
    with pytest.raises(Refused, match="No APK"):
        check_apk_path(str(tmp_path / "missing.apk"))


def test_project_must_be_allowed(project, tmp_path):
    other = tmp_path / "other_app"
    other.mkdir()
    (other / "pubspec.yaml").write_text("name: other\n")
    with pytest.raises(Refused, match="not allowed"):
        Policy.create(projects=[project]).check_project(str(other))


def test_an_allowed_project_is_matched_whatever_the_spelling(project):
    policy = Policy.create(projects=[project])
    assert policy.check_project(str(project / "integration_test" / "..")) == project.resolve()


def test_a_subfolder_of_an_allowed_project_is_not_the_project(project):
    with pytest.raises(Refused):
        Policy.create(projects=[project]).check_project(str(project / "integration_test"))


@pytest.mark.parametrize("test_path", ["../outside_test.dart", "integration_test/../../outside_test.dart"])
def test_test_path_cannot_leave_the_project(project, test_path):
    (project.parent / "outside_test.dart").write_text("void main() {}\n")
    with pytest.raises(Refused, match="outside"):
        Policy.create(projects=[project]).check_test_path(project.resolve(), test_path)


def test_an_absolute_test_path_elsewhere_is_refused(project, tmp_path):
    elsewhere = tmp_path / "elsewhere_test.dart"
    elsewhere.write_text("void main() {}\n")
    with pytest.raises(Refused, match="outside"):
        Policy.create(projects=[project]).check_test_path(project.resolve(), str(elsewhere))


def test_test_path_must_exist_and_be_dart(project):
    policy = Policy.create(projects=[project])
    with pytest.raises(Refused, match="does not exist"):
        policy.check_test_path(project.resolve(), "integration_test/missing_test.dart")
    with pytest.raises(Refused, match="not a .dart"):
        policy.check_test_path(project.resolve(), "README.md")


def test_a_test_folder_inside_the_project_passes(project):
    path = Policy.create(projects=[project]).check_test_path(project.resolve(), "integration_test")
    assert path == (project / "integration_test").resolve()


@pytest.mark.parametrize("timeout_s", [0, -5, 3601, 10 ** 9])
def test_timeouts_are_bounded(timeout_s):
    with pytest.raises(Refused):
        check_timeout(timeout_s)


def test_policy_refuses_a_malformed_allowlist_at_start():
    with pytest.raises(Refused):
        Policy.create(packages=["not a package"])


# --- through the server: the refusal comes before anything acts

async def test_the_tool_list_is_fixed(make_server):
    async with Client(make_server()) as client:
        names = sorted(tool.name for tool in (await client.list_tools()).tools)
    assert names == ["install_apk", "launch_app", "list_devices", "restart_app", "run_flutter_test",
                     "screenshot", "set_airplane_mode", "tap", "type_text", "ui_elements"]


async def test_install_of_a_package_off_the_list_is_refused(make_server, world, tmp_path):
    other = make_apk(tmp_path / "settings.apk", "com.android.settings")
    result = await call(make_server(), "install_apk",
                        {"serial": "emulator-5554", "apk_path": str(other), "package": "com.android.settings"})
    assert result.is_error
    assert "not allowed" in text(result)
    assert world.commands("install") == []


async def test_an_apk_must_declare_the_package_it_is_installed_as(make_server, world, tmp_path):
    """The allowlist is checked against what the APK really contains, not
    against the name the agent writes next to it."""
    other = make_apk(tmp_path / "innocent-looking.apk", "com.android.settings")
    result = await call(make_server(), "install_apk",
                        {"serial": "emulator-5554", "apk_path": str(other), "package": DEMO})
    assert result.is_error
    assert "declares package 'com.android.settings'" in text(result)
    assert world.commands("install") == []


async def test_a_file_that_is_not_an_apk_is_refused(make_server, world, tmp_path):
    fake = tmp_path / "fake.apk"
    fake.write_bytes(b"MZ not a zip")
    result = await call(make_server(), "install_apk",
                        {"serial": "emulator-5554", "apk_path": str(fake), "package": DEMO})
    assert result.is_error
    assert world.commands("install") == []


async def test_launch_of_a_package_off_the_list_is_refused(make_server, world):
    result = await call(make_server(), "launch_app", {"serial": "emulator-5554", "package": "com.android.settings"})
    assert result.is_error
    assert world.commands("monkey") == []


async def test_a_bad_serial_never_reaches_adb(make_server, world):
    result = await call(make_server(), "tap", {"serial": "emulator-5554;reboot", "label": "Back"})
    assert result.is_error
    assert world.calls == []


async def test_flutter_test_in_a_project_off_the_list_is_refused(make_server, world, project):
    result = await call(make_server(projects=[]), "run_flutter_test",
                        {"serial": "emulator-5554", "project_dir": str(project), "test_path": "integration_test"})
    assert result.is_error
    assert "not allowed" in text(result)
    assert world.commands("flutter") == []


async def test_flutter_test_path_outside_the_project_is_refused(make_server, world, project):
    (project.parent / "outside_test.dart").write_text("void main() {}\n")
    result = await call(make_server(), "run_flutter_test",
                        {"serial": "emulator-5554", "project_dir": str(project), "test_path": "../outside_test.dart"})
    assert result.is_error
    assert world.commands("flutter") == []
