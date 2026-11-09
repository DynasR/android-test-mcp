"""Run the server over stdio.

    python -m android_test_mcp --allow-package com.example.app --allow-project C:\\path\\to\\app

Everything the agent may touch is named here, at start, by a human: packages,
Flutter projects, and physical devices (emulators are allowed by default).
"""
import argparse
import sys
import tempfile
from pathlib import Path

from .errors import Refused
from .policy import Policy
from .server import build_server


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="android-test-mcp", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--allow-package", action="append", default=[], metavar="PACKAGE",
                        help="an app package the agent may install and launch (repeatable)")
    parser.add_argument("--allow-project", action="append", default=[], metavar="DIR",
                        help="a Flutter project whose tests the agent may run (repeatable)")
    parser.add_argument("--allow-device", action="append", default=[], metavar="SERIAL",
                        help="a PHYSICAL device the agent may act on (repeatable); emulators need nothing")
    parser.add_argument("--evidence-dir", type=Path, default=Path("evidence"),
                        help="where screenshots and test logs are kept (default: ./evidence)")
    parser.add_argument("--lock-dir", type=Path, default=Path(tempfile.gettempdir()) / "android-test-mcp",
                        help="where the heavy-job lock lives; the default is shared by every instance "
                             "on this machine, so two sessions never run two heavy jobs at once")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    for project in args.allow_project:
        if not (Path(project) / "pubspec.yaml").is_file():
            sys.exit(f"android-test-mcp: {project} is not a Flutter project (no pubspec.yaml)")
    try:
        policy = Policy.create(args.allow_package, args.allow_project, args.allow_device)
    except Refused as error:
        sys.exit(f"android-test-mcp: {error}")
    build_server(policy, args.evidence_dir.resolve(), lock_dir=args.lock_dir.resolve()).run("stdio")


if __name__ == "__main__":
    main()
