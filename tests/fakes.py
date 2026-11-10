"""A fake adb + flutter, answering the way the real tools do.

It plays the part of the injected runner: it receives argv lists, keeps
them in `calls`, and answers canned outputs copied from real devices. Any
command it does not know fails the test: the server cannot slip in a verb
nobody reviewed (uninstall, pm clear, a raw shell).
"""
import struct
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import quoteattr

from android_test_mcp.device import UI_DUMP_PATH
from android_test_mcp.runner import RunResult, RunTimeout

DEMO = "com.example.demo"


# --- view hierarchies, in the shape uiautomator writes for a Flutter app


def node(desc="", text="", hint="", bounds="[0,0][0,0]", clickable=False, cls="android.view.View"):
    attributes = {
        "index": "0", "text": text, "resource-id": "", "class": cls, "package": DEMO,
        "content-desc": desc, "checkable": "false", "checked": "false",
        "clickable": "true" if clickable else "false", "enabled": "true",
        "focusable": "true" if clickable else "false", "focused": "false", "scrollable": "false",
        "long-clickable": "false", "password": "false", "selected": "false", "bounds": bounds,
    }
    if hint:
        attributes["hint"] = hint
    return "<node " + " ".join(f"{k}={quoteattr(v)}" for k, v in attributes.items()) + " />"


def hierarchy(*nodes: str) -> str:
    return ("<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\">"
            '<node index="0" text="" resource-id="" class="android.widget.FrameLayout" '
            f'package="{DEMO}" content-desc="" checkable="false" checked="false" clickable="false" '
            'enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" '
            'password="false" selected="false" bounds="[0,0][1080,2400]">'
            + "".join(nodes) + "</node></hierarchy>")


HOME = hierarchy(
    node(desc="Songs", bounds="[0,96][1080,240]"),
    node(desc="Back", bounds="[0,96][144,240]", clickable=True, cls="android.widget.Button"),
    node(desc="Backups", bounds="[48,600][1032,744]", clickable=True, cls="android.widget.Button"),
    node(desc="Settings\nTab 2 of 3", bounds="[360,2232][720,2400]", clickable=True),
    node(hint="Search songs", bounds="[48,300][1032,420]", clickable=True, cls="android.widget.EditText"),
    node(desc="Press + to add a song", bounds="[48,1000][1032,1100]"),
    node(desc="Add a song", bounds="[900,2000][1032,2132]", clickable=True, cls="android.widget.Button"),
    node(bounds="[0,2232][360,2400]", clickable=True, cls="android.widget.ImageView"),
    node(desc="Offscreen banner", bounds="[0,0][0,0]"),
)
SETTINGS = hierarchy(
    node(desc="Settings", bounds="[0,96][1080,240]"),
    node(desc="Back", bounds="[0,96][144,240]", clickable=True, cls="android.widget.Button"),
    node(desc="Dark theme", bounds="[48,300][1032,420]", clickable=True),
)


def tiny_png(width=1080, height=2400) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00" * 8)) + chunk(b"IEND", b""))


# --- binary AndroidManifest.xml, the way aapt2 compiles it


def binary_manifest(package: str, utf8: bool = False, typed_only: bool = False) -> bytes:
    android_ns = "http://schemas.android.com/apk/res/android"
    strings = ["versionCode", "android", android_ns, "manifest", "package", package]
    if utf8:
        encoded = [bytes([len(s), len(s.encode())]) + s.encode() + b"\0" for s in strings]
    else:
        encoded = [struct.pack("<H", len(s)) + s.encode("utf-16-le") + b"\0\0" for s in strings]
    offsets, position = [], 0
    for item in encoded:
        offsets.append(position)
        position += len(item)
    body = b"".join(encoded)
    body += b"\0" * (-len(body) % 4)
    strings_start = 28 + 4 * len(strings)
    pool = (struct.pack("<HHIIIIII", 0x0001, 28, strings_start + len(body), len(strings), 0,
                        0x100 if utf8 else 0, strings_start, 0)
            + struct.pack(f"<{len(strings)}I", *offsets) + body)
    resource_map = struct.pack("<HHII", 0x0180, 8, 12, 0x0101021B)
    namespace = struct.pack("<HHIIIII", 0x0100, 16, 24, 1, 0xFFFFFFFF, 1, 2)
    raw = 0xFFFFFFFF if typed_only else 5
    attributes = struct.pack("<IIIHBBI", 0xFFFFFFFF, 4, raw, 8, 0, 0x03, 5)
    extension = struct.pack("<IIHHHHHH", 0xFFFFFFFF, 3, 20, 20, 1, 0, 0, 0)
    start = struct.pack("<HHIII", 0x0102, 16, 16 + len(extension) + len(attributes), 1, 0xFFFFFFFF)
    chunks = pool + resource_map + namespace + start + extension + attributes
    return struct.pack("<HHI", 0x0003, 8, 8 + len(chunks)) + chunks


def make_apk(path: Path, package: str = DEMO, **options) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AndroidManifest.xml", binary_manifest(package, **options))
        archive.writestr("classes.dex", b"dex\n035\0")
    return path


# --- flutter test --reporter json, one pass, one fail, one skip

FLUTTER_JSON = "\n".join([
    '{"protocolVersion":"0.1.1","runnerVersion":"1.25.8","pid":4242,"type":"start","time":0}',
    '{"suite":{"id":0,"platform":"android","path":"integration_test/app_test.dart"},"type":"suite","time":0}',
    '{"test":{"id":1,"name":"loading integration_test/app_test.dart","suiteID":0,"groupIDs":[],'
    '"metadata":{"skip":false,"skipReason":null},"line":null,"column":null,"url":null},"type":"testStart","time":2}',
    "Running Gradle task 'assembleDebug'...                            41.2s",
    "√ Built build\\app\\outputs\\flutter-apk\\app-debug.apk",
    '{"testID":1,"result":"success","skipped":false,"hidden":true,"type":"testDone","time":48000}',
    '{"group":{"id":2,"suiteID":0,"parentID":null,"name":"","metadata":{"skip":false,"skipReason":null},'
    '"testCount":3,"line":null,"column":null,"url":null},"type":"group","time":48001}',
    '{"test":{"id":3,"name":"home screen lists the songs","suiteID":0,"groupIDs":[2],'
    '"metadata":{"skip":false,"skipReason":null},"line":12,"column":3,"url":"file:///app/integration_test/app_test.dart"},'
    '"type":"testStart","time":48002}',
    '{"testID":3,"result":"success","skipped":false,"hidden":false,"type":"testDone","time":49500}',
    '{"test":{"id":4,"name":"adding a song updates the counter","suiteID":0,"groupIDs":[2],'
    '"metadata":{"skip":false,"skipReason":null},"line":20,"column":3,"url":"file:///app/integration_test/app_test.dart"},'
    '"type":"testStart","time":49501}',
    '{"testID":4,"messageType":"print","message":"tapping Add a song","type":"print","time":49600}',
    '{"testID":4,"error":"Expected: <2>\\n  Actual: <1>\\nsong counter","stackTrace":"package:test_api expect\\n'
    'integration_test/app_test.dart 27:5  main.<fn>","isFailure":true,"type":"error","time":50100}',
    '{"testID":4,"result":"failure","skipped":false,"hidden":false,"type":"testDone","time":50120}',
    '{"test":{"id":5,"name":"export to the cloud","suiteID":0,"groupIDs":[2],'
    '"metadata":{"skip":true,"skipReason":"needs network"},"line":31,"column":3,"url":null},"type":"testStart","time":50121}',
    '{"testID":5,"result":"success","skipped":true,"hidden":false,"type":"testDone","time":50122}',
    '{"success":false,"type":"done","time":50200}',
]) + "\n"


# --- logcat -d -b crash, in the threadtime format


def crash(package: str, pid: int, exception: str, caused_by: tuple[str, ...] = (), when="11-10 14:02:11.123") -> str:
    def line(message):
        return f"{when}  {pid:>5}  {pid:>5} E AndroidRuntime: {message}"
    lines = [line("FATAL EXCEPTION: main"), line(f"Process: {package}, PID: {pid}"), line(exception),
             line("\tat android.app.ActivityThread.performLaunchActivity(ActivityThread.java:4280)")]
    for cause in caused_by:
        lines += [line(f"Caused by: {cause}"), line("\tat java.lang.Runtime.loadLibrary0(Runtime.java:1081)")]
    return "\n".join(lines) + "\n"


ABI_MISMATCH = ('java.lang.UnsatisfiedLinkError: dlopen failed: "/data/app/~~x==/com.example.demo-y==/'
                'lib/arm64/libflutter.so" is for EM_AARCH64 (183) instead of EM_X86_64 (62)')

DEMO_ABI_CRASH = "--------- beginning of crash\n" + crash(
    DEMO, 5120, "java.lang.RuntimeException: Unable to start activity ComponentInfo{com.example.demo/"
                "com.example.demo.MainActivity}: java.lang.RuntimeException: native library failed",
    caused_by=("java.lang.RuntimeException: native library failed", ABI_MISMATCH))

OTHER_CRASH = "--------- beginning of crash\n" + crash(
    "com.other.app", 6001, "java.lang.IllegalStateException: other app is broken")


# --- the fake devices


@dataclass
class FakeDevice:
    state: str = "device"
    model: str = "sdk_gphone64_x86_64"
    qemu: bool = True
    size: str = "1080x2400"
    packages: dict = field(default_factory=lambda: {DEMO: ("1.4.0", "14")})
    screens: dict = field(default_factory=lambda: {"home": HOME, "settings": SETTINGS})
    current: str = "home"
    # (screen, label bounds) -> next screen: what a tap inside those bounds opens
    links: dict = field(default_factory=lambda: {("home", (360, 2232, 720, 2400)): "settings"})
    keyboard: bool = False
    # the dump file on the device; uiautomator writes it, `rm -f` removes it
    ui_file: str | None = None
    # dumps that fail ("could not get idle state") and write nothing
    failing_dumps: int = 0
    # dumps that see only the root node: Flutter has not published its semantics yet
    pending_semantics: int = 0
    # dumps that fail right AFTER a tap: the tap switched apps and uiautomator
    # cannot read the screen during the transition (seen live on 2026-11-10)
    failing_dumps_after_tap: int = 0
    # focus after launch: (focused window package, focused app package); None = the launched app
    focus_after_launch: tuple | None = None
    focus: tuple = ("com.android.launcher3", "com.android.launcher3")
    running: set = field(default_factory=set)
    dies_at_launch: bool = False
    crash_buffer: str = ""
    install_output: str = "Performing Streamed Install\nSuccess\n"
    installs_package: str | None = DEMO
    screencap: bytes = field(default_factory=tiny_png)
    taps: list = field(default_factory=list)


class FakeWorld:
    def __init__(self, devices: dict[str, FakeDevice] | None = None):
        self.devices = devices if devices is not None else {"emulator-5554": FakeDevice()}
        self.calls: list[list[str]] = []
        self.flutter_stdout = FLUTTER_JSON
        self.flutter_returncode = 1
        self.flutter_timeout = False
        self.flutter_cwd = None

    def commands(self, verb: str) -> list[list[str]]:
        return [argv for argv in self.calls if verb in argv]

    def __call__(self, argv, timeout, cwd=None) -> RunResult:
        argv = list(argv)
        self.calls.append(argv)
        if argv[0] == "flutter":
            return self._flutter(argv, timeout, cwd)
        if argv == ["adb", "devices", "-l"]:
            return ok(self._devices_listing())
        assert argv[:2] == ["adb", "-s"], f"unexpected command {argv}"
        device = self.devices[argv[2]]
        return self._adb(device, argv[3:])

    def _devices_listing(self) -> str:
        lines = ["List of devices attached"]
        for serial, device in self.devices.items():
            extra = f"product:sdk model:{device.model} device:emu64xa transport_id:1" if device.state == "device" else "transport_id:2"
            lines.append(f"{serial}\t{device.state} {extra}")
        return "\n".join(lines) + "\n\n"

    def _adb(self, device: FakeDevice, args: list[str]) -> RunResult:
        match args:
            case ["shell", "getprop"]:
                qemu = "1" if device.qemu else ""
                return ok(f"[ro.boot.qemu]: [{qemu}]\n[ro.product.model]: [{device.model}]\n"
                          "[ro.build.version.sdk]: [34]\n")
            case ["shell", "wm", "size"]:
                return ok(f"Physical size: {device.size}\n")
            case ["install", "-r", apk]:
                assert Path(apk).is_file()
                if "Success" in device.install_output and device.installs_package:
                    device.packages[device.installs_package] = ("2.0.0", "20")
                return ok(device.install_output)
            case ["shell", "pm", "path", package]:
                if package in device.packages:
                    return ok(f"package:/data/app/~~x==/{package}-y==/base.apk\n")
                return RunResult(1, b"", b"")
            case ["shell", "dumpsys", "package", package]:
                name, code = device.packages.get(package, ("", ""))
                return ok(f"Packages:\n  Package [{package}] (abc):\n    versionCode={code} minSdk=21 "
                          f"targetSdk=34\n    versionName={name}\n")
            case ["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"]:
                if package not in device.packages:
                    return ok("  bash arg: -p\n** No activities found to run, monkey aborted.\n")
                device.focus = device.focus_after_launch or (package, package)
                if not device.dies_at_launch:
                    device.running.add(package)
                return ok("  bash arg: -p\nEvents injected: 1\n## Network stats: elapsed time=12ms\n")
            case ["shell", "pidof", package]:
                if package in device.running:
                    return ok("4321\n")
                return RunResult(1, b"", b"")
            case ["logcat", "-d", "-b", "crash"]:
                return ok(device.crash_buffer)
            case ["shell", "dumpsys", "window"]:
                window, app = device.focus
                current = f"Window{{f00 u0 {window}/{window}.MainActivity}}" if window else "null"
                focused = f"ActivityRecord{{ba5 u0 {app}/.MainActivity t12}}" if app else "null"
                return ok(f"WINDOW MANAGER WINDOWS (dumpsys window windows)\n  mCurrentFocus={current}\n"
                          f"  mFocusedApp={focused}\n")
            case ["shell", "rm", "-f", path] if path == UI_DUMP_PATH:
                device.ui_file = None
                return ok("")
            case ["shell", "uiautomator", "dump", path] if path == UI_DUMP_PATH:
                if device.failing_dumps:
                    device.failing_dumps -= 1
                    return ok("ERROR: could not get idle state.\n")
                if device.pending_semantics:
                    device.pending_semantics -= 1
                    device.ui_file = hierarchy()
                else:
                    device.ui_file = device.screens[device.current]
                return ok(f"UI hierchary dumped to: {path}\n")
            case ["exec-out", "cat", path] if path == UI_DUMP_PATH:
                if device.ui_file is None:
                    return RunResult(1, b"", f"cat: {path}: No such file or directory\n".encode())
                return ok(device.ui_file)
            case ["shell", "dumpsys", "input_method"]:
                return ok(f"  mInputShown={'true' if device.keyboard else 'false'}\n")
            case ["shell", "input", "tap", x, y]:
                device.taps.append((int(x), int(y)))
                device.failing_dumps += device.failing_dumps_after_tap
                for (screen, (x1, y1, x2, y2)), target in device.links.items():
                    if screen == device.current and x1 <= int(x) < x2 and y1 <= int(y) < y2:
                        device.current = target
                return ok("")
            case ["exec-out", "screencap", "-p"]:
                return RunResult(0, device.screencap, b"")
        raise AssertionError(f"unexpected adb command {args}")

    def _flutter(self, argv, timeout, cwd) -> RunResult:
        assert argv[1:6] == ["test", "--reporter", "json", "-d", argv[5]], argv
        self.flutter_cwd = cwd
        if self.flutter_timeout:
            raise RunTimeout(argv, timeout, b"Running Gradle task 'assembleDebug'...\n", b"")
        return RunResult(self.flutter_returncode, self.flutter_stdout.encode(), b"")


def ok(text: str) -> RunResult:
    return RunResult(0, text.encode(), b"")
