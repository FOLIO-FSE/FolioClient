# Installation

FolioClient supports Python 3.10 and higher. We recommend using the latest stable version of Python.

## Basic Installation

Install FolioClient using pip:

```bash
pip install folioclient
```

## Performance Installation

## Experimental Performance Features

For improved JSON processing performance, install with the experimental orjson extra:

```bash
pip install folioclient[orjson]
```

This will install the optional `orjson` library, which provides significantly faster JSON encoding and decoding. **Note:** This feature is experimental and may have compatibility issues in some environments.

## Development Installation

To install FolioClient for development, first clone the repository:

```bash
git clone https://github.com/FOLIO-FSE/FolioClient.git
cd FolioClient
```

Then install using uv (recommended):

```bash
# Install dependencies
uv sync

# Install with development dependencies
uv sync --extra dev

# Install with performance optimizations
uv sync --extra orjson  # For experimental performance features
```

## Requirements

### Core Dependencies

* **Python 3.10+**: Required for modern async/await and type hints
* **httpx**: Modern HTTP client for sync and async requests  
* **jsonref**: JSON reference resolution for FOLIO schemas
* **pyyaml**: YAML processing support

### Optional Dependencies

* **orjson**: High-performance JSON library (experimental - recommended for testing performance improvements)

### Development Dependencies

* **pytest**: Testing framework
* **pytest-asyncio**: Async testing support
* **mypy**: Static type checking
* **ruff**: Linting and formatting
* **coverage**: Test coverage reporting

## Compatibility

FolioClient is tested against:

* **Python versions**: 3.10, 3.11, 3.12, 3.13, 3.14
* **Operating systems**: Linux, macOS, Windows
* **FOLIO versions**: All [officially supported FOLIO releases](https://folio-org.atlassian.net/wiki/spaces/TC/pages/1187348628/DR-000043+-+Support+period)

## Virtual Environment

We strongly recommend using a virtual environment:

```bash
# Create virtual environment
uv venv folio-env # or python -m venv folio-env

# Activate (Unix/macOS)
source folio-env/bin/activate

# Activate (Windows)
folio-env\Scripts\activate

# Install FolioClient
uv pip install folioclient # or pip install folioclient if not using uv
```

## Verification

Verify your installation:

```python
import folioclient
print(folioclient.__version__)

# Test basic functionality
from folioclient import FolioClient
print("FolioClient imported successfully!")
```