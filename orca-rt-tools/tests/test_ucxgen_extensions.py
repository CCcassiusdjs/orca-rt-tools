"""rttools.ucxgen and rttools.paper.rtlapp with the three manifests of the
generator: one release period (with or without --bodies), time-triggered
(general phase model) and composition of applications."""
import os

import pytest

from tests.conftest import REPO_ROOT
from rttools.paper import rtlapp
from rttools.ucxgen import __main__ as gcli
from rttools.ucxgen import emit, model

APPS = os.path.join(REPO_ROOT, "apps")
APP_DIR = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os", "app")
EXP = os.path.join(REPO_ROOT, "experiments")
CF_CSV = os.path.join(APPS, "car-full", "car-full.csv")
CF_MAP = os.path.join(APPS, "car-full", "car-full-ONTO-hermes4x4.map")
E_CSV = os.path.join(APPS, "synthetic-app-e", "synthetic-app-e.csv")
CARV_CSV = os.path.join(APPS, "car-v", "car-v.csv")
WE = os.path.join(APPS, "wcet-e")


def stored(name):
    return {f"{name}.{x}": open(os.path.join(APP_DIR, f"{name}.{x}")).read() for x in ("c", "json", "sim")}


def test_the_generated_applications_of_the_three_extensions():
    """car_v (one period), car_full (time-triggered), wcet_e (--bodies) and
    carv_e (composition) from one process match the stored files."""
    ms = {
        "car_v": model.build(CARV_CSV, os.path.join(APPS, "car-v", "car-v-ONTO-hermes4x4.map"), "car_v"),
        "car_full": model.build(CF_CSV, CF_MAP, "car_full"),
        "wcet_e": model.build(os.path.join(WE, "wcet-e.csv"), os.path.join(WE, "wcet-e-ONTO-hermes2x2.map"),
                              "wcet_e", mesh="2x2", bodies=os.path.join(WE, "wcet-e.bodies.json")),
        "carv_e": model.compose([("CARV", CARV_CSV, os.path.join(EXP, "multiapp", "maps", "CARV.map")),
                                 ("E", E_CSV, os.path.join(EXP, "multiapp", "maps", "E.map"))],
                                "carv_e", mesh="4x5"),
    }
    assert ms["car_full"]["model"] == "time_triggered" and "bodies" in ms["wcet_e"] and ms["carv_e"]["apps"]
    for name, m in ms.items():
        assert gcli.outputs(m) == stored(name), name


def test_bodies_on_a_time_triggered_application():
    with pytest.raises(model.GenError, match="--bodies applies to applications with one release period"):
        model.build(CF_CSV, CF_MAP, "x", bodies=os.path.join(WE, "wcet-e.bodies.json"))


def test_composition_of_a_time_triggered_application():
    with pytest.raises(model.GenError, match="applications CF follow the general phase model"):
        model.compose([("CF", CF_CSV, CF_MAP), ("E", E_CSV, os.path.join(EXP, "multiapp", "maps", "E.map"))],
                      "x", mesh="4x5")


def test_rtlapp_app_option_on_a_time_triggered_manifest(tmp_path, capsys):
    man = os.path.join(APP_DIR, "car_full.json")
    with pytest.raises(SystemExit) as e:
        rtlapp.main(["analyze", str(tmp_path / "events.txt"), "--manifest", man, "--csv", CF_CSV, "--map", CF_MAP,
                     "--out", str(tmp_path), "--app", "CF"])
    assert e.value.code == 2
    assert "the manifest is a time-triggered application" in capsys.readouterr().err


def test_c_source_dispatch():
    """emit.c_source picks the pattern from the manifest."""
    tt = model.build(CF_CSV, CF_MAP, "car_full")
    assert "ucx_app_tick" in emit.c_source(tt)
    we = model.build(os.path.join(WE, "wcet-e.csv"), os.path.join(WE, "wcet-e-ONTO-hermes2x2.map"), "wcet_e",
                     mesh="2x2", bodies=os.path.join(WE, "wcet-e.bodies.json"))
    assert "body_sort" in emit.c_source(we) and "ucx_app_tick" not in emit.c_source(we)
