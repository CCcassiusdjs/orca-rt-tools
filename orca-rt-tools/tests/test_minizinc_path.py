"""Path of the MiniZinc model (rttools/modules/backend/minizinc/minizinc.py).

ZINC_MODEL is the absolute path of apps/CM-v20220427.mzn, so the model is
found from any current directory.
"""
import os

from rttools.modules.backend.minizinc import minizinc


def test_model_path_exists_from_any_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert os.path.isabs(minizinc.ZINC_MODEL)
    assert os.path.isfile(minizinc.ZINC_MODEL)
    assert os.path.basename(minizinc.ZINC_MODEL) == "CM-v20220427.mzn"
