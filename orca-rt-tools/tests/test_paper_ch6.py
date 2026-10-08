"""Tables 6.5 to 6.7 pipeline (rttools/paper/ch6.py), default applications."""
import json
import os

from tests.conftest import REPO_ROOT
from rttools.paper import ch6

EXP = os.path.join(REPO_ROOT, "experiments", "ch6")


def test_default_run_matches_reference(tmp_path):
    with open(os.path.join(EXP, "config.json")) as f:
        cfg = json.load(f)
    m = ch6.run(cfg, str(tmp_path), jobs=1)
    assert ch6.check_metrics(str(tmp_path / "metrics.json"), os.path.join(EXP, "reference.json")) == []
    cells = {(r["app"], r["criterion"], r["pf"]): r for r in m["tab66"]}
    # MBCF on DCT-Verify reproduces the thesis; with one period per
    # application, LSTF (Eq. 6.2) and MBCF (Eq. 6.3) give the same order
    assert all(cells[("dct_verify", "MBCF", pf)]["agrees"] for pf in (10, 20, 40))
    assert all(cells[("dct_verify", "LSTF", pf)]["run"] == cells[("dct_verify", "MBCF", pf)]["run"]
               for pf in (10, 20, 40))
    for f in ("tab65.tex", "tab66.tex", "tab67.tex", "tab67.csv"):
        assert (tmp_path / f).stat().st_size > 0
