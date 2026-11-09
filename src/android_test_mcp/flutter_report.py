"""Turn the event stream of `flutter test --reporter json` into a verdict.

One JSON object per line (testStart, error, print, testDone, done...), mixed
with plain lines from the build (gradle, "Running Gradle task..."). Plain
lines are ignored here; the full log is kept as evidence anyway.

Hidden tests are the virtual ones package:test creates for loading a file or
running setUpAll. They are hidden only when they succeed: a file that fails to
compile shows up as a visible failing "loading ..." test, and is counted.
"""
import json
from dataclasses import dataclass, field

MAX_ERROR = 1500


@dataclass
class Failure:
    name: str
    error: str = ""


@dataclass
class Report:
    passed: list[str] = field(default_factory=list)
    failed: list[Failure] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    finished: bool = False
    success: bool | None = None

    def summary(self) -> dict:
        return {
            "passed": len(self.passed), "failed": len(self.failed), "skipped": len(self.skipped),
            "finished": self.finished,
            "failures": [{"name": f.name, "error": f.error[:MAX_ERROR]} for f in self.failed],
            "skipped_tests": self.skipped,
        }


def parse_events(output: str) -> Report:
    report = Report()
    names: dict[int, str] = {}
    errors: dict[int, list[str]] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind == "testStart":
            test = event.get("test") or {}
            names[test.get("id")] = test.get("name", "?")
        elif kind == "error":
            errors.setdefault(event.get("testID"), []).append(event.get("error", ""))
        elif kind == "testDone":
            if event.get("hidden"):
                continue
            test_id = event.get("testID")
            name = names.get(test_id, f"test {test_id}")
            if event.get("skipped"):
                report.skipped.append(name)
            elif event.get("result") == "success":
                report.passed.append(name)
            else:
                report.failed.append(Failure(name, "\n".join(errors.get(test_id, []))))
        elif kind == "done":
            report.finished = True
            report.success = event.get("success")
    return report
