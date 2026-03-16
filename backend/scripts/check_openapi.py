import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from iris.core.http.openapi import check_openapi_schema
from iris.core.settings import get_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check IRIS OpenAPI schema against a committed snapshot.")
    parser.add_argument("--snapshot", required=True, help="Filesystem path to the committed OpenAPI JSON snapshot.")
    parser.add_argument("--mode", choices=("full", "local", "ha_addon"), help="Launch mode override.")
    parser.add_argument(
        "--profile",
        choices=("platform_full", "platform_local", "ha_embedded"),
        help="Deployment profile override.",
    )
    parser.add_argument(
        "--enable-hypothesis-engine",
        action="store_true",
        help="Include hypothesis-engine routes when checking the schema.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    base_settings = get_settings()
    settings = base_settings.model_copy(
        update={
            key: value
            for key, value in {
                "api_launch_mode": args.mode,
                "api_deployment_profile": args.profile,
                "enable_hypothesis_engine": True if args.enable_hypothesis_engine else base_settings.enable_hypothesis_engine,
            }.items()
            if value is not None
        }
    )
    matches, diff = check_openapi_schema(settings=settings, snapshot=args.snapshot)
    if matches:
        print(args.snapshot)
        return 0
    sys.stderr.write(diff)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
