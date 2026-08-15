from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def sandbox_path() -> Path:
    root = Path.cwd() / ".test-data"
    root.mkdir(mode=0o777, exist_ok=True)
    path = root / uuid4().hex
    path.mkdir(mode=0o777)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
