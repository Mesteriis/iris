from __future__ import annotations

import argparse
from pathlib import Path

from src.core.i18n import write_translation_coverage


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the IRIS translation coverage report.")
    parser.add_argument("--output", required=True, help="Filesystem path for the generated coverage markdown.")
    parser.add_argument("--base-locale", default="en", help="Canonical locale used as the coverage baseline.")
    args = parser.parse_args()

    output_path = write_translation_coverage(
        output=Path(args.output),
        base_locale=str(args.base_locale),
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
