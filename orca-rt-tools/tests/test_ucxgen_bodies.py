"""rttools.ucxgen --bodies: application WCET-E (apps/wcet-e) with bodies whose
paths depend on the input data; the generation without --bodies keeps the
code of CAR-V."""
import json
import os

import pytest

from rttools.ucxgen import __main__ as gen
from rttools.ucxgen import emit, model
from tests.conftest import REPO_ROOT

APPS = os.path.join(REPO_ROOT, "apps", "wcet-e")
CSV = os.path.join(APPS, "wcet-e.csv")
MAP = os.path.join(APPS, "wcet-e-ONTO-hermes2x2.map")
BODIES = os.path.join(APPS, "wcet-e.bodies.json")
APP_DIR = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os", "app")


def test_stored_application_matches_the_generator():
    assert gen.main(["check", CSV, MAP, "--name", "wcet_e", "--mesh", "2x2", "--bodies", BODIES,
                     "--out", APP_DIR]) == 0


def test_bodies_in_the_manifest_and_the_code():
    m = model.build(CSV, MAP, "wcet_e", mesh="2x2", bodies=BODIES)
    kinds = {t["name"]: (t["body"], t["repeat"], t["workload"]) for t in m["tasks"]}
    assert kinds["B"] == ("sort", 1, 0) and kinds["C"] == ("count", 4, 0) and kinds["H"] == ("search", 4, 0)
    src = emit.c_source(m)
    assert "#include <lib/wcet.h>" in src and "WCET_LOOP_TOTAL" in src
    assert "BODY_SORT, 1" in src and "--bodies wcet-e.bodies.json" in src
    # n_in and n_out at bytes 12 and 13 of struct task_s (pkt-sim/software/ucx-os/wcet/ucxgen.json)
    assert "int32_t workload;               /* counts of ucx_sleep (body sleep) */\n  uint8_t n_in, n_out;" in src


def test_code_without_bodies_is_unchanged():
    csv = os.path.join(REPO_ROOT, "apps", "car-v", "car-v.csv")
    mp = os.path.join(REPO_ROOT, "apps", "car-v", "car-v-ONTO-hermes4x4.map")
    m = model.build(csv, mp, "car_v", mesh="4x4")
    assert "bodies" not in m
    assert emit.c_source(m) == open(os.path.join(APP_DIR, "car_v.c")).read()


@pytest.mark.parametrize("bad,msg", [
    ({"tasks": {"Z": {"kind": "sort"}}}, "unknown task"),
    ({"tasks": {"A": {"kind": "fft"}}}, "kind must be"),
    ({"tasks": {"A": {"kind": "sort", "repeat": 0}}}, "repeat"),
    ({"work_words": 48}, "power of two"),
])
def test_bodies_errors(tmp_path, bad, msg):
    p = tmp_path / "b.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(model.GenError, match=msg):
        model.build(CSV, MAP, "x", mesh="2x2", bodies=str(p))
