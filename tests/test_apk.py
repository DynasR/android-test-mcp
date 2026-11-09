"""The package an APK declares, read from its compiled manifest."""
import zipfile

import pytest

from android_test_mcp.apk import declared_package
from android_test_mcp.errors import Refused

from fakes import make_apk


@pytest.mark.parametrize("utf8", [False, True], ids=["utf16-pool", "utf8-pool"])
@pytest.mark.parametrize("typed_only", [False, True], ids=["raw-value", "typed-value"])
def test_the_declared_package_is_read(tmp_path, utf8, typed_only):
    apk = make_apk(tmp_path / "app.apk", "com.example.demo", utf8=utf8, typed_only=typed_only)
    assert declared_package(apk) == "com.example.demo"


def test_a_long_package_name_is_read(tmp_path):
    name = "com.example." + "x" * 200
    assert declared_package(make_apk(tmp_path / "app.apk", name)) == name


def test_a_file_that_is_not_a_zip_is_refused(tmp_path):
    path = tmp_path / "app.apk"
    path.write_bytes(b"not a zip at all")
    with pytest.raises(Refused, match="not a readable APK"):
        declared_package(path)


def test_an_archive_without_manifest_is_refused(tmp_path):
    path = tmp_path / "app.apk"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("classes.dex", b"dex")
    with pytest.raises(Refused, match="not a readable APK"):
        declared_package(path)


def test_a_plain_text_manifest_is_refused(tmp_path):
    path = tmp_path / "app.apk"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AndroidManifest.xml", '<manifest package="com.example.demo"/>')
    with pytest.raises(Refused, match="could not be decoded"):
        declared_package(path)


def test_a_truncated_manifest_is_refused(tmp_path):
    good = make_apk(tmp_path / "good.apk")
    with zipfile.ZipFile(good) as archive:
        manifest = archive.read("AndroidManifest.xml")
    path = tmp_path / "app.apk"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AndroidManifest.xml", manifest[:60])
    with pytest.raises(Refused):
        declared_package(path)
