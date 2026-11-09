"""Read the package name an APK declares, before installing it.

Without this, `install_apk(package="com.allowed.app", apk_path="other.apk")`
would install whatever `other.apk` contains, and the check after the install
would pass as long as com.allowed.app was already on the device. The
allowlist would be a name on a form, not a lock.

The manifest inside an APK is compiled to Android's binary XML. Only what is
needed is decoded: the string pool, then the first start tag, `<manifest>`,
and its `package` attribute. No dependency on aapt or the Android SDK.
"""
import struct
import zipfile
from pathlib import Path

from .errors import Refused

_STRING_POOL, _XML_FILE, _START_ELEMENT = 0x0001, 0x0003, 0x0102
_UTF8_FLAG = 0x100
_TYPE_STRING = 0x03
_NO_INDEX = 0xFFFFFFFF
MAX_MANIFEST_BYTES = 4 * 1024 * 1024


def declared_package(apk: Path) -> str:
    try:
        with zipfile.ZipFile(apk) as archive:
            info = archive.getinfo("AndroidManifest.xml")
            if info.file_size > MAX_MANIFEST_BYTES:
                raise Refused(f"{apk.name}: AndroidManifest.xml is implausibly large.")
            manifest = archive.read(info)
    except (zipfile.BadZipFile, KeyError, OSError) as error:
        raise Refused(f"{apk.name} is not a readable APK: {error}") from error
    try:
        package = _package_from_binary_xml(manifest)
    except (struct.error, IndexError, UnicodeDecodeError, ValueError) as error:
        raise Refused(f"{apk.name}: its manifest could not be decoded ({error}).") from error
    if not package:
        raise Refused(f"{apk.name}: its manifest declares no package.")
    return package


def _package_from_binary_xml(data: bytes) -> str | None:
    kind, header_size, _ = struct.unpack_from("<HHI", data, 0)
    if kind != _XML_FILE:
        raise ValueError("not an Android binary XML file")
    strings: list[str] = []
    offset = header_size
    while offset + 8 <= len(data):
        kind, header_size, size = struct.unpack_from("<HHI", data, offset)
        if size < 8:
            raise ValueError("corrupt chunk size")
        if kind == _STRING_POOL:
            strings = _string_pool(data, offset)
        elif kind == _START_ELEMENT:
            return _manifest_package(data, offset, header_size, strings)
        offset += size
    return None


def _string_pool(data: bytes, start: int) -> list[str]:
    count, _, flags, strings_start, _ = struct.unpack_from("<IIIII", data, start + 8)
    header_size = struct.unpack_from("<H", data, start + 2)[0]
    offsets = struct.unpack_from(f"<{count}I", data, start + header_size)
    base = start + strings_start
    return [_utf8_string(data, base + o) if flags & _UTF8_FLAG else _utf16_string(data, base + o)
            for o in offsets]


def _utf8_string(data: bytes, at: int) -> str:
    _, at = _utf8_length(data, at)       # length in UTF-16 units, unused
    length, at = _utf8_length(data, at)  # length in bytes
    return data[at:at + length].decode("utf-8")


def _utf8_length(data: bytes, at: int) -> tuple[int, int]:
    first = data[at]
    if first & 0x80:
        return ((first & 0x7F) << 8) | data[at + 1], at + 2
    return first, at + 1


def _utf16_string(data: bytes, at: int) -> str:
    length = struct.unpack_from("<H", data, at)[0]
    at += 2
    if length & 0x8000:
        length = ((length & 0x7FFF) << 16) | struct.unpack_from("<H", data, at)[0]
        at += 2
    return data[at:at + 2 * length].decode("utf-16-le")


def _manifest_package(data: bytes, start: int, header_size: int, strings: list[str]) -> str | None:
    ext = start + header_size
    _, name, attr_start, attr_size, attr_count = struct.unpack_from("<IIHHH", data, ext)
    if strings[name] != "manifest":
        raise ValueError("the first element is not <manifest>")
    for i in range(attr_count):
        at = ext + attr_start + i * attr_size
        _, attr_name, raw_value = struct.unpack_from("<III", data, at)
        data_type, value = struct.unpack_from("<BI", data, at + 15)
        if strings[attr_name] != "package":
            continue
        if raw_value != _NO_INDEX:
            return strings[raw_value]
        if data_type == _TYPE_STRING:
            return strings[value]
    return None
