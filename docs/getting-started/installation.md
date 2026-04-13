# Installation

## Requirements

- Python 3.10 or newer
- A dedicated Backoffice bot user with Administrator rights and full site access

## Install from GitHub

```bash
pip install git+https://github.com/christopher-nance/Sonnys-Backoffice-Wrapper.git
```

For production use, pin to a tag:

```bash
pip install git+https://github.com/christopher-nance/Sonnys-Backoffice-Wrapper.git@v0.1.0
```

## Verify

```python
import sonnys_backoffice

print(sonnys_backoffice.__version__)
```

## Development install

If you're working on the library itself, clone the repo and install with the dev extras:

```bash
git clone https://github.com/christopher-nance/Sonnys-Backoffice-Wrapper.git
cd Sonnys-Backoffice-Wrapper
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

The `docs` extras install MkDocs Material + mkdocstrings for local doc builds:

```bash
.venv/bin/pip install -e ".[docs]"
.venv/bin/mkdocs serve
```
