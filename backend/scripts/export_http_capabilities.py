from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.http.capabilities import write_http_capability_catalog
from src.core.settings import get_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export the IRIS HTTP capability catalog across launch modes.")
    parser.add_argument("--output", required=True, help="Filesystem path for the generated Markdown file.")
    parser.add_argument(
        "--enable-hypothesis-engine",
        action="store_true",
        help="Include hypothesis-engine routes in the generated catalog.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    base_settings = get_settings()
    settings = base_settings.model_copy(
        update={
            "enable_hypothesis_engine": True if args.enable_hypothesis_engine else base_settings.enable_hypothesis_engine,
        }
    )
    output_path = write_http_capability_catalog(settings=settings, output=args.output)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
