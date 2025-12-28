.PHONY: help clean install dev-install test test-core test-builtin test-cov lint format check build sdist wheel docs html clean-docs test-rtd upload upload-test check-package

help:
	@echo "Available targets:"
	@echo ""
	@echo "Setup (run first):"
	@echo "  install       - Install the package"
	@echo "  dev-install   - Install with development dependencies (recommended)"
	@echo ""
	@echo "Testing:"
	@echo "  test          - Run all tests (main + builtin)"
	@echo "  test-core     - Run main tests only"
	@echo "  test-builtin  - Run built-in routines tests only"
	@echo "  test-cov      - Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint          - Run linting checks (flake8)"
	@echo "  format        - Format code with black"
	@echo "  check         - Run all checks (lint + format check + tests)"
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
	@echo "  test-rtd      - Test Read the Docs configuration locally"
	@echo ""
	@echo "Cleanup:"
	@echo "  clean         - Clean build artifacts"
	@echo "  clean-docs    - Clean documentation build"
	@echo ""
	@echo "Note: Always run 'make dev-install' before development or testing!"

install:
	pip install -e .

dev-install:
	pip install -e ".[dev]"

test:
	pytest tests/ routilux/builtin_routines/ -v

test-core:
	pytest tests/ -v

test-builtin:
	pytest routilux/builtin_routines/ -v

test-cov:
	pytest tests/ routilux/builtin_routines/ --cov=routilux --cov-report=html --cov-report=term

lint:
	flake8 routilux/ tests/ examples/ --max-line-length=100 --extend-ignore=E203,W503,E501

format:
	black routilux/ tests/ examples/

format-check:
	black --check routilux/ tests/ examples/

check: lint format-check test
	@echo "All checks passed!"

build: clean
	python -m build

sdist: clean
	python -m build --sdist

wheel: clean
	python -m build --wheel

check-package: build
	@echo "Checking package..."
	pip install twine
	twine check dist/*

upload: check-package
	@echo "Uploading to PyPI..."
	@if [ -z "$$PYPI_TOKEN" ]; then \
		echo "Error: PYPI_TOKEN environment variable is not set."; \
		echo "Usage: PYPI_TOKEN=your-token make upload"; \
		exit 1; \
	fi
	pip install twine
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
	pip install twine
	twine upload dist/* \
		--repository testpypi \
		--username __token__ \
		--password $$TEST_PYPI_TOKEN

docs:
	cd docs && make html

html:
	cd docs && make html

test-rtd:
	@echo "Testing Read the Docs configuration locally..."
	@echo "Step 1: Installing package with docs dependencies..."
	pip install -e ".[docs]"
	@echo "Step 2: Building documentation (simulating Read the Docs build)..."
	@echo "  Note: Warnings are allowed (Read the Docs uses fail_on_warning: false)"
	cd docs && sphinx-build -b html source build/html || { \
		echo "✗ Documentation build failed! Check errors above."; \
		exit 1; \
	}
	@echo "Step 3: Checking for build output..."
	@if [ -f docs/build/html/index.html ]; then \
		echo "✓ Documentation built successfully!"; \
		echo "  Output: docs/build/html/index.html"; \
		echo "  To view: python3 -m http.server 8000 -d docs/build/html"; \
	else \
		echo "✗ Build output not found!"; \
		exit 1; \
	fi

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	find . -type d -name __pycache__ -exec rm -r {} +
	find . -type f -name "*.pyc" -delete

clean-docs:
	cd docs && make clean

