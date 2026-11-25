"""Run every test from its own empty folder, so nothing a test runs (like `cad2ascope run`, whose default
--repo-root is the current folder) can write into the cad2ascope repo itself."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)
