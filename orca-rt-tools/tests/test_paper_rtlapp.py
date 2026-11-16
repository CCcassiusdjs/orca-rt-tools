"""Analysis of an RTL run of a generated application (rttools.paper.rtlapp):
stored runs CV (no markers) and CV2 (ITER markers) of CAR-V against their
references and the phase model,
iterations from the tags, the response with ITER markers, the XY route
and the iteration markers of the generator."""
import json
import os
import re
import shutil

import pytest

from tests.conftest import REPO_ROOT
from rttools.paper import exp23, rtlapp
from rttools.ucxgen import emit, model as genmodel

EXP = os.path.join(REPO_ROOT, "experiments", "car-v-rtl")
LOGS = os.path.join(EXP, "logs")
APP = os.path.join(REPO_ROOT, "apps", "car-v")
CSV = os.path.join(APP, "car-v.csv")
MAP = os.path.join(APP, "car-v-ONTO-hermes4x4.map")
MANIFEST = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os", "app", "car_v.json")
ARCH = os.path.join(REPO_ROOT, "arch", "hermes-4x4.gml")
CV_LOG = os.path.join(LOGS, "CV.events.txt")
CV2_LOG = os.path.join(LOGS, "CV2.events.txt")


@pytest.fixture(scope="module")
def cv(tmp_path_factory):
    out = tmp_path_factory.mktemp("cv")
    return rtlapp.analyze(CV_LOG, MANIFEST, CSV, MAP, str(out), arch=ARCH), out


def test_cv_matches_reference(cv):
    _, out = cv
    assert exp23.check(str(out / "metrics.json"), os.path.join(EXP, "reference_CV.json")) == []
    for f in ("responses.csv", "packets.csv", "flows.csv", "cpu.csv", "tasks.csv", "network.csv",
              "network_packets.csv"):
        assert (out / f).exists(), f


def test_cv_model_at_the_clock_of_the_run(cv):
    m, _ = cv
    md = m["model"]
    assert m["clock"]["clock_hz"] == 380_000_000 and m["clock"]["source"] == "RUN_INFO"
    assert md["period_cycles"] == 190_000
    # R_bound = phi(OBMG) P + f^(OBMG) = 4 x 190,000 + 95,000
    assert md["response_bound"] == {"cycles": 855_000, "ms": 2.25, "task": "OBMG", "phase": 4}
    assert md["deadline"]["cycles"] == 950_000
    assert set(md["outputs"]) == {"NAVC", "OBMG"} and md["dispatch_matches_manifest"]
    assert m["inputs"]["csv_matches_manifest"] and m["inputs"]["map_matches_manifest"]


def test_cv_iterations_from_the_tags(cv):
    m, _ = cv
    # every send and receive of the log decodes to a flow of the manifest,
    # on the PE of the manifest, in FIFO order
    assert m["tags"] == {"unknown_tags": 0, "lane_errors": 0, "repeated": 0, "fifo_mismatch": 0}
    assert m["markers"] == 0 and m["releases"]["count"] == 17
    assert m["releases"]["acks"]["pes_min"] == m["releases"]["acks"]["pes_max"] == 8
    t = m["tasks"]
    # one run of OBMG serves iterations k - 1 and k for every even k; the
    # exit of OBMG bounds the end of k - 1 from above
    assert t["OBMG"]["source"] == "run_exit" and t["OBMG"]["same_run_as_previous"] == [2, 4, 6, 8, 10, 12, 14]
    assert t["FDF1"]["same_run_as_previous"] == list(range(2, 17, 2))


def test_cv_responses_against_the_model(cv):
    m, _ = cv
    r = m["responses"]
    rb, dl = m["model"]["response_bound"]["cycles"], m["model"]["deadline"]["cycles"]
    assert r["complete"] == 14 and r["exact"] == 7 and r["upper_bound_only"] == 7
    # exact responses (even k) below R_bound; every response below the deadline
    assert r["max_exact_cycles"] < rb and r["exact_above_bound"] == 0
    assert r["above_deadline"] == 0 and r["max_cycles"] < dl
    # the upper bounds (odd k) exceed R_bound, their lower bounds do not
    assert r["max_upper_cycles"] > rb and r["lower_above_bound"] == 0
    for row in r["rows"]:
        assert row["exact"] == (row["iteration"] % 2 == 0)


def test_cv_packets_and_network(cv):
    m, _ = cv
    p = m["packets"]
    assert p["late"] == 0 and p["remote_packets"] == 264 and p["min_slack_remote_cycles"] > 0
    n = m["network"]
    assert n["packets"] == 264 and n["unpaired_tx"] == n["unpaired_rx"] == n["identity_errors"] == 0
    # header waits only on the flows that share the destination router with
    # a flow sent at the same instant; the link schedule separates them
    waits = {f["flow"]: f["contender_flows"] for f in n["flows"] if f["header_waits_above_bound"]}
    assert waits == {4: [3], 14: [13], 17: [18], 19: [20], 22: [21]}
    s = m["link_schedule"]["starts"]
    for a, b in waits.items():
        assert s[a] != s[b[0]]
    assert m["monitor"]["errors"] == 0 and m["monitor"]["nodes"] == 16


def test_cpu_windows_of_phi_plus_one_releases(cv):
    m, _ = cv
    w = m["cpu_windows"]
    assert w["releases_per_window"] == 5 and len(w["windows"]) == 2
    for pe, x in w["pes"].items():
        assert x["mean"] < x["estimated"], pe
        a = m["cpu_attributed"][pe]
        assert abs(a["measured"] - x["mean"]) / x["mean"] < 0.002, pe


@pytest.fixture(scope="module")
def cv2(tmp_path_factory):
    out = tmp_path_factory.mktemp("cv2")
    return rtlapp.analyze(CV2_LOG, MANIFEST, CSV, MAP, str(out), arch=ARCH), out


def test_cv2_matches_reference(cv2):
    _, out = cv2
    assert exp23.check(str(out / "metrics.json"), os.path.join(EXP, "reference_CV2.json")) == []


def test_cv2_markers_give_every_response(cv2):
    """Run CV2 (car_v.c with ITER markers): the end of every iteration of
    every task comes from its markers; the 14 responses are exact and below
    R_bound and the deadline."""
    m, _ = cv2
    assert m["clock"]["clock_hz"] == 380_000_000
    assert set(m["iteration_source"].values()) == {"markers"} and m["markers"] == 758
    assert m["tags"] == {"unknown_tags": 0, "lane_errors": 0, "repeated": 0, "fifo_mismatch": 0}
    r = m["responses"]
    rb, dl = m["model"]["response_bound"]["cycles"], m["model"]["deadline"]["cycles"]
    assert r["complete"] == r["exact"] == 14 and r["upper_bound_only"] == 0
    assert r["above_bound"] == 0 and r["above_deadline"] == 0
    assert r["max_cycles"] == 845_952 and rb - r["max_cycles"] == 9_048
    # the run of OBMG still serves k - 1 and k for even k; the marker splits it
    assert m["tasks"]["OBMG"]["same_run_as_previous"] == [2, 4, 6, 8, 10, 12, 14]
    odd = [x["response_cycles"] for x in r["rows"] if x["iteration"] % 2]
    assert max(odd) < rb < dl
    assert m["packets"]["late"] == 0 and m["monitor"]["errors"] == 0


def test_unwrap_iterations():
    assert rtlapp.unwrap_iterations([1, 2, 3], 1024) == [1, 2, 3]
    assert rtlapp.unwrap_iterations(list(range(1, 1024)) + [0, 1], 1024)[-3:] == [1023, 1024, 1025]
    assert rtlapp.unwrap_iterations([0, 0, 0], 1) == [1, 2, 3]
    assert rtlapp.unwrap_iterations([5, 7], 1024) == [5, 7]


def test_xy_links():
    assert rtlapp.xy_links("3-0", "2-3") == [("3-0", "2-0"), ("2-0", "2-1"), ("2-1", "2-2"), ("2-2", "2-3"),
                                             ("2-3", "local")]
    a, b = set(rtlapp.xy_links("2-0", "2-3")), set(rtlapp.xy_links("3-0", "2-3"))
    assert ("2-2", "2-3") in a & b and ("3-0", "2-0") not in a


def _edge_ns(t_ns, half_fs):
    """An integer ns within half a unit of a rising edge near t_ns."""
    period = 2 * half_fs
    n = round((t_ns * 10 ** 6 - half_fs) / period)
    return round((2 * n + 1) * half_fs / 10 ** 6)


def test_markers_give_the_end_of_each_iteration(tmp_path):
    """ITER lines of OBMG inside the runs that serve two iterations: the
    response of each iteration ends at the end marker and is exact."""
    info = exp23.read_run_info(os.path.join(LOGS, "CV.RUN_INFO"))
    half = int(info["clock_half_period_fs"])
    letter = next(t["iter_letter"] for t in json.load(open(MANIFEST))["tasks"] if t["name"] == "OBMG")
    lines = open(CV_LOG).read().splitlines()
    sched = [(int(m.group(1)), int(m.group(2))) for m in
             (re.match(r"# (\d+) 3-3 scheduled (\d+)$", s) for s in lines) if m]
    runs = [(a, b) for (a, i), (b, _) in zip(sched, sched[1:]) if i == 1 and a > 3_000_000]
    extra = []
    k = 0
    for a, b in runs:
        mid = _edge_ns((a + b) // 2, half)
        for edge, t in (("begin", _edge_ns(a + 10, half)), ("end", mid), ("begin", _edge_ns(mid + 10, half)),
                        ("end", _edge_ns(b - 10, half))):
            if edge == "begin":
                k += 1
            extra.append((t, f"# {t} 3-3 ITER {edge} {letter} {k}"))
    body = sorted([(int(re.match(r"# (\d+)", s).group(1)) if re.match(r"# \d+ ", s) else -1, s) for s in lines]
                  + extra, key=lambda x: x[0])
    log = tmp_path / "M.events.txt"
    log.write_text("\n".join(s for _, s in body) + "\n")
    shutil.copy(os.path.join(LOGS, "CV.RUN_INFO"), tmp_path / "M.RUN_INFO")
    m = rtlapp.analyze(str(log), MANIFEST, CSV, MAP, str(tmp_path / "out"))
    assert m["markers"] == 4 * len(runs) and m["tasks"]["OBMG"]["source"] == "markers"
    r = m["responses"]
    assert r["upper_bound_only"] == 0 and r["exact"] == r["complete"] == 2 * len(runs)
    tr, clk, _ = rtlapp.load_log(str(log), rtlapp.load_app(MANIFEST, CSV, MAP))
    r1 = min(mk.time for mk in tr.lane_marks("TRIGGER"))
    end1 = next(x["time"] for x in tr.meta["iterations"] if x["edge"] == "end" and x["iteration"] == 1)
    row1 = r["rows"][0]
    assert row1["iteration"] == 1 and row1["response_cycles"] == exp23.exact(clk.cycles(end1 - r1))
    assert row1["response_cycles"] < m["model"]["response_bound"]["cycles"]


def test_generator_writes_markers_with_one_letter_per_task(tmp_path):
    m = json.load(open(MANIFEST))
    letters = [t["iter_letter"] for t in m["tasks"]]
    assert len(set(letters)) == len(letters) and all(re.fullmatch("[A-Za-z]", x) for x in letters)
    src = emit.c_source(m)
    assert src.count("ITER_BEGIN(t->letter, done + 1);") == 1 and src.count("ITER_END(t->letter, done);") == 1
    # 53 tasks exceed the letters of the markers
    rows = "\n".join(f"{i},0,20000,0,T{i},T{i}" for i in range(1, 54))
    flows = "\n".join(f"{i},0.0005,64,0.0005,T{i},T{i + 1}" for i in range(1, 53))
    csv = tmp_path / "a.csv"
    csv.write_text("#tasks,,,,,\nTask,Period,Capacity,Deadline,Acronym,Description\n" + rows +
                   "\n#flows,,,,,\nFlow,Period,Data,Deadline,Source,Target\n" + flows +
                   "\n#parameters,,,,,\nParameter,Value,,,,\nscheduler_cycles,10000,,,,\n")
    mp = tmp_path / "a.map"
    mp.write_text("\n".join(f"{n}:" + ",".join(f"T{i}" for i in range(1, 54) if (i - 1) % 16 == n)
                            for n in range(16)) + "\n")
    with pytest.raises(genmodel.GenError, match="letters"):
        genmodel.build(str(csv), str(mp), "a", mesh="4x4")
