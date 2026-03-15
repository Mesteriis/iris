#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_PATH = ROOT / "ha" / "integration"
COMPATIBILITY_PATH = ROOT / "ha" / "compatibility.yaml"


def main() -> int:
    args = _parse_args()
    _run(["git", "-C", str(INTEGRATION_PATH), "fetch", "origin", "--tags", "--prune"])
    _run(["git", "-C", str(INTEGRATION_PATH), "checkout", "--detach", args.ref])
    pinned_commit = _run(
        ["git", "-C", str(INTEGRATION_PATH), "rev-parse", "HEAD"],
        capture_output=True,
    ).strip()
    _update_compatibility_pin(pinned_commit)
    print(f"Updated ha/integration to {pinned_commit}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update ha/integration submodule checkout and compatibility pin.")
    parser.add_argument("--ref", required=True, help="Branch, tag, or commit to check out in ha/integration.")
    return parser.parse_args()


def _run(command: list[str], *, capture_output: bool = False) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture_output,
    )
    return result.stdout if capture_output else ""


def _update_compatibility_pin(pinned_commit: str) -> None:
    text = COMPATIBILITY_PATH.read_text(encoding="utf-8")
    updated = re.sub(
        r'(?m)^(\s+pinned_commit:\s*")[^"]+(")$',
        rf'\g<1>{pinned_commit}\2',
        text,
    )
    COMPATIBILITY_PATH.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
