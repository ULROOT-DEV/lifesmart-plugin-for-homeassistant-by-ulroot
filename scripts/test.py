"""Run only the required pytest plugin, on the actual installed HA runtime."""

import os
import sys

# HA 2026.11 establishes its HTTPX alias before third-party plugins import HTTPX.
import homeassistant  # noqa: F401
import pytest

os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
raise SystemExit(pytest.main(["-p", "pytest_asyncio.plugin", *sys.argv[1:]]))
