.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\\033[36m%-20s\\033[0m %s\\n", $$1, $$2}'

UV := uv

.PHONY: setup
setup: ## Create venv, lock dependencies, install dependencies and pre-commit hooks
	@echo "🚀 Checking for UV..."
	@command -v $(UV) >/dev/null 2>&1 || { echo >&2 "UV is not installed. Please install it (e.g., 'pip install uv' or see https://github.com/astral-sh/uv#installation). Aborting."; exit 1; }
	@echo "🚀 Creating virtual environment using UV..."
	@$(UV) venv .venv
	@echo "🚀 Checking uv lock file consistency with 'pyproject.toml': Running uv lock --check"
	@$(UV) lock --check
	@echo "🚀 Syncing dependencies from lockfile..."
	@$(UV) sync # Reads uv.lock
	@echo "🚀 Installing pre-commit hooks..."
	@$(UV) run pre-commit install

.PHONY: install # Alias for setup
install: setup

.PHONY: lock
lock: ## Lock dependencies from pyproject.toml into uv.lock using UV
	@echo "🚀 Locking dependencies..."
	@$(UV) lock

.PHONY: sync
sync: ## Sync dependencies from uv.lock
	@echo "🚀 Syncing dependencies from lockfile..."
	@$(UV) sync

.PHONY: check
check: ## Run code quality tools
	@echo "🚀 Checking lockfile consistency (running uv lock and checking for changes)..."
	@$(UV) lock # Re-generate lockfile based on pyproject.toml
	# Check if uv.lock was modified. Fails if there are unstaged changes to uv.lock.
	@git diff --quiet --exit-code uv.lock || (echo "❌ uv.lock is out of sync with pyproject.toml. Run 'make lock' and commit changes." && exit 1)
	@echo "✅ uv.lock is consistent with pyproject.toml."
	@echo "🚀 Linting code: Running pre-commit"
	@$(UV) run pre-commit run -a
	@echo "🚀 Static type checking: Running mypy"
	@$(UV) run mypy --check-untyped-defs paradex_py # Specify target explicitly
	@echo "🚀 Checking for unused dependencies: Running deptry"
	@$(UV) run deptry .

.PHONY: test
test: ## Test the code with pytest
	@echo "🚀 Testing code: Running pytest"
	@$(UV) run pytest --cov=paradex_py --cov-config=pyproject.toml --cov-report=xml -vv

.PHONY: build
build: clean-build ## Build wheel and sdist using uv build
	@echo "🚀 Building wheel and sdist with uv"
	@$(UV) build --out-dir dist/

.PHONY: clean-build
clean-build: ## Clean build artifacts
	@rm -rf dist build *.egg-info

.PHONY: publish
publish: ## Publish a release to PyPI using uv publish
	@echo "🚀 Publishing to PyPI with uv (using trusted publisher or env vars UV_PUBLISH_TOKEN/USERNAME/PASSWORD)"
	@$(UV) publish dist/*
	# Add --repository <url> or --index <name> for alternative indices
	# uv handles TestPyPI automatically if configured via trusted publishing
	# No explicit dry run needed, PyPI/uv usually handle existing files gracefully.

.PHONY: build-and-publish
build-and-publish: build publish ## Build and publish

.PHONY: docs-test
docs-test: ## Test if docs can be built without warnings or errors
	@$(UV) run mkdocs build -s

.PHONY: docs
docs: ## Build and serve the documentation
	@$(UV) run mkdocs serve

.DEFAULT_GOAL := help
