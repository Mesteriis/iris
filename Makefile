.PHONY: lint start backend frontend all backend-start frontend-start _lint-all _lint-backend _lint-frontend

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

backend frontend all:
	@:
