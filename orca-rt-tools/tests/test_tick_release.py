"""Release by tick (pkt-sim/software/ucx-os/lib/tick_release.c): the phase
index n(v) in application E and in the generated applications, the data
path of the generated code, the setup files and RUN_INFO of simulate.sh,
the static t(v) of an image with the release by tick (rttools.wcet), and
the conformance of a run with the phase model (rttools.paper.phasecheck)."""
import json
import os
import re
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT, run_module
from rttools.paper import exp23, phasecheck, rtlapp
from rttools.ucxgen import emit, model

UCX = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os")
APP_DIR = os.path.join(UCX, "app")
EXP = os.path.join(REPO_ROOT, "experiments")
APPS = os.path.join(REPO_ROOT, "apps")
CARV_CSV = os.path.join(APPS, "car-v", "car-v.csv")
CARV_MAP = os.path.join(APPS, "car-v", "car-v-ONTO-hermes4x4.map")
E_CSV = os.path.join(APPS, "synthetic-app-e", "synthetic-app-e.csv")
WCETE = os.path.join(APPS, "wcet-e")
PARTS = [("CARV", CARV_CSV, os.path.join(EXP, "multiapp", "maps", "CARV.map")),
         ("E", E_CSV, os.path.join(EXP, "multiapp", "maps", "E.map"))]


def e_config(f_clk=434912000):
    cfg = exp23.load_config(os.path.join(EXP, "exp23", "config.json"))
    cfg["clock_hz"] = f_clk
    return cfg


# ---------------------------------------------------------------- application E


def test_weird_a_phase_constants_are_the_model():
    src = open(os.path.join(APP_DIR, "weird_a.c")).read()
    n = {m[0]: int(m[1]) for m in re.findall(r"^#define N_([A-J]) (\d+)$", src, re.M)}
    assert n == exp23.response_bound(e_config())["phases"]
    # every task waits for its phase before it reads its input; A has no voluntary sleep
    for t in "BCDEFGHI":
        assert f"PHASE_WAIT(N_{t}, k + 1);\n    recv_and_print();" in src
    assert "PHASE_WAIT(N_J, done + 1);" in src and "PHASE_WAIT(N_A, k + 1);" in src


def test_weird_a_setup_and_makefile():
    sim = open(os.path.join(APP_DIR, "weird_a.sim")).read()
    cfg = e_config()
    nodes = [int(pe.split("-")[1]) * 2 + int(pe.split("-")[0]) for pe in cfg["pe_tasks"]]
    assert re.search(r"^RELEASE_MASK=(\d+)$", sim, re.M)[1] == str(sum(1 << n for n in nodes)) == "15"
    assert "\nMESH=2x2\n" in sim and sim.endswith("TICK_RELEASE=1\n")
    mk = open(os.path.join(UCX, "Makefile")).read()
    assert "TR_DEFS = -DUCX_APP_IRQ4 -DUCX_APP_TICK -DUCX_TICK_RELEASE" in mk
    assert "$(CC) $(CFLAGS) $(TR_DEFS) -o $(BUILD_APP_DIR)/weird_a.o app/weird_a.c" in mk
    assert "weird_a_data: incl ucx.pack\n\t$(CC) $(CFLAGS) -o $(BUILD_APP_DIR)/weird_a.o app/weird_a.c" in mk
    assert "$(CC) $(CFLAGS) $(TR_DEFS) -o $(BUILD_APP_DIR)/$@.o app/$@.c" in mk


# ---------------------------------------------------------------- generator


def unifdef(text, macro="UCX_TICK_RELEASE"):
    """`text` preprocessed without `macro` (only the #ifdef/#ifndef/#else/
    #endif lines of the macro), and without the paragraph of the release by
    tick in the header comment."""
    out, stack = [], []
    for line in text.splitlines(keepends=True):
        s = line.strip()
        if s in (f"#ifdef {macro}", f"#ifndef {macro}"):
            stack.append(s.startswith("#ifndef"))
            continue
        if s.startswith("#if"):                 # another macro: kept as it is
            stack.append(None)
        elif stack and stack[-1] is not None and s == "#else":
            stack[-1] = not stack[-1]
            continue
        elif stack and s == "#endif":
            if stack.pop() is not None:
                continue
        if all(x is not False for x in stack):
            out.append(line)
    text = "".join(out)
    head = {"UCX_TICK_RELEASE": " *\n * Release by tick", "UCX_NOC_TT": " *\n * Time-triggered injection"}.get(macro)
    a = text.find(head) if head else -1
    if a >= 0:
        b = text.find(" *\n *", a + 1)
        end = text.index(" */\n", a)
        text = text[:a] + text[b if 0 <= b < end else end:]
    return text


@pytest.mark.parametrize("name", ["car_v", "wcet_e", "carv_e", "e_ucx"])
def test_data_path_of_the_generated_code(name):
    """Without UCX_NOC_TT and UCX_TICK_RELEASE, the stored code (release by
    tick and time-triggered injection, the default of the generator) is the
    code of the data-driven release (--release data): the code of runs CV,
    CV2 and MA. The time-triggered injection (UCX_NOC_TT) is removed first:
    it needs the release by tick."""
    if name == "e_ucx":
        e_map2 = os.path.join(APPS, "synthetic-app-e", "synthetic-app-e-ONTO-hermes2x2.map")
        tick = model.build(E_CSV, e_map2, "e_ucx", mesh="2x2")
        data = model.build(E_CSV, e_map2, "e_ucx", mesh="2x2", release_rule=model.DATA)
    elif name == "carv_e":
        tick = model.compose(PARTS, "carv_e", mesh="4x5")
        data = model.compose(PARTS, "carv_e", mesh="4x5", release_rule=model.DATA)
    elif name == "car_v":
        tick = model.build(CARV_CSV, CARV_MAP, "car_v", mesh="4x4")
        data = model.build(CARV_CSV, CARV_MAP, "car_v", mesh="4x4", release_rule=model.DATA)
    else:
        args = (os.path.join(WCETE, "wcet-e.csv"), os.path.join(WCETE, "wcet-e-ONTO-hermes2x2.map"), "wcet_e")
        bodies = os.path.join(WCETE, "wcet-e.bodies.json")
        tick = model.build(*args, mesh="2x2", bodies=bodies)
        data = model.build(*args, mesh="2x2", bodies=bodies, release_rule=model.DATA)
    src = emit.c_source(tick)
    assert src == open(os.path.join(APP_DIR, f"{name}.c")).read()
    assert unifdef(unifdef(src, "UCX_NOC_TT")) == emit.c_source(data)
    assert "ucx_phase_wait(done + 1 + TASK_PHASE[t - TASKS]);" in src
    assert "TICK_RELEASE" not in emit.c_source(data) and "rule" not in data["release"]
    # the release by tick keeps the source PEs and adds every PE with a task
    assert tick["release"]["pes"] == data["release"]["pes"]
    assert tick["release"]["tick_pes"] == sorted({t["pe"] for t in tick["tasks"]})
    assert emit.sim_setup(tick).endswith(f"RELEASE_MASK={tick['release']['tick_mask']}\nTICK_RELEASE=1\n")
    assert emit.sim_setup(data).endswith(f"RELEASE_MASK={data['release']['mask']}\n")


def test_generated_phases_are_the_model():
    m = json.load(open(os.path.join(APP_DIR, "car_v.json")))
    app = rtlapp.load_app(os.path.join(APP_DIR, "car_v.json"), CARV_CSV, CARV_MAP)
    mdl = rtlapp.model(app, 380000000)
    assert {t["name"]: t["phase"] for t in m["tasks"]} == {v: d["phase"] for v, d in mdl["tasks"].items()}
    assert m["release"]["tick_mask"] == 65535 and m["release"]["mask"] == 2494
    src = open(os.path.join(APP_DIR, "car_v.c")).read()
    table = re.search(r"TASK_PHASE\[N_TASKS\] = \{([^}]*)\}", src)[1]
    assert [int(x) for x in table.split(",")] == [t["phase"] for t in m["tasks"]]
    # composition: phase of each task in the model of its application
    c = json.load(open(os.path.join(APP_DIR, "carv_e.json")))
    e = {t["name"]: t["phase"] for t in c["tasks"] if t["app"] == "E"}
    assert e == exp23.response_bound(e_config())["phases"]
    assert c["release"]["tick_mask"] == (1 << 20) - 1


def test_cli_release_option(tmp_path):
    for rule, mask in (("tick", "65535\nTICK_RELEASE=1"), ("data", "2494")):
        out = tmp_path / rule
        r = run_module("rttools.ucxgen", "generate", CARV_CSV, CARV_MAP, "--name", "car_v", "--mesh", "4x4",
                       "--out", str(out), "--release", rule)
        assert r.returncode == 0, r.stderr
        assert (out / "car_v.sim").read_text().endswith(f"RELEASE_MASK={mask}\n")
    r = run_module("rttools.ucxgen", "check", CARV_CSV, CARV_MAP, "--name", "car_v", "--mesh", "4x4",
                   "--out", str(tmp_path / "data"))
    assert r.returncode == 1                     # the default rule (tick) differs from the data files
    with pytest.raises(model.GenError):
        model.build(CARV_CSV, CARV_MAP, "car_v", release_rule="time")


# ---------------------------------------------------------------- simulate.sh


def test_simulate_release_line(tmp_path):
    from tests.test_simulate_options import stub_repo, run_do
    repo, env, log = stub_repo(tmp_path)
    shutil.copy2(os.path.join(APP_DIR, "weird_a.sim"), repo / "pkt-sim" / "software" / "ucx-os" / "app")
    sh = str(repo / "experiments" / "exp23" / "simulate.sh")
    r = subprocess.run(["bash", sh, str(tmp_path / "o"), "1000"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "vsim -c work.manycore_top work.chk_binds +RUN_NS=1000 -gRELEASE_MASK=15\n" in run_do(tmp_path / "o")
    info = (tmp_path / "o" / "RUN_INFO").read_text()
    assert "app=weird_a mesh=2x2 generics=-gRELEASE_MASK=15\n" in info and info.endswith("release=tick\n")
    # weird_a_data: the vsim command of run F
    r = subprocess.run(["bash", sh, str(tmp_path / "d"), "1000", "weird_a_data"], capture_output=True, text=True,
                       env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "vsim -c work.manycore_top work.chk_binds +RUN_NS=1000\n" in run_do(tmp_path / "d")
    assert (tmp_path / "d" / "RUN_INFO").read_text().endswith("release=data\n")
    assert "-s weird_a_data" in log.read_text()


# ---------------------------------------------------------------- phase conformance


def test_release_rule():
    assert phasecheck.release_rule({}) == "data"
    assert phasecheck.release_rule({"release": "tick"}) == "tick"
    assert phasecheck.release_rule({"release": "tick"}, "data") == "data"
    assert phasecheck.release_rule({}, "auto") == "data"
    with pytest.raises(ValueError):
        phasecheck.release_rule({"release": "x"})
    with pytest.raises(ValueError):
        phasecheck.release_rule({}, "x")


def test_conformance_of_run_h(tmp_path):
    """Run H (weird_a_data): 32 of 33 phases with a task that runs twice."""
    m = exp23.analyze(os.path.join(EXP, "exp23", "logs", "H.events.txt"), e_config(500000000),
                      str(tmp_path / "H"))
    pc = m["phase_conformance"]
    assert pc["release"] == "data" and pc["phases"] == 33 and pc["phases_with_a_task_twice"] == 32
    assert not pc["conforms"]
    assert {v for v, t in pc["tasks"].items() if t["phases_twice"]} == set("CEGHIJ")
    assert pc["tasks"]["A"]["phases_twice"] == 0 and pc["tasks"]["A"]["early"] == 0
    assert pc["pes"]["1-0"]["phases_above"] == 16 and pc["pes"]["1-0"]["bound_max"] == 173370
    r = run_module("rttools.paper.phasecheck", str(tmp_path / "H" / "metrics.json"))
    assert r.returncode == 1 and "32 phases with a task twice" in r.stdout
    # a log without ITER lines (run F) has no conformance
    m = exp23.analyze(os.path.join(EXP, "exp23", "logs", "F.events.txt"), e_config(500000000),
                      str(tmp_path / "F"))
    assert m["phase_conformance"] is None
    r = run_module("rttools.paper.phasecheck", str(tmp_path / "F" / "metrics.json"))
    assert r.returncode == 2


def test_conformance_of_run_cv2(tmp_path):
    m = rtlapp.analyze(os.path.join(EXP, "car-v-rtl", "logs", "CV2.events.txt"),
                       os.path.join(APP_DIR, "car_v.json"), CARV_CSV, CARV_MAP, str(tmp_path), release_rule="data")
    pc = m["phase_conformance"]
    assert (pc["phases"], pc["phases_with_a_task_twice"], pc["release"]) == (16, 14, "data")
    assert m["releases"]["acks"]["pes_expected"] == 8
    # the same log read as a run with the release by tick expects the acknowledgment of every PE
    assert rtlapp.release_acks(os.path.join(EXP, "car-v-rtl", "logs", "CV2.events.txt"),
                               {"manifest": json.load(open(os.path.join(APP_DIR, "car_v.json")))},
                               "tick")["pes_expected"] == 16


class Slice:
    def __init__(self, start, end, label):
        self.start, self.end, self.label = start, end, label


class FakeTrace:
    """Two PEs, phases of 100 units from 0; `slices`: {lane: [(start, end, label)]}."""

    def __init__(self, slices, t1):
        self.slices = {k: [Slice(*s) for s in v] for k, v in slices.items()}
        self.t0, self.t1 = 0, t1

    def lane_slices(self, lane):
        return self.slices.get(lane, [])

    def slices_between(self, lane, t0, t1):
        return [s for s in self.lane_slices(lane) if s.end > t0 and s.start < t1]

    def is_idle(self, s):
        return s.label == "IDLE"


class FakeClock:
    def cycles(self, raw):
        return raw

    def ms(self, raw):
        return raw / 1000


def run_conformance(slices, begins, demand=60):
    tr = FakeTrace(slices, 400)
    n = {"U": 0, "V": 1}
    return phasecheck.conformance(tr, FakeClock(), [0, 100, 200, 300, 400], begins,
                                  lambda v, j: j - 1 + n[v], {"U": "0-0", "V": "1-0"},
                                  lambda pe, p: demand, "tick")


def test_conformance_rules():
    # U (n = 0) serves j in phase j - 1, V (n = 1) in phase j: conforms
    slices = {"0-0": [(p, p + 50, "U") for p in (0, 100, 200, 300)],
              "1-0": [(p, p + 40, "V") for p in (100, 200, 300)]}
    begins = {"U": {1: 0, 2: 100, 3: 200, 4: 300}, "V": {1: 100, 2: 200, 3: 300}}
    pc = run_conformance(slices, begins)
    assert pc["conforms"] and pc["phases"] == 4 and pc["jobs"] == 7
    assert pc["tasks"]["V"]["max_jobs_per_phase"] == 1 and pc["pes"]["0-0"]["busy_max"] == 50
    # V serves iterations 1 and 2 in phase 1: twice, and iteration 2 is early
    b2 = {"U": begins["U"], "V": {1: 100, 2: 150, 3: 300}}
    pc = run_conformance(slices, b2)
    assert pc["phases_with_a_task_twice"] == 1 and pc["early_jobs"] == 1 and not pc["conforms"]
    assert pc["rows"] == [{"phase": 1, "start_ms": 0.1, "twice": ["V"], "cpu_above": []}]
    # V begins iteration 2 in phase 3 instead of 2: late, reported and not checked
    pc = run_conformance({"0-0": slices["0-0"], "1-0": [(p, p + 40, "V") for p in (100, 200)]},
                         {"U": begins["U"], "V": {1: 100, 2: 300}})
    assert pc["late_jobs"] == 1 and pc["tasks"]["V"]["late"] == 1 and pc["conforms"]
    # CPU of PE 0-0 above the bound in every phase
    pc = run_conformance(slices, begins, demand=40)
    assert pc["phases_cpu_above"] == 4 and pc["pes"]["0-0"]["excess_max"] == 10 and not pc["conforms"]
    assert pc["tasks"]["U"]["max_dispatches_per_phase"] == 1


def test_cli_conforming_run(tmp_path):
    slices = {"0-0": [(p, p + 50, "U") for p in (0, 100, 200, 300)], "1-0": []}
    pc = run_conformance(slices, {"U": {1: 0, 2: 100, 3: 200, 4: 300}})
    p = tmp_path / "metrics.json"
    p.write_text(json.dumps({"phase_conformance": pc}))
    r = run_module("rttools.paper.phasecheck", str(p))
    assert r.returncode == 0 and "conforms" in r.stdout


# ---------------------------------------------------------------- static t(v)


def test_static_costs_with_the_release_by_tick():
    """Image with the release by tick: the release interrupt on every PE
    (release term in every t(v)), the tick hook inside the tick term, and
    the same terms otherwise; t(V_k) stays below the CSV costs of E."""
    pytest.importorskip("elftools")
    pytest.importorskip("scipy")
    from rttools.wcet.__main__ import load_spec, run_spec
    spec = load_spec(os.path.join(EXP, "wcet", "specs", "weird_a_H.json"))
    spec["annotations"] = [a for a in spec["annotations"] if not a.endswith("H.image.json")]
    img = os.path.join(EXP, "wcet", "images", "tick")
    data = run_spec(spec, os.path.join(img, "weird_a_data.elf"))
    tick = run_spec(spec, os.path.join(img, "weird_a.elf"))
    assert (data["release_rule"], tick["release_rule"]) == ("data", "tick")
    assert all(t["terms"]["release"] == tick["kernel"]["release"] for t in tick["tasks"].values())
    assert [v for v, t in data["tasks"].items() if t["terms"]["release"]] == ["A"]
    assert tick["kernel"]["tick"] > data["kernel"]["tick"]
    est = exp23.estimates(e_config())
    for cluster, tasks in exp23.dispatch_sequences(e_config()).items():
        st = sum(tick["tasks"][v]["t"] for v in tasks)
        assert sum(data["tasks"][v]["t"] for v in tasks) < st <= est[cluster]


# ---------------------------------------------------------------- build


def test_build_weird_a_and_weird_a_data(tmp_path):
    """weird_a links the release by tick (lib/tick_release.c and its tick
    hook); weird_a_data links the release of A by the kernel handler of
    PE 0 (the image of runs A to H)."""
    from tests.test_ucxgen_carv import build, toolchain
    path = toolchain(tmp_path)
    if path is None:
        pytest.skip("riscv64-elf toolchain ausente")
    ucx = tmp_path / "ucx-os"
    shutil.copytree(UCX, ucx, ignore=shutil.ignore_patterns("*.o", "*.pack", "image.*", "code.txt"))
    target = ucx / "build" / "target"
    env = {**os.environ, "PATH": path}

    def syms():
        return subprocess.run(["riscv64-elf-nm", str(target / "image.elf")], capture_output=True, text=True,
                              env=env).stdout
    tick = build(ucx, "weird_a", path)
    s = syms()
    for f in ("ucx_phase_wait", "ucx_app_tick", "irq4_handler"):
        assert re.search(rf" T {f}$", s, re.M), f
    data = build(ucx, "weird_a_data", path)
    s = syms()
    assert "ucx_phase_wait" not in s and "ucx_app_tick" not in s and re.search(r" T irq4_handler$", s, re.M)
    assert tick != data
    assert build(ucx, "weird_a", path) == tick
