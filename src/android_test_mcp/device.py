"""The adb verbs the server needs, and nothing else.

Each method builds an argv list (never a shell string), calls the injected
runner, and parses the answer. What adb prints is checked, not trusted: adb
often exits 0 after doing nothing.
"""
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import DeviceError
from .runner import RunResult, Runner

UI_DUMP_PATH = "/data/local/tmp/android-test-mcp-ui.xml"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

_PROP = re.compile(r"^\[([^\]]+)\]: \[(.*)\]\s*$", re.MULTILINE)
_SIZE = re.compile(r"(Physical|Override) size: (\d+x\d+)")
_FOCUS = re.compile(r"mCurrentFocus=Window\{\S+ \S+ ([^/\s}]+)/")
_FOCUSED_APP = re.compile(r"mFocusedApp=\S*\{\S+ \S+ ([^/\s}]+)/")
_VERSION_NAME = re.compile(r"versionName=(\S+)")
_VERSION_CODE = re.compile(r"versionCode=(\d+)")


@dataclass(frozen=True)
class AttachedDevice:
    serial: str
    state: str
    model: str


class Adb:
    def __init__(self, runner: Runner, timeout_s: float = 30.0):
        self.runner = runner
        self.timeout_s = timeout_s

    def _run(self, serial: str | None, *args: str, timeout: float | None = None) -> RunResult:
        argv = ["adb"] + (["-s", serial] if serial else []) + list(args)
        return self.runner(argv, timeout=timeout or self.timeout_s, cwd=None)

    def _shell(self, serial: str, *args: str, timeout: float | None = None) -> str:
        return self._run(serial, "shell", *args, timeout=timeout).text

    # --- devices

    def attached(self) -> list[AttachedDevice]:
        result = self._run(None, "devices", "-l")
        if result.returncode != 0:
            raise DeviceError(f"adb devices failed: {result.text.strip()[:300]}")
        devices = []
        for line in result.stdout.decode("utf-8", errors="replace").splitlines():
            parts = line.split()
            if len(parts) < 2 or line.startswith(("List of devices", "*")):
                continue
            model = next((p.split(":", 1)[1] for p in parts[2:] if p.startswith("model:")), "")
            devices.append(AttachedDevice(parts[0], parts[1], model))
        return devices

    def properties(self, serial: str) -> dict[str, str]:
        return dict(_PROP.findall(self._shell(serial, "getprop")))

    @staticmethod
    def reports_emulator(properties: dict[str, str]) -> bool:
        return "1" in (properties.get("ro.kernel.qemu"), properties.get("ro.boot.qemu"))

    def screen_size(self, serial: str) -> str:
        sizes = dict(_SIZE.findall(self._shell(serial, "wm", "size")))
        return sizes.get("Override") or sizes.get("Physical") or ""

    # --- packages

    def install(self, serial: str, apk: Path, timeout: float) -> None:
        result = self._run(serial, "install", "-r", str(apk), timeout=timeout)
        if result.returncode != 0 or "Success" not in result.text:
            raise DeviceError(f"adb install failed: {result.text.strip()[-500:]}")

    def package_path(self, serial: str, package: str) -> str | None:
        for line in self._shell(serial, "pm", "path", package).splitlines():
            if line.startswith("package:"):
                return line.removeprefix("package:").strip()
        return None

    def package_version(self, serial: str, package: str) -> tuple[str, str]:
        dump = self._shell(serial, "dumpsys", "package", package)
        name, code = _VERSION_NAME.search(dump), _VERSION_CODE.search(dump)
        return (name.group(1) if name else ""), (code.group(1) if code else "")

    def launch(self, serial: str, package: str) -> None:
        output = self._shell(serial, "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
        if "Events injected: 1" not in output:
            raise DeviceError(f"Could not launch {package}: {output.strip()[-300:]}")

    def focus(self, serial: str) -> tuple[str | None, str | None]:
        """(package of the window holding the focus, package of the focused app).
        They differ when a system dialog sits on top of the app."""
        dump = self._shell(serial, "dumpsys", "window")
        window, app = _FOCUS.search(dump), _FOCUSED_APP.search(dump)
        return (window.group(1) if window else None), (app.group(1) if app else None)

    def is_running(self, serial: str, package: str) -> bool:
        return self._shell(serial, "pidof", package).strip().split(" ")[0].isdigit()

    def crash_log(self, serial: str) -> str:
        """The crash buffer, read without clearing it (no -c)."""
        return self._run(serial, "logcat", "-d", "-b", "crash").stdout.decode("utf-8", errors="replace")

    # --- screen

    def dump_ui(self, serial: str) -> str:
        """The hierarchy now. The old dump file is removed first: if the new dump
        fails, reading a stale one would describe a screen that is gone."""
        self._shell(serial, "rm", "-f", UI_DUMP_PATH)
        self._shell(serial, "uiautomator", "dump", UI_DUMP_PATH)
        result = self._run(serial, "exec-out", "cat", UI_DUMP_PATH)
        return result.stdout.decode("utf-8", errors="replace")

    def keyboard_shown(self, serial: str) -> bool:
        """Only `dumpsys input_method` knows; the hierarchy never shows the IME."""
        return "mInputShown=true" in self._shell(serial, "dumpsys", "input_method")

    def tap(self, serial: str, x: int, y: int) -> None:
        self._shell(serial, "input", "tap", str(x), str(y))

    def screencap(self, serial: str) -> bytes:
        # exec-out, not shell: shell may rewrite line endings and corrupt the PNG.
        data = self._run(serial, "exec-out", "screencap", "-p").stdout
        if not data.startswith(PNG_SIGNATURE):
            raise DeviceError(f"screencap did not return a PNG: {data[:200]!r}")
        return data


def png_size(data: bytes) -> tuple[int, int]:
    """Width and height from the IHDR chunk, which always comes first."""
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
