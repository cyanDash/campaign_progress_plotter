import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest


@pytest.fixture(autouse=True)
def _log_beside_the_test_not_in_the_repo(tmp_path, monkeypatch):
    import window_output_plotter
    monkeypatch.setattr(window_output_plotter, "default_log_path", lambda: tmp_path / "default_run.log")
