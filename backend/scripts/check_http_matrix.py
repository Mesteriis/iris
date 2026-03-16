import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.http.matrix import check_http_availability_matrix
from src.core.settings import get_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check the IRIS HTTP availability matrix against a committed snapshot.")
    parser.add_argument("--snapshot", required=True, help="Filesystem path to the committed HTTP availability matrix.")
    parser.add_argument(
        "--enable-hypothesis-engine",
        action="store_true",
        help="Include hypothesis-engine routes in the generated matrix.",
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
    matches, diff = check_http_availability_matrix(settings=settings, snapshot=args.snapshot)
    if matches:
        print(args.snapshot)
        return 0
    sys.stderr.write(diff)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
