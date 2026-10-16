"""Time-triggered injection of the packets between PEs (pkt-sim/software/
ucx-os/lib/noc_tt.c): the network-interface model of the link schedule
(rttools/modules/routing/router.py), the tables app/<app>_tt.h
(rttools.ucxgen.tt), the check of a run (rttools.paper.ttcheck through
exp23, rtlapp and rtlmr) on logs with synthetic FLIT, END and TIMER lines,
the kernel build options and the terms of the network interface in the
static analysis (experiments/wcet, config_tt.json)."""
import json
import os
import re
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT
from rttools.modules.routing import router
from rttools.paper import exp23, ttcheck
from rttools.ucxgen import tt

EXP = os.path.join(REPO_ROOT, "experiments")
UCX = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os")
APP_DIR = os.path.join(UCX, "app")
APPS = os.path.join(REPO_ROOT, "apps")
ARCH = os.path.join(REPO_ROOT, "arch")
E_CSV = os.path.join(APPS, "synthetic-app-e", "synthetic-app-e.csv")
E_MAP = os.path.join(APPS, "synthetic-app-e", "synthetic-app-e-ONTO-hermes2x2.map")


# ------------------------------------------------------------ model

def test_ni_model_default_is_tt_and_off_removes_the_bound(monkeypatch):
    assert router.ni_model() == (True, router.NI_WAIT_CYCLES)
    assert router.ni_resources()
    assert router.NI_WAIT_CYCLES == router.NI_INJECT_CYCLES + router.NI_RX_SIZE_CYCLES + router.NI_RX_END_CYCLES
    l0 = router.occupancy(1, 1200, wait=0, ni="off")
    assert router.occupancy(1, 1200, wait=0) == l0 + router.NI_WAIT_CYCLES
    assert router.occupancy(1, 1200, wait=0, ni="tt") == l0 + router.NI_WAIT_CYCLES
    assert router.occupancy(1, 1200, wait=0, ni=100) == l0 + 100
    for value in ("", "tt", "TT"):
        monkeypatch.setenv(router.NI_ENV, value)
        assert router.ni_model() == (True, router.NI_WAIT_CYCLES)
    monkeypatch.setenv(router.NI_ENV, "off")
    assert router.ni_model() == (False, 0) and not router.ni_resources()
    assert router.occupancy(1, 1200, wait=0) == l0
    prev = router.set_ni("tt")
    assert router.ni_model() == (True, router.NI_WAIT_CYCLES)
    router.set_ni(prev)
    assert router.ni_model() == (False, 0)
    for bad in ("x", "-1", True):
        with pytest.raises(ValueError):
            router.parse_ni(bad)


def test_ni_resource_in_the_link_schedule():
    """With the model tt each packet between PEs holds the network
    interfaces of its two PEs (labels NI-<node>) besides its links."""
    from rttools.modules.instances import instantiator
    from rttools.modules.io import appparser, mapparser, nocparser
    from rttools.modules.unwrapper import flowUnwrapper
    from rttools.tui.model import network as tnet
    with tnet.quiet():
        g, _ = appparser.loadFromFile(E_CSV)
        noc = nocparser.loadFromFile(os.path.join(ARCH, "hermes-2x2.gml"))
        entries = mapparser.loadFromFile(E_MAP)
        inst = instantiator.createInstance(g, noc, 434912000)
        router.set_ni("off")
        _, _, links_off = flowUnwrapper.unwrap(inst, noc, entries)
        router.set_ni("tt")
        packets, _, links = flowUnwrapper.unwrap(inst, noc, entries)
    remote = [p for p in packets if p.get("resources")]
    assert len(remote) == 5 and all(len(p["resources"]) == 2 and all(r.startswith("NI-") for r in p["resources"])
                                    for p in remote)
    ni = {d["label"] for _, _, d in links if str(d["label"]).startswith("NI-")}
    assert ni == {"NI-0", "NI-1", "NI-2", "NI-3"} and len(links) == len(links_off) + 4


def test_rows_round_up_to_the_timer_step():
    """s16 = s rounded up to 16 cycles; s16 = ticks P + 16 count; s + o_i
    inside the window of the packet (application E at 434.912 MHz)."""
    rows = ttcheck.schedule_rows(E_CSV, E_MAP, os.path.join(ARCH, "hermes-2x2.gml"), 434912000)
    assert rows["model"] == "phase" and len(rows["rows"]) == 5
    for r in rows["rows"]:
        assert r["offset"] <= r["s16"] < r["offset"] + tt.TIMER_STEP and r["s16"] % tt.TIMER_STEP == 0
        assert r["s16"] == r["ticks"] * r["period"] + tt.TIMER_STEP * r["count"]
        assert r["release"] <= r["s"] and r["s"] + r["occupancy"] <= r["deadline"]
    # o_i of the table holds w_NI
    m = {r["flow"]: r for r in rows["rows"]}
    a_c = m["f1"]
    assert a_c["occupancy"] - router.NI_WAIT_CYCLES == router.occupancy(1, 1230, ni="off")


def test_buffers_cover_the_occupancy():
    rows = [{"flow": "f1", "job_start": 0, "phase_start": 0, "offset": 100, "occupancy": 50},
            {"flow": "f1", "job_start": 120, "phase_start": 100, "offset": 0, "occupancy": 10}]
    # the second job starts at 120, before the end 150 of the first packet
    assert tt.buffers(rows, 1000) == {"f1": 2}
    rows[1]["job_start"] = 150
    assert tt.buffers(rows, 1000) == {"f1": 1}


@pytest.mark.parametrize("args", [
    ["tt-check", E_CSV, E_MAP, "--arch", os.path.join(ARCH, "hermes-2x2.gml"), "--name", "weird_a",
     "--clock", "449152000", "--clock", "500000000", "--style", "named", "--out", APP_DIR,
     "--costs", os.path.join(EXP, "wcet", "costs", "tt", "weird_a.json")],
    ["tt-check", os.path.join(APPS, "car-v", "car-v.csv"), os.path.join(APPS, "car-v", "car-v-ONTO-hermes4x4.map"),
     "--arch", os.path.join(ARCH, "hermes-4x4.gml"), "--name", "car_v", "--clock", "441088000",
     "--clock", "500000000", "--out", APP_DIR, "--costs", os.path.join(EXP, "wcet", "costs", "tt", "car_v.json")],
    ["tt-check", os.path.join(APPS, "wcet-e", "wcet-e.csv"), os.path.join(APPS, "wcet-e", "wcet-e-ONTO-hermes2x2.map"),
     "--arch", os.path.join(ARCH, "hermes-2x2.gml"), "--name", "wcet_e", "--clock", "234656000",
     "--clock", "500000000", "--out", APP_DIR, "--costs", os.path.join(EXP, "wcet", "costs", "tt", "wcet_e.json")],
    ["tt-check", os.path.join(APPS, "car-full", "car-full.csv"),
     os.path.join(APPS, "car-full", "car-full-ONTO-hermes4x4.map"), "--arch", os.path.join(ARCH, "hermes-4x4.gml"),
     "--name", "car_full", "--clock", "526080000", "--out", APP_DIR,
     "--costs", os.path.join(EXP, "wcet", "costs", "tt", "car_full.json")],
    ["tt-check", E_CSV, E_MAP, "--arch", os.path.join(ARCH, "hermes-2x2.gml"), "--name", "e_ucx",
     "--clock", "457600000", "--clock", "500000000", "--out", APP_DIR],
])
def test_stored_tables_match_the_generator(args):
    from rttools.ucxgen.__main__ import main
    assert main(args) == 0


def test_composition_table_matches_the_generator(monkeypatch):
    from rttools.ucxgen.__main__ import main
    monkeypatch.chdir(os.path.join(EXP, "multiapp"))
    assert main(["tt-compose-check", "--composition", "composition.json", "--name", "carv_e",
                 "--clock", "457600000", "--clock", "500000000", "--out", APP_DIR,
                 "--costs", os.path.join(EXP, "wcet", "costs", "tt", "carv_e.json")]) == 0


def test_table_without_a_schedule_stops(tmp_path):
    """CAR-V at 380 MHz, the clock of the runs up to tag r11-rc5, has no
    link schedule with w_NI: the generator stops."""
    from rttools.ucxgen.__main__ import main
    shutil.copy(os.path.join(APP_DIR, "car_v.json"), tmp_path / "car_v.json")
    assert main(["tt", os.path.join(APPS, "car-v", "car-v.csv"), os.path.join(APPS, "car-v", "car-v-ONTO-hermes4x4.map"),
              "--arch", os.path.join(ARCH, "hermes-4x4.gml"), "--name", "car_v", "--clock", "380000000",
              "--out", str(tmp_path)]) == 2
    assert not (tmp_path / "car_v_tt.h").exists()


# ------------------------------------------------------------ ttcheck

def test_parse_lines_and_tick_grid():
    lines = ["# FLIT END t=10 src=0-0 dst=1-0 tag=5 cyc=21", "# TIMER t=3 pe=0-0 cyc=7",
             "# TIMER t=9 pe=0-0 cyc=107", "# TIMER t=5 pe=0-0 cyc=51", "# TIMER t=9 pe=0-0 cyc=207",
             "# FLIT TX t=1 src=0-0 dst=1-0 tag=5 size=5 head=1 last=7 block=0 gap=0"]
    ends, timers = ttcheck.parse_lines(lines)
    assert ends == [{"t": 10, "src": "0-0", "dst": "1-0", "tag": 5, "cyc": 21}]
    assert len(timers) == 4
    g = ttcheck.tick_grid(timers, 100)["0-0"]
    assert (g["residue"], g["ticks"], g["lines_on_grid"]) == (7, 3, 3)
    assert ttcheck.nearest_tick(g, 160, 100) == 207 and ttcheck.nearest_tick(g, 140, 100) == 107


def packet_row(**kw):
    p = {"flow": "F1", "src": "0-0", "dst": "1-0", "tag": 5, "size": 10, "hops": 1, "tau": 1000, "s": 100,
         "s16": 112, "occupancy": 12 + 11 + 40 + 300, "deadline": 1000}
    p.update(tx_head=1000 + 112 + 30, tx_last=1000 + 112 + 30 + 11)
    p.update(rx_head=p["tx_head"] + 12, rx_last=p["tx_head"] + 12 + 11 + 5, end=p["tx_head"] + 12 + 11 + 5 + 20)
    p.update(kw)
    return p


def test_evaluate_counts_each_bound():
    ok = ttcheck.evaluate([packet_row()], w_h=20)
    assert ok["packets"] == 1 and ok["violations"] == 0
    r = ok["per_packet"][0]
    assert (r["inject_delay"], r["header_wait"], r["rx_wait"], r["end_wait"]) == (42, 0, 5, 20)
    assert r["occupancy_used"] == r["inject_delay"] + 12 + 11 + 5 + 20
    early = ttcheck.evaluate([packet_row(tx_head=1099)], w_h=20)
    assert early["early"] == 1 and early["violations"] >= 1
    p = packet_row()
    late = ttcheck.evaluate([packet_row(rx_head=p["rx_head"] + 41, rx_last=p["rx_last"] + 41, end=p["end"] + 41)],
                            w_h=20)
    assert late["header_above_bound"] == 1
    end = ttcheck.evaluate([packet_row(end=p["rx_last"] + router.NI_RX_END_CYCLES + 1)], w_h=20)
    assert end["end_wait_above_bound"] == 1 and end["occupancy_above"] == 1
    assert ttcheck.evaluate([packet_row(tau=None)])["unchecked"] == 1


def test_overlap_at_a_network_interface():
    a = packet_row()
    b = packet_row(tag=6, tx_head=a["tx_head"] + 5, tx_last=a["tx_last"] + 5, rx_head=a["rx_head"] + 5,
                   rx_last=a["rx_last"] + 5, end=a["end"] + 5, s=105)
    assert ttcheck.evaluate([a, b], w_h=20)["ni_overlaps"] == 2       # at 0-0 and at 1-0


def test_injection_rule():
    assert ttcheck.injection_rule(None) == "finish"
    assert ttcheck.injection_rule({"injection": "tt"}) == "tt"
    with pytest.raises(ValueError):
        ttcheck.injection_rule({"injection": "x"})


# ------------------------------------------------------------ synthetic runs

DELTA = 1900          # release request before the tick of its phase (cycles)
LAT = 30              # compare interrupt to the header at the router
STALL = 40            # credit withheld until irq2_handler gives the buffer
END = 70              # last flit to the handshake of irq3_handler


def _swap(label):
    x, y = label.split("-")
    return f"{y}-{x}"


def synth_log(base_log, base_info, out_dir, packets, pes, period, f_hz, perturb=None, costs=None, deadline=None):
    """Copy of a stored log without its FLIT lines, plus TIMER lines (ticks
    of every PE in `pes` and a compare interrupt per packet) and FLIT TX, RX
    and END lines of `packets` ({src, dst (monitor labels), tag, size, hops,
    tau, s16}); RUN_INFO with injection=tt (and deadline=<deadline> when
    given: the deadline model of the link schedule of `packets`). The line of cycle c has the
    $time (whole ns) of the rising edge (2 c + 1) half fs of the clock of
    f_hz, as the monitor prints it."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(base_log) as f:
        base = [ln for ln in f if "FLIT " not in ln and "TIMER " not in ln]
    rel = [int(m.group(1)) for m in (re.search(r"workflow iteration at (\d+) ns", ln) for ln in base) if m]
    half = round(5e14 / f_hz)
    ns = (lambda c: int(round((2 * c + 1) * half / 1e6)))
    first = int(round(rel[0] * f_hz / 1e9)) + DELTA
    last = int(round(rel[-1] * f_hz / 1e9)) + 3 * period
    extra = []
    for pe in pes:
        c = first - 2 * period
        while c <= last:
            extra.append(f"# TIMER t={ns(c)} pe={pe} cyc={c}")
            c += period
    for i, p in enumerate(packets):
        d = dict(tx=p["tau"] + p["s16"] + LAT)
        if perturb:
            perturb(i, p, d)
        tx = d["tx"]
        n = p["size"]
        rxh = tx + 6 * (p["hops"] + 1) + d.get("header", 0)
        rxl = rxh + n + 1 + STALL
        end = rxl + END + d.get("end", 0)
        if p["s16"] % period:
            extra.append(f"# TIMER t={ns(p['tau'] + p['s16'])} pe={p['src']} cyc={p['tau'] + p['s16']}")
        extra += [f"# FLIT TX t={ns(tx)} src={p['src']} dst={p['dst']} tag={p['tag']} size={n} head={tx} "
                  f"last={tx + n + 1} block=0 gap=0",
                  f"# FLIT RX t={ns(rxl)} src={p['src']} dst={p['dst']} tag={p['tag']} size={n} head={rxh} "
                  f"last={rxl} stall={STALL} gap=0",
                  f"# FLIT END t={ns(end)} src={p['src']} dst={p['dst']} tag={p['tag']} cyc={end}"]
    log = out_dir / "events.txt"
    log.write_text("".join(base) + "\n".join(extra) + "\n")
    info = open(base_info).read()
    extra_info = "injection=tt\n" + (f"deadline={deadline}\n" if deadline else "")
    if costs:
        from rttools.ucxgen.model import sha256
        extra_info += f"costs=max_csv_static costs_file={os.path.basename(costs)} costs_sha256={sha256(costs)}\n"
    (out_dir / "RUN_INFO").write_text(info + ("" if info.endswith("\n") else "\n") + extra_info)
    return str(log), rel


def tick_of(rel_ns, q, f_hz, period):
    return int(round(rel_ns[0] * f_hz / 1e9)) + DELTA + q * period


COSTS = os.path.join(EXP, "wcet", "costs", "tt")


def e_packets(f_hz, rel, costs=None):
    """Packets of application E for run UH: the n-th packet of each flow
    between PEs from the job of phase n + n(source); monitor labels (the
    swap of the config labels, run UH)."""
    cfg = exp23.load_config(os.path.join(EXP, "exp23", "config.json"))
    phi = exp23.response_bound(cfg)["phases"]
    router.set_ni("tt")
    rows = {r["flow"]: r for r in ttcheck.schedule_rows(E_CSV, E_MAP, os.path.join(ARCH, "hermes-2x2.gml"),
                                                         cfg["clock_hz"], costs=costs)["rows"]}
    from rttools.ucxgen.model import read_csv
    _, csv_flows, _ = read_csv(E_CSV)
    fid = {(f["source"], f["target"]): f["id"] for f in csv_flows}
    P = 217456
    out = []
    for f in cfg["flows"]:
        if f["src_pe"] == f["dst_pe"]:
            continue
        r = rows["f" + str(fid[(f["source"], f["target"])])]
        for n in range(len(rel)):
            q = n + phi[f["source"]]
            if q >= len(rel) - 1:
                break
            out.append({"src": _swap(f["src_pe"]), "dst": _swap(f["dst_pe"]), "tag": int(f["tag"]),
                        "size": router.getPacketFlits(int(f["tag"])), "hops": exp23._hops(f["src_pe"], f["dst_pe"]),
                        "tau": tick_of(rel, q, f_hz, P), "s16": r["s16"], "s": r["offset"], "o": r["occupancy"]})
    return out


def run_e(tmp_path, perturb=None, costs=None):
    E = os.path.join(EXP, "exp23")
    info = exp23.read_run_info(os.path.join(E, "logs", "UH.RUN_INFO"))
    f_hz = float(info["clock_hz_exact"])
    with open(os.path.join(E, "logs", "UH.events.txt")) as f:
        rel = [int(m.group(1)) for m in (re.search(r"workflow iteration at (\d+) ns", ln) for ln in f) if m]
    pk = e_packets(f_hz, rel, costs)
    log, _ = synth_log(os.path.join(E, "logs", "UH.events.txt"), os.path.join(E, "logs", "UH.RUN_INFO"),
                       tmp_path / "run", pk, ["0-0", "1-0", "0-1", "1-1"], 217456, f_hz, perturb, costs)
    m = exp23.analyze(log, exp23.load_config(os.path.join(E, "config.json")), str(tmp_path / "out"),
                      arch=os.path.join(ARCH, "hermes-2x2.gml"), mapping=E_MAP)
    return m, pk


def test_exp23_run_with_the_injection_at_the_schedule(tmp_path):
    m, pk = run_e(tmp_path)
    t = m["tt"]
    assert m["injection"] == "tt"
    assert t["packets"] == len(pk) > 100 and t["unchecked"] == 0 and t["violations"] == 0
    assert t["inject_delay_min"] >= LAT and t["inject_delay_max"] <= LAT + 15
    assert (t["rx_wait_max"], t["end_wait_max"], t["header_wait_max"]) == (STALL, END, 0)
    assert t["tick_grid_coverage_min"] == 1 and t["phase_ticks_irregular_pes"] == 0
    assert (tmp_path / "out" / "tt_packets.csv").exists()
    from rttools.paper import phasecheck
    assert phasecheck.main([str(tmp_path / "out" / "metrics.json")]) in (0, 1)


def test_exp23_run_with_the_costs_of_the_image(tmp_path, monkeypatch):
    """RUN_INFO costs=max(CSV, static) weird_a.json: the link schedule takes
    t(v) = max(CSV, static t(v) of the image); every iteration of run UH
    ends at or before F(v) of that model after the tick of its phase and
    every packet between PEs is enqueued (send TAG line) at or before its
    instant s (the finish injection of UH sends a packet at the end of its
    job, before s)."""
    # UH ran with a table built before the release guard of the link schedule (router.release_guard)
    monkeypatch.setenv("RTTOOLS_RELEASE_GUARD", "off")
    m, pk = run_e(tmp_path, costs=os.path.join(COSTS, "weird_a.json"))
    t = m["tt"]
    assert m["costs"] == {"file": "weird_a.json", "rule": "max"}
    assert t["violations"] == 0 and t["packets"] == len(pk)
    assert t["jobs"]["events"] > 300 and t["jobs"]["late"] == 0 and t["jobs"]["unchecked"] == 0
    assert t["ready"]["events"] > 100 and t["ready"]["late"] == 0
    assert (tmp_path / "out" / "tt_jobs.csv").exists() and (tmp_path / "out" / "tt_ready.csv").exists()


def test_costs_of_run_checks_the_hash(tmp_path):
    assert ttcheck.costs_of_run({"costs": "csv"}) is None and ttcheck.costs_of_run(None) is None
    path = os.path.join(COSTS, "car_v.json")
    from rttools.ucxgen.model import sha256
    info = {"costs": "max_csv_static", "costs_file": "car_v.json", "costs_sha256": sha256(path)}
    assert ttcheck.costs_of_run(info) == path
    with pytest.raises(ValueError):
        ttcheck.costs_of_run(dict(info, costs_sha256="00"))


def test_exp23_run_finds_an_early_and_a_late_packet(tmp_path):
    def perturb(i, p, d):
        if i == 3:
            d["tx"] = p["tau"] + p["s"] - 1                    # before the instant
        if i == 7:
            d["end"] = router.NI_RX_END_CYCLES                 # handshake past its bound, inside o_i
        if i == 9:
            d["end"] = p["o"]                                  # handshake past the end of o_i
    m, _ = run_e(tmp_path, perturb)
    t = m["tt"]
    assert (t["early"], t["end_wait_above_bound"], t["occupancy_above"]) == (1, 2, 1)
    assert t["violations"] == 4


def test_runs_without_the_line_are_finish():
    """The stored runs (no injection line in RUN_INFO) keep the model of
    their references: no tt check, link schedule without the network
    interface."""
    m_info = exp23.read_run_info(os.path.join(EXP, "exp23", "logs", "UH.RUN_INFO"))
    assert "injection" not in m_info and ttcheck.injection_rule(m_info) == "finish"


@pytest.mark.parametrize("costs", [None, os.path.join(COSTS, "wcet_e.json")])
def test_rtlapp_run_wcet_e(tmp_path, costs):
    """WCET-E (rtlapp): the packets of a synthetic run at 500 MHz with the
    instants of wcet_e_tt.h conform; tags carry flow and iteration. With
    the costs of the image in RUN_INFO: every iteration of run W3 ends at
    or before F(v) of the model with t(v) = max(CSV, static) and every
    packet is enqueued at or before its instant s."""
    from rttools.paper import rtlapp
    W = os.path.join(EXP, "wcet")
    man = os.path.join(APP_DIR, "wcet_e.json")
    csv_p = os.path.join(APPS, "wcet-e", "wcet-e.csv")
    map_p = os.path.join(APPS, "wcet-e", "wcet-e-ONTO-hermes2x2.map")
    app = rtlapp.load_app(man, csv_p, map_p)
    mdl = rtlapp.model(app, 500000000)
    rows = {r["flow"]: r for r in ttcheck.schedule_rows(csv_p, map_p, os.path.join(ARCH, "hermes-2x2.gml"),
                                                         500000000, costs=costs)["rows"]}
    with open(os.path.join(W, "logs", "W3.events.txt")) as f:
        rel = [int(m.group(1)) for m in (re.search(r"workflow iteration at (\d+) ns", ln) for ln in f) if m]
    f_hz = 500000000.0
    P = 250000
    pk = []
    for fid, fl in app["flows"].items():
        if fl["local"]:
            continue
        r = rows["f" + str(fl["csv_id"])]
        for n in range(len(rel)):
            q = n + mdl["tasks"][fl["source"]]["phase"]
            if q >= len(rel) - 1:
                break
            pk.append({"src": fl["src_label"], "dst": fl["dst_label"], "tag": fid * 1024 + n + 1,
                       "size": router.getPacketFlits(fl["bytes"]), "hops": exp23._hops(fl["src_label"], fl["dst_label"]),
                       "tau": tick_of(rel, q, f_hz, P), "s16": r["s16"], "s": r["offset"]})
    log, _ = synth_log(os.path.join(W, "logs", "W3.events.txt"), os.path.join(W, "logs", "W3.RUN_INFO"),
                       tmp_path / "run", pk, ["0-0", "1-0", "0-1", "1-1"], P, f_hz, costs=costs,
                       deadline=router.deadline_model())
    m = rtlapp.analyze(log, man, csv_p, map_p, str(tmp_path / "out"), arch=os.path.join(ARCH, "hermes-2x2.gml"))
    t = m["tt"]
    assert t["packets"] == len(pk) and t["violations"] == 0 and t["unchecked"] == 0
    assert m["link_schedule"]["feasible"]
    if costs:
        assert m["costs"]["file"] == "wcet_e.json"
        assert t["jobs"]["events"] > 50 and t["jobs"]["late"] == 0 and t["jobs"]["unchecked"] == 0
        assert t["ready"]["events"] > 20 and t["ready"]["late"] == 0
    assert any("time-triggered injection" in x for x in rtlapp.summary_lines(m))


def test_rtlmr_run_car_full(tmp_path):
    """CAR-full (rtlmr): packet n of a flow is packet n mod N_e of
    hyperperiod n div N_e, from the job of phase H_t h + phase_start / P."""
    from rttools.paper import rtlmr
    F = os.path.join(EXP, "car-full")
    man_p = os.path.join(APP_DIR, "car_full.json")
    man = json.load(open(man_p))
    csv_p = os.path.join(APPS, "car-full", "car-full.csv")
    map_p = os.path.join(APPS, "car-full", "car-full-ONTO-hermes4x4.map")
    # the clock of run CF4 (432 MHz) is below the minimum of the deadline model tick: the packets of the
    # synthetic run follow the deadline model start (the modeled start of the reader, tables up to r11-rc8)
    prev = router.set_deadline("start")
    try:
        table = ttcheck.schedule_rows(csv_p, map_p, os.path.join(ARCH, "hermes-4x4.gml"), 432000000)
    finally:
        router.set_deadline(prev)
    by = ttcheck.rows_by_flow(table)
    with open(os.path.join(F, "logs", "CF4.events.txt")) as f:
        rel = [int(m.group(1)) for m in (re.search(r"workflow iteration at (\d+) ns", ln) for ln in f) if m]
    f_hz = 432000000.0
    P = 108000
    Ht = man["hyper_ticks"]
    pk = []
    for fl in man["flows"]:
        if fl["local"]:
            continue
        rs = by["f" + str(fl["csv_id"])]
        n = 0
        while True:
            h, k = divmod(n, len(rs))
            q = h * Ht + rs[k]["phase_start"] // P
            if q >= len(rel) - 1:
                break
            pk.append({"src": fl["src_label"], "dst": fl["dst_label"], "tag": fl["id"] * 1024 + (n + 1) % 1024,
                       "size": router.getPacketFlits(fl["bytes"]),
                       "hops": exp23._hops(fl["src_label"], fl["dst_label"]),
                       "tau": tick_of(rel, q, f_hz, P), "s16": rs[k]["s16"], "s": rs[k]["offset"]})
            n += 1
    pes = [f"{x}-{y}" for x in range(4) for y in range(4)]
    log, _ = synth_log(os.path.join(F, "logs", "CF4.events.txt"), os.path.join(F, "logs", "CF4.RUN_INFO"),
                       tmp_path / "run", pk, pes, P, f_hz, deadline="start")
    m = rtlmr.analyze(log, man_p, csv_p, map_p, str(tmp_path / "out"), arch=os.path.join(ARCH, "hermes-4x4.gml"))
    t = m["tt"]
    assert t["packets"] == len(pk) > 1000 and t["violations"] == 0 and t["unchecked"] == 0


# ------------------------------------------------------------ build and scripts

def test_kernel_sources_and_build_options():
    mk = open(os.path.join(UCX, "Makefile")).read()
    assert "INJECTION ?= tt" in mk and "INJ_DEFS = -DUCX_NOC_TT" in mk and "noc_tt.o" in mk
    assert "TR_DEFS = -DUCX_APP_IRQ4 -DUCX_APP_TICK -DUCX_TICK_RELEASE $(INJ_DEFS)" in mk
    sched = open(os.path.join(UCX, "kernel", "sched.c")).read()
    assert "#ifdef UCX_NOC_TT\n\t\t/* time-triggered injection" in sched and "ucx_noc_tt_tick();" in sched
    for app in ("weird_a", "car_v", "carv_e", "e_ucx", "wcet_e", "car_full"):
        src = open(os.path.join(APP_DIR, app + ".c")).read()
        assert f'#include "{app}_tt.h"' in src and "ucx_noc_send_at(" in src
    for f in ("build_sw.sh", "simulate.sh"):
        s = open(os.path.join(EXP, "exp23", f)).read()
        assert "INJECTION=${INJECTION:-tt}" in s
    sim = open(os.path.join(EXP, "exp23", "simulate.sh")).read()
    assert "FLIT (TX|RX|END) |TIMER t=" in sim and 'echo "injection=tt"' in sim


def test_simulate_injection_line(tmp_path):
    """simulate.sh passes INJECTION to make and writes injection=tt when the
    listing of the image has timer1ocr_handler, else injection=finish; an
    unknown value stops with status 2. The line costs copies the costs file
    of the line Costs of app/<app>_tt.h (costs=csv without it)."""
    from tests.test_simulate_options import stub_repo
    repo, env, log = stub_repo(tmp_path)
    sh = str(repo / "experiments" / "exp23" / "simulate.sh")
    r = subprocess.run(["bash", sh, str(tmp_path / "o"), "1000"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert "-s weird_a F_CLK=500000000 F_TICK=2000 INJECTION=tt" in log.read_text()
    assert "\ninjection=finish\n" in (tmp_path / "o" / "RUN_INFO").read_text()
    assert "\ncosts=csv\n" in (tmp_path / "o" / "RUN_INFO").read_text()
    shutil.copy(os.path.join(APP_DIR, "weird_a_tt.h"), repo / "pkt-sim" / "software" / "ucx-os" / "app")
    # a make that leaves a listing with the compare handler
    b = tmp_path / "bin2"
    b.mkdir()
    lst = tmp_path / "o2" / "pkt-sim" / "software" / "ucx-os" / "build" / "target"
    (b / "make").write_text(f'#!/bin/sh\nmkdir -p {lst}\necho "00001234 <timer1ocr_handler>:" > {lst}/image.lst\n'
                            f'echo "$@" >> {log}\n')
    (b / "make").chmod(0o755)
    env2 = {**env, "PATH": f"{b}:{env['PATH']}", "INJECTION": "finish"}
    r = subprocess.run(["bash", sh, str(tmp_path / "o2"), "1000"], capture_output=True, text=True, env=env2)
    assert r.returncode == 0, r.stderr
    assert "-s weird_a F_CLK=500000000 F_TICK=2000 INJECTION=finish" in log.read_text()
    info = exp23.read_run_info(str(tmp_path / "o2" / "RUN_INFO"))
    assert info["injection"] == "tt" and info["costs"] == "max_csv_static"
    assert ttcheck.costs_of_run(info) == os.path.join(COSTS, "weird_a.json")
    r = subprocess.run(["bash", sh, str(tmp_path / "o3"), "1000"], capture_output=True, text=True,
                       env={**env, "INJECTION": "x"})
    assert r.returncode == 2 and "INJECTION must be" in r.stderr


def test_ni_terms_of_the_images_within_the_model(tmp_path):
    """experiments/wcet config_tt.json: every term of the network interface
    of every image with the time-triggered injection (gcc 12.2 and 13.2)
    at or below its constant of the model, and the metrics equal
    reference_tt.json."""
    pytest.importorskip("elftools")
    pytest.importorskip("scipy")
    from rttools.paper import wcet
    m = wcet.analyze(os.path.join(EXP, "wcet", "config_tt.json"), str(tmp_path))
    assert m["ni_within_bound"] and m["ni_bound"] == router.NI_WAIT_CYCLES
    # the constants are the largest terms of the images of tag r11-rc7 (car_full, gcc 13.2); the
    # tick hook of car_full with TT_TICK shortens its terms, so the largest w_NI is now below it
    assert m["ni_max"] == 14998 < router.NI_WAIT_CYCLES
    for name in ("inject", "rx_size", "rx_end"):
        assert max(r["ni"][name] for r in m["ni_images"].values()) <= m["ni_term_bounds"][name]
    assert m["apps"]["E"]["pe_bound_sound"]
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(EXP, "wcet", "reference_tt.json")) == []
