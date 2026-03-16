import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.architecture.service_layer_scorecard import (
    build_service_layer_scorecard,
    write_service_layer_scorecard_json,
    write_service_layer_scorecard_markdown,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export the service-layer architecture scorecard.")
    parser.add_argument("--markdown-output", required=True, help="Filesystem path for the generated Markdown scorecard.")
    parser.add_argument("--json-output", required=True, help="Filesystem path for the generated JSON scorecard.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_service_layer_scorecard()
    markdown_path = write_service_layer_scorecard_markdown(rows=rows, output=args.markdown_output)
    json_path = write_service_layer_scorecard_json(rows=rows, output=args.json_output)
    print(markdown_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
