# Contributing to Routilux

Thank you for your interest in contributing to Routilux!

## Development Setup

### Quick Start

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Set up development environment**:
   ```bash
   make dev-install
   ```

3. **Run tests**:
   ```bash
   make test
   ```

That's it! You're ready to contribute.

For detailed setup instructions, see [SETUP.md](SETUP.md).

## Development Workflow

### Standard Development

For active development where you need to import and use routilux:

```bash
make dev-install  # Installs package + all dependencies
make test         # Run all tests (main + builtin)
make lint         # Check code quality
make format       # Format code
```

### CI/CD or Code Review

If you only need development tools (linting, formatting) without installing the package:

```bash
make setup-venv   # Only installs dependencies, not the package
make lint         # Can still run linting
make format-check # Can still check formatting
```

**Note**: Some tests may require the package to be installed.

## Making Changes

1. **Create a branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**

3. **Run checks**:
   ```bash
   make check  # Runs lint, format-check, and tests
   ```

4. **Commit your changes**:
   ```bash
   git commit -m "Add feature: description"
   ```

5. **Push and create a pull request**

## Code Quality

- **Linting**: `make lint` (uses ruff)
- **Formatting**: `make format` (uses ruff)
- **Type checking**: `mypy` (optional, not enforced in CI)
- **Tests**: `make test` (uses pytest)

All checks must pass before submitting a PR.

## Testing

### Run all tests:
```bash
make test  # Runs both main tests and builtin routine tests
```

### Run specific test suites:
```bash
make test-core     # Run main tests only
make test-builtin  # Run built-in routines tests only
```

### Run with coverage:
```bash
make test-cov
```

### Run integration tests (requires external services):
```bash
make test-integration
```

## Documentation

### Build documentation:
```bash
make docs
```

Documentation is built using Sphinx. See `docs/` directory for source files.

## Project Structure

- `routilux/` - Main package code
- `routilux/builtin_routines/` - Built-in routine implementations
- `tests/` - Test files for main package
- `docs/` - Documentation source
- `examples/` - Example code
- `pyproject.toml` - Project configuration and dependencies

## Questions?

Feel free to open an issue or start a discussion!
