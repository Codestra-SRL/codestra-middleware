.PHONY: inventory backup format-check lint typecheck test test-integration security verify build deploy-internal rollback report

PYTHON ?= python3
ROOT := $(CURDIR)

inventory:
	@printf 'repository=%s\n' "$(ROOT)"
	@git status --short --branch 2>/dev/null || true

backup:
	@stamp=$$(date +%Y%m%d-%H%M%S); dir=/opt/codestra/backups/middleware/$$stamp; mkdir -p "$$dir"; tar --exclude='.git' --exclude='__pycache__' -czf "$$dir/source.tgz" -C /opt/codestra middleware; sha256sum "$$dir/source.tgz"

format-check:
	@command -v ruff >/dev/null || { echo 'ruff unavailable; install pinned development dependencies' >&2; exit 2; }
	@ruff format --check app migrations tests

lint:
	@command -v ruff >/dev/null || { echo 'ruff unavailable; install pinned development dependencies' >&2; exit 2; }
	@ruff check app migrations tests

typecheck:
	@command -v mypy >/dev/null || { echo 'mypy unavailable; install pinned development dependencies' >&2; exit 2; }
	@mypy app

test:
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -q tests

test-integration:
	@echo 'Integration tests require an explicitly provisioned isolated PostgreSQL/Redis test environment'; exit 2

security:
	@! rg -n --hidden --glob '!*.pyc' --glob '!.git/**' '(BEGIN (RSA|OPENSSH) PRIVATE KEY|password\s*=|secret\s*=|AKIA[0-9A-Z]{16})' .

verify: format-check lint typecheck test security

build:
	@python3 -m compileall -q -f app

deploy-internal:
	@echo 'Deployment intentionally disabled; requires separate approval.'; exit 2

rollback:
	@echo 'Rollback is documented only; no runtime changes were made.'

report:
	@test -f reports/phase1-outbox-build-report.md
