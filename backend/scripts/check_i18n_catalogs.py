import argparse
import sys
from pathlib import Path

from iris.core.i18n import check_translation_coverage, validate_catalogs


def main() -> int:
    parser = argparse.ArgumentParser(description="Check IRIS translation catalogs and coverage snapshot.")
    parser.add_argument("--snapshot", required=True, help="Filesystem path to the committed coverage markdown.")
    parser.add_argument("--base-locale", default="en", help="Canonical locale used as the validation baseline.")
    args = parser.parse_args()

    report = validate_catalogs(base_locale=str(args.base_locale))
    if not report.is_valid:
        from iris.core.i18n import render_translation_coverage

        sys.stderr.write(render_translation_coverage(report))
        return 1

    matches, rendered = check_translation_coverage(
        snapshot=Path(args.snapshot),
        base_locale=str(args.base_locale),
    )
    if matches:
        print("Translation catalogs match the committed coverage snapshot.")
        return 0

    sys.stderr.write(rendered)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
