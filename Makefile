.PHONY: lint start backend frontend all backend-start frontend-start _lint-all _lint-backend _lint-frontend \
	openapi-export-full openapi-export-ha openapi-check-full openapi-check-ha openapi-check api-matrix-export

BACKEND_HOOKS := \
	ruff \
	pyupgrade \
	backend-mypy \
	backend-bandit \
	backend-import-linter \
	backend-deptry \
	backend-pip-audit \
	backend-eradicate \
	backend-tryceratops \
	backend-vulture \
	backend-xenon \
	backend-semgrep

FRONTEND_HOOKS := \
	frontend-vue-tsc \
	frontend-npm-audit

OPENAPI_DIR := openapi
OPENAPI_EXPORT := cd backend && uv run python scripts/export_openapi.py
OPENAPI_CHECK := cd backend && uv run python scripts/check_openapi.py
API_MATRIX_EXPORT := cd backend && uv run python scripts/export_http_matrix.py

LINT_SCOPE := $(firstword $(filter backend frontend all,$(filter-out lint start,$(MAKECMDGOALS))))
LINT_SCOPE := $(if $(LINT_SCOPE),$(LINT_SCOPE),all)
START_SERVICE := $(firstword $(filter backend frontend,$(MAKECMDGOALS)))

lint:
	@case "$(LINT_SCOPE)" in \
		backend) $(MAKE) --no-print-directory _lint-backend ;; \
		frontend) $(MAKE) --no-print-directory _lint-frontend ;; \
		all) $(MAKE) --no-print-directory _lint-all ;; \
		*) echo "Usage: make lint [backend|frontend|all]" >&2; exit 2 ;; \
	esac

_lint-all:
	uv run --project backend --group dev pre-commit run --all-files --hook-stage manual

_lint-backend:
	@set -e; \
	for hook in $(BACKEND_HOOKS); do \
		echo "==> $$hook"; \
		uv run --project backend --group dev pre-commit run $$hook --all-files --hook-stage manual; \
	done

_lint-frontend:
	@set -e; \
	for hook in $(FRONTEND_HOOKS); do \
		echo "==> $$hook"; \
		uv run --project backend --group dev pre-commit run $$hook --all-files --hook-stage manual; \
	done

start:
	@case "$(START_SERVICE)" in \
		backend) $(MAKE) --no-print-directory backend-start ;; \
		frontend) $(MAKE) --no-print-directory frontend-start ;; \
		*) echo "Usage: make <backend|frontend> start" >&2; exit 2 ;; \
	esac

backend-start:
	cd backend && uv run python -m src.main

frontend-start:
	npm --prefix frontend run dev

openapi-export-full:
	@$(OPENAPI_EXPORT) \
		--output $(OPENAPI_DIR)/openapi-full.json \
		--mode full \
		--profile platform_full \
		--enable-hypothesis-engine

openapi-export-ha:
	@$(OPENAPI_EXPORT) \
		--output $(OPENAPI_DIR)/openapi-ha-addon.json \
		--mode ha_addon \
		--profile ha_embedded \
		--enable-hypothesis-engine

openapi-check-full:
	@$(OPENAPI_CHECK) \
		--snapshot $(OPENAPI_DIR)/openapi-full.json \
		--mode full \
		--profile platform_full \
		--enable-hypothesis-engine

openapi-check-ha:
	@$(OPENAPI_CHECK) \
		--snapshot $(OPENAPI_DIR)/openapi-ha-addon.json \
		--mode ha_addon \
		--profile ha_embedded \
		--enable-hypothesis-engine

openapi-check: openapi-check-full openapi-check-ha

api-matrix-export:
	@$(API_MATRIX_EXPORT) \
		--output ../docs/_generated/http-availability-matrix.md \
		--enable-hypothesis-engine

backend frontend all:
	@:
