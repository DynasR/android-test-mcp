"""Mutation check: break each protection on purpose, and require a test to fail.

A test suite that stays green when a lock is removed protects nothing. Each
mutation below removes or weakens one protection; the named test file must
then turn red. The source file is always restored byte for byte, even on
interruption.

Usage: python tools/mutation_check.py      (about two minutes)
Exit code: 0 if every mutation is caught, 1 otherwise.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LF, CRLF = chr(10), chr(13) + chr(10)

POLICY = "src/android_test_mcp/policy.py"
DEVICE = "src/android_test_mcp/device.py"
JOBLOCK = "src/android_test_mcp/joblock.py"
UI = "src/android_test_mcp/ui.py"
SERVER = "src/android_test_mcp/server.py"
APK = "src/android_test_mcp/apk.py"
RUNNER = "src/android_test_mcp/runner.py"
REPORT = "src/android_test_mcp/flutter_report.py"
CRASH = "src/android_test_mcp/crash.py"

# (what is broken, file, original text, mutated text, test file that must fail)
MUTATIONS = [
    # --- lock 1: device allowlist
    ("lock 1: every device allowed", POLICY,
     "        if serial in self.allowed_devices:", "        if True:", "tests/test_device_lock.py"),
    ("lock 1: serial form not checked", POLICY,
     "        if not EMULATOR_SERIAL.fullmatch(serial):", "        if False:", "tests/test_device_lock.py"),
    ("lock 1: serial form matched as a prefix", POLICY,
     "        if not EMULATOR_SERIAL.fullmatch(serial):", "        if not EMULATOR_SERIAL.match(serial):",
     "tests/test_device_lock.py"),
    ("lock 1: device's own emulator property ignored", POLICY,
     "        if not reports_emulator:", "        if False:", "tests/test_device_lock.py"),
    ("lock 1: every device claims to be an emulator", DEVICE,
     '        return "1" in (properties.get("ro.kernel.qemu"), properties.get("ro.boot.qemu"))',
     "        return True", "tests/test_device_lock.py"),
    ("server: lock 1 unplugged", SERVER,
     "        if not allowed:\n            raise Refused(f\"Device {serial}",
     "        if False:\n            raise Refused(f\"Device {serial}", "tests/test_device_lock.py"),
    ("server: device presence not checked", SERVER,
     "        if serial not in attached:", "        if False:", "tests/test_device_lock.py"),

    # --- lock 2: fixed verbs, validated arguments
    ("lock 2: package allowlist removed", POLICY,
     "        if package not in self.allowed_packages:", "        if False:", "tests/test_argument_lock.py"),
    ("lock 2: package name matched as a prefix", POLICY,
     "not PACKAGE.fullmatch(package)", "not PACKAGE.match(package)", "tests/test_argument_lock.py"),
    ("lock 2: serial matched as a prefix", POLICY,
     "not SERIAL.fullmatch(serial)", "not SERIAL.match(serial)", "tests/test_argument_lock.py"),
    ("lock 2: .apk suffix not required", POLICY,
     '    if path.suffix.lower() != ".apk":', "    if False:", "tests/test_argument_lock.py"),
    ("lock 2: project allowlist removed", POLICY,
     "        if path not in self.allowed_projects:", "        if False:", "tests/test_argument_lock.py"),
    ("lock 2: test path may leave the project", POLICY,
     "        if not path.is_relative_to(project):", "        if False:", "tests/test_argument_lock.py"),
    ("lock 2: test timeout unbounded", POLICY,
     "    if not 1 <= timeout_s <= MAX_TEST_TIMEOUT_S:", "    if False:", "tests/test_argument_lock.py"),
    ("server: APK's declared package not compared", SERVER,
     "            if declared != package:", "            if False:", "tests/test_argument_lock.py"),
    ("server: package allowlist unplugged from install", SERVER,
     "            policy.check_package(package)\n            apk = check_apk_path(apk_path)",
     "            apk = check_apk_path(apk_path)", "tests/test_argument_lock.py"),
    ("server: serial not validated", SERVER,
     "        check_serial(serial)\n        attached", "        attached", "tests/test_argument_lock.py"),
    ("apk: package attribute read from the wrong field", APK,
     "            return strings[raw_value]", "            return strings[attr_name]", "tests/test_apk.py"),
    ("runner: arguments go through a shell", RUNNER,
     "stderr=subprocess.PIPE, shell=False,", "stderr=subprocess.PIPE, shell=True,", "tests/test_runner.py"),
    ("runner: batch-file metacharacters let through", RUNNER,
     "        if unsafe:", "        if False:", "tests/test_runner.py"),
    ("runner: only the direct child is killed", RUNNER,
     "        _kill_tree(process)", "        process.kill()", "tests/test_runner.py"),

    # --- lock 3: one heavy job at a time
    ("lock 3: lock always granted", JOBLOCK,
     "            if not _try_lock(fd):", "            _try_lock(fd)\n            if False:",
     "tests/test_job_lock.py"),
    ("server: lock dir ignored", SERVER,
     "    heavy = HeavyJobLock(Path(lock_dir or evidence_dir))", "    heavy = HeavyJobLock(Path(evidence_dir))",
     "tests/test_job_lock.py"),
    ("server: lock 3 unplugged from install", SERVER,
     '            with heavy.hold(f"install_apk {package} on {serial}"):', "            with _as_tool_error():",
     "tests/test_job_lock.py"),
    ("server: lock 3 unplugged from flutter test", SERVER,
     '            with heavy.hold(f"run_flutter_test on {serial}"):', "            with _as_tool_error():",
     "tests/test_job_lock.py"),

    # --- lock 4: loud taps
    ("lock 4: ambiguity tolerated", UI,
     "    if len(distinct) > 1:", "    if False:", "tests/test_tap_lock.py"),
    ("lock 4: exact match done as substring", UI,
     "        hits = [node for node in screen.nodes if label in node.labels]",
     "        hits = [node for node in screen.nodes if any(label in text for text in node.labels)]",
     "tests/test_tap_lock.py"),
    ("lock 4: hint not read", UI,
     "(self.desc, self.text, self.hint)", "(self.desc, self.text)", "tests/test_tap_lock.py"),
    ("lock 4: invisible elements tapped", UI,
     "    on_screen = [node for node in hits if node.has_area]", "    on_screen = hits", "tests/test_tap_lock.py"),
    ("lock 4: signature sees only the structure", UI,
     '        visible.append("\\x1f".join(element.get(name) or "" for name in _VISIBLE))',
     '        visible.append(element.get("class") or "")', "tests/test_tap_lock.py"),
    ("server: screen always reported changed", SERVER,
     "            if read_screen(serial).signature != signature:", "            if True:", "tests/test_tap_lock.py"),
    ("server: target looked up nowhere", SERVER,
     "            target = find_target(before, label, match)",
     "            target = before.nodes[-1]", "tests/test_tap_lock.py"),
    ("device: keyboard never reported", DEVICE,
     '        return "mInputShown=true" in', '        return False and "mInputShown=true" in',
     "tests/test_tap_lock.py"),
    ("device: stale dump file not removed", DEVICE,
     '        self._shell(serial, "rm", "-f", UI_DUMP_PATH)\n', "", "tests/test_tap_lock.py"),

    # --- verified launch and install
    ("launch: focus not verified", SERVER,
     "                if window == package:", "                if True:", "tests/test_server.py"),
    ("launch: focused app taken for the front window", SERVER,
     "                if window == package:", "                if app == package:", "tests/test_server.py"),
    ("launch: package matched as a prefix", SERVER,
     "                if window == package:", '                if (window or "").startswith(package):',
     "tests/test_server.py"),
    ("launch: installation not checked first", SERVER,
     "            if adb.package_path(serial, package) is None:", "            if False:", "tests/test_server.py"),
    ("launch: liveness not checked, every failure read as a crash", SERVER,
     "        if adb.is_running(serial, package):", "        if False:", "tests/test_crash.py"),
    ("launch: crash log never read", SERVER,
     "        if adb.is_running(serial, package):", "        if True:", "tests/test_crash.py"),
    ("device: a dead process reported alive", DEVICE,
     '        return self._shell(serial, "pidof", package).strip().split(" ")[0].isdigit()',
     "        return True", "tests/test_crash.py"),
    ("crash: any package's crash blamed", CRASH,
     "    ours = [lines for name, lines in crashes if name == package]",
     "    ours = [lines for name, lines in crashes]", "tests/test_crash.py"),
    ("crash: package matched as a prefix", CRASH,
     "    ours = [lines for name, lines in crashes if name == package]",
     "    ours = [lines for name, lines in crashes if name and name.startswith(package)]",
     "tests/test_crash.py"),
    ("crash: oldest crash taken", CRASH,
     "    lines = ours[-1]", "    lines = ours[0]", "tests/test_crash.py"),
    ("crash: first Caused by taken", CRASH,
     'caused_by[-1].removeprefix("Caused by: ")', 'caused_by[0].removeprefix("Caused by: ")',
     "tests/test_crash.py"),
    ("crash: lines of other processes mixed in", CRASH,
     "        if not crashes or pid != current_pid:", "        if not crashes:", "tests/test_crash.py"),
    ("crash: device text not capped", CRASH,
     "    return text if len(text) <= MAX_CAUSE else", "    return text if True else", "tests/test_crash.py"),
    ("crash: control characters let through", CRASH,
     '    text = "".join(ch if ch.isprintable() else " " for ch in text).strip()',
     "    text = text.strip()", "tests/test_crash.py"),
    ("crash: ABI hint never given", CRASH,
     "    mismatch = _ABI.search(cause)", "    mismatch = None", "tests/test_crash.py"),
    ("install: adb's word taken for success", DEVICE,
     '        if result.returncode != 0 or "Success" not in result.text:', "        if result.returncode != 0:",
     "tests/test_server.py"),
    ("install: presence not verified after install", SERVER,
     "            if installed is None:", "            if False:", "tests/test_server.py"),
    ("screenshot: any bytes taken for a PNG", DEVICE,
     "        if not data.startswith(PNG_SIGNATURE):", "        if False:", "tests/test_server.py"),

    # --- flutter verdict
    ("flutter: hidden tests counted", REPORT,
     '            if event.get("hidden"):', "            if False:", "tests/test_flutter_report.py"),
    ("flutter: skipped tests counted as passed", REPORT,
     '            if event.get("skipped"):', "            if False:", "tests/test_flutter_report.py"),
    ("flutter: exit code ignored", SERVER,
     "            success = (result.returncode == 0 and report.finished",
     "            success = (report.finished", "tests/test_server.py"),
    ("flutter: a run without tests reported as a run", SERVER,
     "            if not (report.finished or report.passed or report.failed or report.skipped):",
     "            if False:", "tests/test_server.py"),
    ("flutter: log not kept", SERVER,
     '                log.write_bytes(result.stdout + b"\\n--- stderr ---\\n" + result.stderr)\n', "",
     "tests/test_server.py"),
]


def caught(test_file: str) -> bool:
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", test_file],
                         cwd=ROOT, capture_output=True, text=True, timeout=600)
    return run.returncode != 0


def read_exact(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def write_exact(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def main() -> int:
    missed = []
    for name, file, original, mutated, test_file in MUTATIONS:
        path = ROOT / file
        # Read and written back without newline translation: the file comes
        # back exactly as it was, whatever its line endings.
        source = read_exact(path)
        eol = CRLF if CRLF in source else LF
        original, mutated = original.replace(LF, eol), mutated.replace(LF, eol)
        if source.count(original) != 1:
            print(f"STALE   {name}: the original text is not in {file} exactly once", flush=True)
            missed.append(name)
            continue
        try:
            write_exact(path, source.replace(original, mutated))
            ok = caught(test_file)
        finally:
            write_exact(path, source)
        print(f"{'caught' if ok else 'MISSED'}  {name}", flush=True)
        if not ok:
            missed.append(name)
    print(f"\n{len(MUTATIONS) - len(missed)}/{len(MUTATIONS)} mutations caught.")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
