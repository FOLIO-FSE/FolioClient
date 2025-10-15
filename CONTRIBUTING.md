# Contributing to FolioClient

Thank you for your interest in contributing to FolioClient! This guide will help you get started with contributing to this Python library for interacting with FOLIO Platform APIs. These are guidelines to help make collaboration easier. They are not intended to be barriers to contribution—we just ask for good-faith efforts.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Code Style](#code-style)
- [Submitting Changes](#submitting-changes)
- [Reporting Issues](#reporting-issues)
- [Documentation](#documentation)
- [Release Process](#release-process)

## Code of Conduct

By participating in this project, you agree to abide by the [FOLIO Community Code of Conduct](https://folio-org.atlassian.net/wiki/x/V5B). Please be respectful and constructive in all interactions with maintainers and other contributors.

## Getting Started

### Prerequisites

- Python 3.10 or higher (Python 3.13 recommended)
- [uv](https://github.com/astral-sh/uv) for dependency management
- Git for version control
- A FOLIO system for testing (optional, but recommended for comprehensive testing)
  - You can use the [community reference environments](https://folio-org.atlassian.net/wiki/spaces/FOLIJET/pages/513704182/Reference+environments), but please be considerate of others

### First Steps

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/yourusername/FolioClient.git
   cd FolioClient
   ```
3. **Add the upstream remote**:
   ```bash
   git remote add upstream https://github.com/FOLIO-FSE/FolioClient.git
   ```

## Development Setup

```bash
# Install dependencies (including dev and docs)
uv sync --all-groups

# Install with JSON performance optimizations
uv sync --extra orjson
```

### Environment Setup

1. **Set up environment variables** (if testing against a FOLIO system):
   ```bash
   export FOLIO_URL="https://your-folio-instance.example.com"
   export FOLIO_TENANT="your_tenant"
   export FOLIO_USERNAME="your_username"
   export FOLIO_PASSWORD="your_password"
   ```

2. **Create a `.env` file** (optional, for local development):
   ```bash
   FOLIO_URL=https://your-folio-instance.example.com
   FOLIO_TENANT=your_tenant
   FOLIO_USERNAME=your_username
   FOLIO_PASSWORD=your_password
   GITHUB_TOKEN=your_github_token  # For GitHub API tests
   ```

## Making Changes

### Branch Naming Convention

- **Feature branches**: `feature/description-of-feature`
- **Bug fixes**: `fix/description-of-bug`
- **Documentation**: `docs/description-of-update`
- **Refactoring**: `refactor/description-of-change`

### Development Workflow

1. **Create a new branch** from `master`:
   ```bash
   git checkout master
   git pull upstream master
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the code style guidelines below

3. **Commit your changes** with descriptive commit messages:
   ```bash
   git add .
   git commit -m "Add feature: description of what you added"
   ```

4. **Keep your branch up to date**:
   ```bash
   git fetch upstream
   git rebase upstream/master
   ```

5. **Keep commits clean** - Use meaningful commit messages and consider interactive rebase (`git rebase -i`) to clean up your commit history before submitting

### Commit Message Guidelines

- Prefer the present tense ("Add feature" not "Added feature")
- Prefer the imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit the first line to 72 characters or less
- Reference issues and pull requests liberally after the first line

Examples:
```
Add async support for batch operations

- Implement async_batch_get method
- Add comprehensive async tests
- Update documentation with async examples

Fixes #123
```

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src/folioclient --cov-report=html

# Run specific test file
uv run pytest tests/test_folio_client.py

# Run tests with verbose output
uv run pytest -v

# Run async tests only
uv run pytest -k "async"
```

#### Integration tests
We provide a limited set of integration tests to verify network functionality of FolioClient. These tests are not included in the standard pytest test run, and require additional configuration. By default they are run against the current community Okapi snapshot environment, Eureka snapshot environment, Eureka ECS snapshot environment, and the most recent Bugfest environment. You can specify a single environment from the available options:
* `snapshot`
* `snapshot-2`
* `eureka` (eureka snapshot)
* `eureka-ecs` (eureka snapshot ECS)
* `snapshot-2-eureka` (eureka backup snapshot)
* `bugfest` (currently Sunflower bugfest)

```bash
# Set up environment variables for integration testing
export FOLIO_SNAPSHOT_USERNAME=<snapshot_admin_usernae>
export FOLIO_SNAPSHOT_PASSWORD=<snapshot_admin_password>
export FOLIO_ECS_EUREKA_USERNAME=<eureka_ecs_snapshot_admin_username>
export FOLIO_ECS_EUREKA_PASSWORD=<eureka_ecs_snapshot_admin_password>
export FOLIO_BUGFEST_USERNAME=<bugfest_admin_username>
export FOLIO_BUGFEST_PASSWORD=<bugfest_admin_password>

# Run integration tests
uv run pytest --run-integration

# Run integration tests against snapshot only (others will be skipped)
uv run pytest --run-integration --integration-server snapshot
```

### Writing Tests

- **Location**: Add tests to the `tests/` directory
- **Naming**: Test files should be named `test_*.py`
- **Async tests**: Use `@pytest.mark.asyncio` for async test functions
- **Mocking**: Use `unittest.mock` for mocking external dependencies
- **Coverage**: Aim for high test coverage, especially for new features

Example test structure:
```python
import pytest
from unittest.mock import Mock, patch
from folioclient import FolioClient

class TestFolioClient:
    @patch.object(FolioClient, '_initial_ecs_check')
    def test_feature_name(self, mock_ecs_check):
        # Test implementation
        pass
    
    @pytest.mark.asyncio
    async def test_async_feature(self):
        # Async test implementation
        pass
```

## Code Style

### Linting and Formatting

We use **Ruff** for both linting and formatting:

```bash
# Check for linting issues
uv run ruff check

# Auto-fix linting issues
uv run ruff check --fix

# Format code
uv run ruff format

# Check formatting without applying
uv run ruff format --check
```

### Type Checking

We use **mypy** for static type checking:

```bash
# Run type checking
uv run mypy src/folioclient --ignore-missing-imports
```

### Code Style Guidelines

- **Line length**: Maximum 99 characters
- **Import sorting**: Use Ruff's import sorting
- **Type hints**: Add type hints for all function parameters and return values
- **Docstrings**: Use Google-style docstrings for all public methods
- **Async/Sync patterns**: Maintain parallel sync and async implementations where applicable

### Documentation Strings

```python
def folio_get(self, path: str, key: str | None = None, query: str = "", 
              query_params: dict = None) -> Any:
    """
    Fetches data from FOLIO and returns it as a JSON object.
    
    Args:
        path: FOLIO API endpoint path
        key: Key in JSON response that contains the array of results
        query: CQL query string for filtering results
        query_params: Additional query parameters for the request
        
    Returns:
        JSON response data, optionally filtered by key
        
    Raises:
        HTTPStatusError: If the HTTP request fails
        FolioClientClosed: If the client has been closed
        
    Example:
        >>> client.folio_get("/users", "users", "username==admin")
    """
```

## Submitting Changes

### Pull Request Process

1. **Update documentation** if you've changed APIs or added features
2. **Add or update tests** for your changes
3. **Ensure all tests pass** and linting is clean
4. **Update the changelog** if appropriate
5. **Submit a pull request** with a clear description

### Pull Request Template

```markdown
## Description
Brief description of what this PR does.

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass (if applicable)
- [ ] New tests added for new functionality

## Checklist
- [ ] Code follows the project's style guidelines
- [ ] Self-review of code completed
- [ ] Code is commented, particularly in hard-to-understand areas
- [ ] Corresponding changes to documentation have been made
- [ ] Changes generate no new warnings
```

### Review Process

1. **Automated checks** must pass (GitHub Actions, linting, tests)
2. **At least one maintainer review** is required
3. **Address feedback** promptly and professionally
4. **Clean commit history** - We use rebase and merge to maintain a linear history for all pull requests, so be sure your branch does not have conflicts with the main branch

## Reporting Issues

### Bug Reports

When reporting bugs, please include:

- **Python version** and operating system
- **FolioClient version** 
- **FOLIO system version** (if applicable)
- **Minimal code example** that reproduces the issue
- **Full error traceback** with any sensitive data removed/redacted
- **Expected vs actual behavior**

### Feature Requests

For feature requests, please include:

- **Use case description** - what problem does this solve?
- **Proposed API** - how should the feature work?
- **Alternative solutions** - what other approaches have you considered?
- **FOLIO API documentation** - links to relevant FOLIO API docs

### Security Issues

For security-related issues, please **do not** open a public issue. Instead:

1. Email the maintainers directly
2. Include a detailed description of the vulnerability
3. Provide steps to reproduce (if applicable)
4. Allow reasonable time for response before disclosure

## Documentation

### Building Documentation

```bash
# Install documentation dependencies
uv sync --group docs 

# Build documentation
cd docs
make html

# Serve documentation locally
make serve
# Open http://localhost:8000 in your browser

# Check for broken links
make linkcheck
```

### Documentation Standards

- **API documentation**: All public methods must have comprehensive docstrings
- **Examples**: Include working code examples in docstrings
- **Type hints**: All parameters and return values must be type-hinted
- **Changelog**: Update `CHANGELOG.md` for user-facing changes

## Release Process

*Note: This section is primarily for maintainers*

### Version Numbering

We follow [Semantic Versioning](https://semver.org/):

- **Major** (1.0.0): Breaking changes
- **Minor** (1.1.0): New features, backwards compatible
- **Patch** (1.1.1): Bug fixes, backwards compatible
- **Pre-release** 
  - (1.0.0b1): Beta versions
  - (1.1.0a1): Alpha versions
  - (1.1.0rc1): Release candidates

### Release Checklist

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Run full test suite, including integration tests
4. Create release tag in GitHub
   - Approve submit workflow to publish to pypi
5. Update GitHub release notes

## Getting Help

- **GitHub Issues**: For bugs, features, and questions
- **GitHub Discussions**: For general discussion and questions
- **Documentation**: Check the README and inline documentation first
- **FOLIO Community**: [FOLIO Project](https://www.folio.org/) for FOLIO-specific questions

## Recognition

Contributors will be recognized in:

- **GitHub contributors list**
- **pyproject.toml** project authors list
- **Changelog acknowledgments**
- **Release notes** (for significant contributions)

Thank you for contributing to FolioClient! Your efforts help make FOLIO integration easier for libraries worldwide. 🚀
