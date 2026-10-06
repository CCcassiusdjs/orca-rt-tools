"""Fix 5 (rttools/modules/backend/minizinc/minizinc.py).

ZINC_MODEL pointed to './minizinc/CM/CM-v20220427.mzn', a path
relative to the current directory and nonexistent in the repository. The model
is in apps/CM-v20220427.mzn.
"""
import os

from rttools.modules.backend.minizinc import minizinc


def test_model_path_exists_from_any_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert os.path.isabs(minizinc.ZINC_MODEL)
    assert os.path.isfile(minizinc.ZINC_MODEL)
    assert os.path.basename(minizinc.ZINC_MODEL) == "CM-v20220427.mzn"
