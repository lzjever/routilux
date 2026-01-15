.PHONY: help clean install dev-install test test-cov test-integration test-unit test-api lint format format-check check build sdist wheel docs html clean-docs upload upload-test check-package setup-venv pre-commit-install pre-commit-run pre-commit-update type-check install-tools clean-all

# Use uv if available, otherwise fall back to pip
UV := $(shell command -v uv 2>/dev/null)
ifeq ($(UV),)
	PIP_CMD = pip
	PYTHON_CMD = python
else
	PIP_CMD = uv pip
	PYTHON_CMD = uv run python
	# dev group is installed by default with uv sync
	UV_SYNC = uv sync --group docs --all-extras
endif

help:
	@echo "Available targets:"
	@echo ""
	@echo "Setup (run first):"
	@echo "  dev-install   - Install package with development dependencies (recommended for active development)"
	@echo "  setup-venv    - Create virtual environment and install dependencies only (no package install)"
	@echo "                  Use for: CI/CD, code review, or when you don't need to import the package"
	@echo "  install       - Install the package (after setup-venv or standalone)"
	@echo ""
	@echo "Testing:"
	@echo "  test          - Run all tests"
	@echo "  test-cov      - Run tests with coverage report"
	@echo "  test-integration - Run all integration tests (requires external services)"
	@echo "  test-unit     - Run only unit tests"
	@echo "  test-api      - Run API endpoint tests"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint          - Run linting checks (ruff)"
	@echo "  format        - Format code with ruff"
	@echo "  format-check  - Check code formatting"
	@echo "  type-check    - Run mypy type checking"
	@echo "  check         - Run all checks (lint + format check + tests)"
	@echo "  pre-commit-install - Install pre-commit hooks"
	@echo "  pre-commit-run     - Run pre-commit hooks manually on all files"
	@echo "  pre-commit-update   - Update pre-commit hooks to latest versions"
	@echo ""
	@echo "Building:"
	@echo "  build         - Build source and wheel distributions"
	@echo "  sdist         - Build source distribution"
	@echo "  wheel         - Build wheel distribution"
	@echo "  check-package - Check package before uploading"
	@echo ""
	@echo "Publishing:"
	@echo "  upload        - Upload package to PyPI (requires PYPI_TOKEN env var)"
	@echo "  upload-test   - Upload package to TestPyPI (requires TEST_PYPI_TOKEN env var)"
	@echo ""
	@echo "Documentation:"
	@echo "  docs          - Build documentation"
	@echo "  html          - Build HTML documentation"
	@echo ""
	@echo "Cleanup:"
	@echo "  clean         - Clean build artifacts"
	@echo "  clean-docs    - Clean documentation build"
	@echo "  clean-all     - Clean all build artifacts and cache files"
	@echo "  install-tools - Install additional development tools"
	@echo ""
	@if [ -n "$(UV)" ]; then \
		echo "Using uv for dependency management"; \
	else \
		echo "Using pip for dependency management (consider installing uv: curl -LsSf https://astral.sh/uv/install.sh | sh)"; \
	fi
	@echo ""
	@echo "Note: For active development, run 'make dev-install' (installs package + deps)."
	@echo "      For CI/tools only, run 'make setup-venv' (deps only, no package)."

setup-venv:
	@echo "Setting up virtual environment and installing dependencies (without installing package)..."
	@echo "This is useful for CI/CD, code review, or when you only need development tools."
	@if [ -n "$(UV)" ]; then \
		uv sync --group docs --all-extras --no-install-project; \
		echo "✅ Virtual environment created and dependencies installed!"; \
		echo "   To install the package later, run: make install"; \
		echo "   Note: Some tests may fail without the package installed."; \
	else \
		echo "Error: uv is required for setup-venv. Install uv or use 'make dev-install' instead."; \
		exit 1; \
	fi

install:
	@if [ -n "$(UV)" ]; then \
		uv sync; \
	else \
		$(PIP_CMD) install -e .; \
	fi

dev-install:
	@echo "Installing package with all development dependencies..."
	@if [ -n "$(UV)" ]; then \
		uv sync --group docs --all-extras; \
	else \
		$(PIP_CMD) install -e ".[dev]"; \
	fi
	@echo "✅ Package and dependencies installed! Ready for development."

test:
	$(PYTHON_CMD) -m pytest tests/ -v

test-cov:
	$(PYTHON_CMD) -m pytest tests/ --cov=routilux --cov-report=html --cov-report=term

test-integration:
	@echo "Running integration tests (requires external services)..."
	$(PYTHON_CMD) -m pytest tests/ -v -m integration

test-unit:
	@echo "Running unit tests only..."
	$(PYTHON_CMD) -m pytest tests/ -v -m "not integration"

test-api:
	@echo "Running API endpoint tests..."
	$(PYTHON_CMD) -m pytest tests/ -v -m api

lint:
	$(PYTHON_CMD) -m ruff check routilux/ tests/ examples/ --output-format=concise

format:
	$(PYTHON_CMD) -m ruff format routilux/ tests/ examples/

format-check:
	$(PYTHON_CMD) -m ruff format --check routilux/ tests/ examples/

type-check:
	@echo "Running mypy type checking..."
	$(PYTHON_CMD) -m mypy routilux/

check: lint format-check test
	@echo "All checks passed!"

build: clean
	@if [ -n "$(UV)" ]; then \
		uv sync --group docs --all-extras; \
	fi
	$(PYTHON_CMD) -m build

sdist: clean
	@if [ -n "$(UV)" ]; then \
		uv sync --group docs --all-extras; \
	fi
	$(PYTHON_CMD) -m build --sdist

wheel: clean
	@if [ -n "$(UV)" ]; then \
		uv sync --group docs --all-extras; \
	fi
	$(PYTHON_CMD) -m build --wheel

check-package: build
	@echo "Checking package..."
	@if [ -n "$(UV)" ]; then \
		uv pip install twine; \
	else \
		$(PIP_CMD) install twine; \
	fi
	twine check dist/*

upload: check-package
	@echo "Uploading to PyPI..."
	@if [ -z "$$PYPI_TOKEN" ]; then \
		echo "Error: PYPI_TOKEN environment variable is not set."; \
		echo "Usage: PYPI_TOKEN=your-token make upload"; \
		exit 1; \
	fi
	@if [ -n "$(UV)" ]; then \
		uv pip install twine; \
	else \
		$(PIP_CMD) install twine; \
	fi
	twine upload dist/* \
		--username __token__ \
		--password $$PYPI_TOKEN

upload-test: check-package
	@echo "Uploading to TestPyPI..."
	@if [ -z "$$TEST_PYPI_TOKEN" ]; then \
		echo "Error: TEST_PYPI_TOKEN environment variable is not set."; \
		echo "Usage: TEST_PYPI_TOKEN=your-token make upload-test"; \
		exit 1; \
	fi
	@if [ -n "$(UV)" ]; then \
		uv pip install twine; \
	else \
		$(PIP_CMD) install twine; \
	fi
	twine upload dist/* \
		--repository testpypi \
		--username __token__ \
		--password $$TEST_PYPI_TOKEN

docs:
	@if [ -n "$(UV)" ]; then \
		uv sync --group docs --all-extras; \
	fi
	cd docs && $(PYTHON_CMD) -m sphinx -M html source build

html:
	@if [ -n "$(UV)" ]; then \
		uv sync --group docs --all-extras; \
	fi
	cd docs && $(PYTHON_CMD) -m sphinx -M html source build

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	find . -type d -name __pycache__ -exec rm -r {} +
	find . -type f -name "*.pyc" -delete
	@if [ -n "$(UV)" ]; then \
		echo "Note: To clean uv virtual environment, run: uv venv --clear"; \
	fi

clean-docs:
	cd docs && make clean

# Pre-commit hooks
pre-commit-install:
	@echo "📦 Installing pre-commit hooks..."
	@$(PYTHON_CMD) -m pip install pre-commit
	@$(PYTHON_CMD) -m pre-commit install
	@echo "✅ Pre-commit hooks installed!"

pre-commit-run:
	@echo "🔍 Running pre-commit hooks on all files..."
	@$(PYTHON_CMD) -m pre-commit run --all-files

pre-commit-update:
	@echo "🔄 Updating pre-commit hooks..."
	@$(PYTHON_CMD) -m pre-commit autoupdate
	@echo "✅ Pre-commit hooks updated!"

# Install additional development tools
install-tools:
	@echo "📦 Installing additional development tools..."
	@if [ -n "$(UV)" ]; then \
		uv add --dev \
			pre-commit \
			bandit \
			pip-audit \
			coverage; \
	else \
		$(PIP_CMD) install pre-commit bandit pip-audit coverage; \
	fi
	@echo "✅ Development tools installed!"

# Clean all artifacts
clean-all: clean clean-docs
	@echo "🧹 Cleaning all build artifacts and cache files..."
	@rm -rf .pytest_cache
	@rm -rf .ruff_cache
	@rm -rf .coverage
	@rm -rf htmlcov
	@rm -rf .pre-commit-cache
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@echo "✓ Clean complete"
