# Development Setup

## Quick Start

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Set up the project**:
   
   **Recommended: For active development**
   ```bash
   make dev-install
   ```
   This installs the package and all dependencies. Use this for normal development.
   
   **Alternative: Dependencies only (for CI/CD or tools)**
   ```bash
   make setup-venv
   ```
   This only installs dependencies, not the package. Useful for CI/CD or when you only need tools.

3. **Run tests**:
   ```bash
   make test
   ```

That's it! The Makefile automatically uses `uv` if available, otherwise falls back to `pip`.

## What is uv?

`uv` is an extremely fast Python package installer and resolver written in Rust. It's designed to be a drop-in replacement for `pip`, `pip-tools`, `virtualenv`, and `pipx`.

### Benefits

- ⚡ **Faster**: 10-100x faster than pip/conda
- 🔒 **Reproducible**: `uv.lock` ensures consistent builds
- 🎯 **Simple**: One tool for virtualenv, pip, and dependency management
- 🔄 **Compatible**: Works with existing `pyproject.toml`

## Common Commands

```bash
make dev-install    # Install all dependencies
make test           # Run all tests (main + builtin)
make test-core      # Run main tests only
make test-builtin   # Run built-in routines tests only
make lint           # Run linting
make format         # Format code
make docs           # Build documentation
make check          # Run all checks
```

## Understanding Dependency Groups

This project uses dependency groups for development dependencies:

- **`dev`**: Development dependencies (pytest, black, flake8, etc.) - **installed by default** with `uv sync`
- **`docs`**: Documentation dependencies (sphinx, themes, etc.) - install with `--group docs`

Dependency groups are **not published to PyPI** and are only for local development.

## Troubleshooting

### uv command not found

Make sure `~/.local/bin` is in your PATH:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Virtual environment issues

Clear and recreate:
```bash
rm -rf .venv
uv sync --group docs --all-extras
```

### Lock file conflicts

Regenerate the lock file:
```bash
rm uv.lock
uv lock
uv sync --group docs --all-extras
```

For more details, see [CONTRIBUTING.md](CONTRIBUTING.md).

