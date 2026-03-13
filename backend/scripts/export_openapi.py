from __future__ import annotations

import argparse

from src.core.http.openapi import write_openapi_schema
from src.core.settings import get_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export IRIS OpenAPI schema for a specific mode/profile.")
    parser.add_argument("--output", required=True, help="Filesystem path for the exported OpenAPI JSON file.")
    parser.add_argument("--mode", choices=("full", "local", "ha_addon"), help="Launch mode override.")
    parser.add_argument(
        "--profile",
        choices=("platform_full", "platform_local", "ha_embedded"),
        help="Deployment profile override.",
    )
    parser.add_argument(
        "--enable-hypothesis-engine",
        action="store_true",
        help="Include hypothesis-engine routes in the exported schema.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = get_settings().model_copy(
        update={
            key: value
            for key, value in {
                "api_launch_mode": args.mode,
                "api_deployment_profile": args.profile,
                "enable_hypothesis_engine": True if args.enable_hypothesis_engine else get_settings().enable_hypothesis_engine,
            }.items()
            if value is not None
        }
    )
    output_path = write_openapi_schema(settings=settings, output=args.output)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
