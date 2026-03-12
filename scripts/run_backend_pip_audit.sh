#!/usr/bin/env bash
set -euo pipefail

tmp_requirements="$(mktemp)"
cleanup() {
  rm -f "$tmp_requirements"
}
trap cleanup EXIT

uv export --project backend --format requirements-txt --no-hashes > "$tmp_requirements"
uv run --project backend --group dev pip-audit -r "$tmp_requirements"
