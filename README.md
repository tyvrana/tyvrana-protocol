# tyvrana-protocol

Shared protocol and schemas for communication between Tyvrana core and application adapters.

## Development

Requires Python 3.12+ and uv. From this repository, create its local environment
and install the package and development dependencies:

```sh
uv sync --locked --python 3.12
```

Run the checks:

```sh
uv run --locked pytest
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
```

To format Python files, run `uv run --locked ruff format .`.
