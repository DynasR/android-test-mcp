"""Locks 1 and 2: which devices may be touched, and which arguments are valid.

Lock 1, the device allowlist. By default only emulators are allowed, and an
emulator must prove it twice: its serial has the form adb gives to local
emulators (`emulator-5554`), AND the device itself reports the emulator
property. A physical device is allowed only when its serial was named at
server start, with --allow-device. Never act on someone's real phone by
accident.

Lock 2, fixed verbs with validated arguments. There is no shell tool. Every
argument that ends up on an adb or flutter command line is checked here first:
serial and package by pattern, packages against an allowlist, paths resolved
and confined to the projects named at server start, typed text restricted to
characters the device shell cannot misread.

These functions decide from their arguments alone: they never call adb.
"""
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import Refused

SERIAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
EMULATOR_SERIAL = re.compile(r"emulator-\d{4,5}")
PACKAGE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+")
MAX_TEST_TIMEOUT_S = 3600

# Typed text travels through `adb shell input text`, and `adb shell` joins its
# arguments into ONE command line that the device's own shell parses: an argv
# list on this side does not protect it. Only characters with no meaning to a
# shell are allowed. `%` is out too: `input text` reads `%s` as a space.
TEXT_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,-_@:/+=")
MAX_TEXT = 200


@dataclass(frozen=True)
class Policy:
    allowed_packages: frozenset[str] = frozenset()
    allowed_projects: tuple[Path, ...] = ()
    allowed_devices: frozenset[str] = frozenset()

    @classmethod
    def create(cls, packages=(), projects=(), devices=()) -> "Policy":
        for package in packages:
            check_package_name(package)
        for serial in devices:
            check_serial(serial)
        return cls(frozenset(packages), tuple(Path(p).resolve() for p in projects), frozenset(devices))

    # --- Lock 1

    def device_verdict(self, serial: str, reports_emulator: bool) -> tuple[bool, str]:
        """(allowed, reason). `reports_emulator` comes from the device's own
        properties, read by the caller."""
        if serial in self.allowed_devices:
            return True, "allowed explicitly with --allow-device"
        if not EMULATOR_SERIAL.fullmatch(serial):
            return False, ("not an emulator serial; a physical device is only allowed when the "
                           "server is started with --allow-device " + serial)
        if not reports_emulator:
            return False, ("has an emulator serial but does not report itself as an emulator "
                           "(ro.kernel.qemu / ro.boot.qemu); refused")
        return True, "emulator"

    # --- Lock 2

    def check_package(self, package: str) -> str:
        check_package_name(package)
        if package not in self.allowed_packages:
            allowed = ", ".join(sorted(self.allowed_packages)) or "none"
            raise Refused(f"Package {package!r} is not allowed. Allowed packages: {allowed}. "
                          "Packages are allowed when the server starts (--allow-package).")
        return package

    def check_project(self, project_dir: str) -> Path:
        path = Path(project_dir).resolve()
        if path not in self.allowed_projects:
            allowed = ", ".join(str(p) for p in self.allowed_projects) or "none"
            raise Refused(f"Project {project_dir!r} is not allowed. Allowed projects: {allowed}. "
                          "Projects are allowed when the server starts (--allow-project).")
        if not (path / "pubspec.yaml").is_file():
            raise Refused(f"{path} has no pubspec.yaml: not a Flutter project.")
        return path

    def check_test_path(self, project: Path, test_path: str) -> Path:
        """Relative paths are read from the project. Whatever the spelling
        (`..`, absolute, symlink), the resolved path must stay inside it."""
        candidate = Path(test_path)
        path = (candidate if candidate.is_absolute() else project / candidate).resolve()
        if not path.is_relative_to(project):
            raise Refused(f"Test path {test_path!r} is outside the project {project}.")
        if not path.exists():
            raise Refused(f"Test path {test_path!r} does not exist in {project}.")
        if path.is_file() and path.suffix != ".dart":
            raise Refused(f"Test path {test_path!r} is not a .dart file.")
        return path


def check_serial(serial: str) -> str:
    if not isinstance(serial, str) or not SERIAL.fullmatch(serial):
        raise Refused(f"{serial!r} is not a valid device serial. Call list_devices to see the serials.")
    return serial


def check_package_name(package: str) -> str:
    if not isinstance(package, str) or len(package) > 255 or not PACKAGE.fullmatch(package):
        raise Refused(f"{package!r} is not a valid Android package name (like com.example.app).")
    return package


def check_apk_path(apk_path: str) -> Path:
    path = Path(apk_path).resolve()
    if path.suffix.lower() != ".apk":
        raise Refused(f"{apk_path!r} does not end in .apk.")
    if not path.is_file():
        raise Refused(f"No APK file at {apk_path!r}.")
    return path


def check_text(text: str) -> str:
    if not isinstance(text, str) or not text:
        raise Refused("Nothing to type: text is empty.")
    if len(text) > MAX_TEXT:
        raise Refused(f"Text is {len(text)} characters long; at most {MAX_TEXT} can be typed in one call.")
    for character in text:
        if character in TEXT_CHARACTERS:
            continue
        if ord(character) > 127:
            raise Refused(f"{character!r} cannot be typed: `adb shell input text` types ASCII only. "
                          "Nothing was typed.")
        raise Refused(f"{character!r} is not allowed in typed text: adb passes the text through the "
                      "device shell, where it could start another command. Allowed: ASCII letters, "
                      "digits, space and . , - _ @ : / + =. Nothing was typed.")
    return text


def check_timeout(timeout_s: float) -> float:
    if not 1 <= timeout_s <= MAX_TEST_TIMEOUT_S:
        raise Refused(f"timeout_s must be between 1 and {MAX_TEST_TIMEOUT_S} seconds.")
    return float(timeout_s)
