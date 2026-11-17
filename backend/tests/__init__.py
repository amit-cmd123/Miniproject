"""Test package setup.

Every setting the application reads is pinned here, before any test module
imports `app`, because `app.core.config` reads the repository's `.env` at
import time and caches the result.

Without this, adding a real API key to `.env` silently turns the unit suite
into a suite that calls Google: slow, costing money, failing when the network
does, and - worst - passing for reasons that have nothing to do with the code
under test. That happened once; this file is why it cannot happen again.

Tests that want a cloud provider construct it explicitly with a fake key and
patch the transport, as `test_gemini_provider.py` does.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Deterministic, offline engines. Set, not defaulted: an inherited value from
# the developer's shell would defeat the point.
os.environ["EVALNOVA_OCR_PROVIDER"] = "mock"
os.environ["EVALNOVA_EVALUATION_PROVIDER"] = "mock"
os.environ["EVALNOVA_GEMINI_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""

# A scratch database file, so a run never touches the development data.
#
# Not `:memory:`, which looks like the obvious choice and is not: SQLite gives
# every *connection* its own in-memory database, and FastAPI's TestClient
# serves requests on a different thread from the one that created the tables.
# The result is "no such table" on the first request. A temporary file is
# shared across connections, which is what these tests need.
_SCRATCH = Path(tempfile.gettempdir()) / "evalnova_tests.db"
_SCRATCH.unlink(missing_ok=True)
os.environ["EVALNOVA_DATABASE_URL"] = f"sqlite:///{_SCRATCH.as_posix()}"
