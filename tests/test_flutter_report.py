"""The JSON event stream of `flutter test`, turned into counts and failures."""
from android_test_mcp.flutter_report import parse_events

from fakes import FLUTTER_JSON


def test_one_pass_one_fail_one_skip():
    report = parse_events(FLUTTER_JSON)
    assert report.passed == ["home screen lists the songs"]
    assert [failure.name for failure in report.failed] == ["adding a song updates the counter"]
    assert report.skipped == ["export to the cloud"]
    assert report.finished and report.success is False


def test_the_failure_carries_its_message():
    [failure] = parse_events(FLUTTER_JSON).failed
    assert "Expected: <2>" in failure.error and "Actual: <1>" in failure.error


def test_the_hidden_loading_test_is_not_counted():
    report = parse_events(FLUTTER_JSON)
    assert not any(name.startswith("loading") for name in report.passed)


def test_a_file_that_does_not_compile_is_a_failure():
    stream = "\n".join([
        '{"test":{"id":1,"name":"loading integration_test/broken_test.dart","suiteID":0,"groupIDs":[]},"type":"testStart"}',
        '{"testID":1,"error":"Failed to load: Error: Undefined name \'tester\'.","isFailure":false,"type":"error"}',
        '{"testID":1,"result":"error","skipped":false,"hidden":false,"type":"testDone"}',
        '{"success":false,"type":"done"}',
    ])
    report = parse_events(stream)
    assert [failure.name for failure in report.failed] == ["loading integration_test/broken_test.dart"]
    assert "Undefined name" in report.failed[0].error


def test_a_stream_cut_short_is_not_finished():
    cut = FLUTTER_JSON.split('{"success"')[0]
    report = parse_events(cut)
    assert not report.finished and report.success is None


def test_noise_is_ignored():
    report = parse_events("Running Gradle task...\n{not json\n[1, 2]\n" + FLUTTER_JSON)
    assert len(report.passed) == 1


def test_summary_is_bounded():
    stream = "\n".join([
        '{"test":{"id":1,"name":"long"},"type":"testStart"}',
        '{"testID":1,"error":"' + "x" * 10000 + '","type":"error"}',
        '{"testID":1,"result":"failure","hidden":false,"type":"testDone"}',
    ])
    summary = parse_events(stream).summary()
    assert len(summary["failures"][0]["error"]) == 1500
