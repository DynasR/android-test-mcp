"""Evidence: every screenshot and test log is kept on disk, named by time and
device, so a claim like "the test passed" can be checked after the fact."""
import re
from datetime import datetime
from pathlib import Path


class Evidence:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def path(self, serial: str, kind: str, suffix: str) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        safe_serial = re.sub(r"[^A-Za-z0-9._-]", "_", serial)
        return self.directory / f"{stamp}_{safe_serial}_{kind}{suffix}"

    def save(self, serial: str, kind: str, suffix: str, data: bytes) -> Path:
        path = self.path(serial, kind, suffix)
        path.write_bytes(data)
        return path
