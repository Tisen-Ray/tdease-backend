"""The Backend's single in-code version constant.

`pyproject.toml` stays the release authority; this module is the only in-code
copy, so the FastAPI metadata, the `/` route and `/ready` cannot drift apart
or from the packaging version. `tests/test_serve_e2e.py` asserts the
equality — bump both together.
"""

__version__ = "0.2.0"
