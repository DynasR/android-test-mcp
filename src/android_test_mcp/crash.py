"""Why an app died at launch, read from the device's crash log.

`adb logcat -d -b crash` holds the last crashes of every app on the device.
Only the latest crash of THE launched package is used: another app's crash
must never be blamed on it. Lines of one crash are tied together by the
process id that logged them, so lines interleaved by other processes are
left out.

What comes out is device data: control characters removed, length capped. It
describes the failure; it is never an instruction to follow.
"""
import re

MAX_CAUSE = 300

# threadtime format: "11-10 14:02:11.123  4321  4321 E AndroidRuntime: message"
_LINE = re.compile(r"^\S+\s+\S+\s+(\d+)\s+\d+\s+[VDIWEFA]\s+[^:]*?:\s?(.*)$")
_PROCESS = re.compile(r"^Process: ([^,\s]+), PID: (\d+)")
_ABI = re.compile(r"is for EM_(\w+) \(\d+\) instead of EM_(\w+)")


def root_cause(log: str, package: str) -> str | None:
    """The root cause of `package`'s latest crash, or None if it has none."""
    crashes: list[tuple[str | None, list[str]]] = []
    current_pid = None
    for raw in log.splitlines():
        line = _LINE.match(raw)
        if not line:
            continue
        pid, message = line.groups()
        if message.startswith("FATAL EXCEPTION"):
            crashes.append((None, []))
            current_pid = pid
            continue
        if not crashes or pid != current_pid:
            continue
        process = _PROCESS.match(message)
        if process and crashes[-1][0] is None:
            crashes[-1] = (process.group(1), crashes[-1][1])
            continue
        crashes[-1][1].append(message)

    ours = [lines for name, lines in crashes if name == package]
    if not ours:
        return None
    lines = ours[-1]
    caused_by = [line for line in lines if line.startswith("Caused by: ")]
    if caused_by:
        cause = caused_by[-1].removeprefix("Caused by: ")
    else:
        cause = next((line for line in lines if line.strip() and not line.lstrip().startswith("at ")), "")
    return _clean(cause) or None


def abi_hint(cause: str) -> str:
    """A plain-language hint when the crash is a native-code ABI mismatch."""
    mismatch = _ABI.search(cause)
    if not mismatch:
        return ""
    built_for, device = mismatch.groups()
    return (f" Hint: the APK has no native code for this device's ABI (its native libraries are "
            f"built for {built_for}, the device runs {device}). Install an APK that includes this "
            "ABI, such as a debug build, or use an emulator image with the APK's ABI.")


def _clean(text: str) -> str:
    text = "".join(ch if ch.isprintable() else " " for ch in text).strip()
    return text if len(text) <= MAX_CAUSE else text[:MAX_CAUSE - 1] + "…"
