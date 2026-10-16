"""Flit times of the packet monitor (experiments/exp23/rtl/pe_checker.sv):
FLIT TX/RX lines, network latency per packet and per flow
(rttools.paper.exp23.network_latency) and the Verilator testbench of the
monitor (experiments/exp23/rtl/test)."""
import json
import os
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT
from rttools.paper import exp23
from rttools.tui.model import parsers

EXP = os.path.join(REPO_ROOT, "experiments", "exp23")
LOG_F = os.path.join(EXP, "logs", "F.events.txt")


def cfg():
    # load_config: the application CSV of the config as an absolute path
    # (creation rows of the dispatch order)
    return exp23.load_config(os.path.join(EXP, "config.json"))


def tx_line(t, src, dst, tag, size, head, last, block=0, gap=0):
    return (f"# FLIT TX t={t} src={src} dst={dst} tag={tag} size={size} head={head} last={last} "
            f"block={block} gap={gap}")


def rx_line(t, src, dst, tag, size, head, last, stall=0, gap=0):
    return (f"# FLIT RX t={t} src={src} dst={dst} tag={tag} size={size} head={head} last={last} "
            f"stall={stall} gap={gap}")


def packet(src, dst, tag, size, m, t0, stall=0, gap=0, header_extra=0):
    """TX and RX lines of one packet whose header leaves at cycle t0:
    header after 6 (m + 1) + header_extra cycles, last flit after
    p + 1 + stall + gap more cycles (the identity of the RX window)."""
    h = t0 + 6 * (m + 1) + header_extra
    last = h + size + 1 + stall + gap
    return [tx_line(2 * t0, src, dst, tag, size, t0, t0 + size + 1),
            rx_line(2 * last, src, dst, tag, size, h, last, stall, gap)]


FLOWS_2 = {"flows": [
    {"name": "F4", "source": "I", "target": "J", "tag": "5670", "src_pe": "1-0", "dst_pe": "1-1"},
    {"name": "F5", "source": "H", "target": "J", "tag": "8900", "src_pe": "1-0", "dst_pe": "1-1"},
]}


def test_parse_flit_lines_reads_both_sides_with_and_without_prefix():
    lines = ["# 3028513 0-0 -> TAG 4560", tx_line(10, "0-0", "1-0", 1230, 311, 5, 317),
             rx_line(20, "0-0", "1-0", 1230, 311, 17, 400, 70, 0)[2:], "# CHKSUM node 0-0 send_pkts=1",
             "# FLIT XX t=1"]
    tx, rx = exp23.parse_flit_lines(lines)
    assert tx == [{"side": "TX", "t": 10, "src": "0-0", "dst": "1-0", "tag": 1230, "size": 311, "head": 5,
                   "last": 317, "block": 0, "gap": 0}]
    assert rx[0]["stall"] == 70 and rx[0]["head"] == 17 and rx[0]["src"] == "0-0"


def test_no_flit_lines_gives_none():
    assert exp23.network_latency([], [], cfg()) is None


def test_zero_load_packets_equal_l0():
    # F4 and F5: 1-0 -> 1-1, m = 1, p = 1421 and 2228
    lines = packet("1-0", "1-1", 5670, 1421, 1, 1000) + packet("1-0", "1-1", 8900, 2228, 1, 5000)
    net = exp23.network_latency(*exp23.parse_flit_lines(lines), FLOWS_2)
    f4, f5 = net["flows"]
    assert (f4["hops"], f4["flits"], f4["L0"], f4["header_model"]) == (1, 1421, 1434, 12)
    assert (f5["flits"], f5["L0"]) == (2228, 2241)
    for f in (f4, f5):
        assert f["packets"] == 1 and f["at_L0"] == 1 and f["header_at_model"] == 1
        assert f["latency_min"] == f["L0"] and f["latency_minus_L0_max"] == 0
        assert f["tag_mismatch"] == 0
    assert net["identity_errors"] == 0 and net["unpaired_tx"] == 0 and net["unpaired_rx"] == 0


def test_latency_minus_l0_is_header_excess_plus_stall_plus_gap():
    lines = (packet("1-0", "1-1", 5670, 1421, 1, 1000, stall=1500, gap=3)
             + packet("1-0", "1-1", 5670, 1421, 1, 9000, stall=1490, header_extra=4))
    net = exp23.network_latency(*exp23.parse_flit_lines(lines), FLOWS_2)
    f4 = net["flows"][0]
    assert f4["packets"] == 2 and f4["at_L0"] == 0 and f4["header_at_model"] == 1
    assert (f4["latency_minus_L0_min"], f4["latency_minus_L0_max"]) == (1494, 1503)
    assert (f4["header_minus_model_min"], f4["header_minus_model_max"]) == (0, 4)
    assert (f4["stall_min"], f4["stall_max"], f4["gap_max"]) == (1490, 1500, 3)
    assert net["identity_errors"] == 0


def test_identity_error_is_counted():
    tx, rx = exp23.parse_flit_lines(packet("1-0", "1-1", 5670, 1421, 1, 1000, stall=10))
    rx[0]["stall"] = 9
    assert exp23.network_latency(tx, rx, FLOWS_2)["identity_errors"] == 1


def test_pairing_keeps_order_per_source_destination_and_size():
    # two F5 packets in flight, an F4 packet between them; RX of the second
    # F5 comes before the RX of F4
    a = packet("1-0", "1-1", 8900, 2228, 1, 1000, stall=100)
    b = packet("1-0", "1-1", 5670, 1421, 1, 2000, stall=5000)
    c = packet("1-0", "1-1", 8900, 2228, 1, 3000, stall=10)
    net = exp23.network_latency(*exp23.parse_flit_lines(a + b + c), FLOWS_2)
    f4, f5 = net["flows"]
    assert f4["packets"] == 1 and f4["stall_max"] == 5000
    assert f5["packets"] == 2 and (f5["stall_min"], f5["stall_max"]) == (10, 100)
    assert net["identity_errors"] == 0


def test_unpaired_lines_and_packets_outside_the_flows():
    lines = (packet("1-0", "1-1", 5670, 1421, 1, 1000)[:1]          # TX without RX
             + packet("0-0", "1-1", 77, 25, 2, 3000)                 # no flow 0-0 -> 1-1 of 25 flits
             + [rx_line(1, "1-0", "1-1", 8900, 2228, 1, 2240)])      # RX without TX
    net = exp23.network_latency(*exp23.parse_flit_lines(lines), FLOWS_2)
    assert (net["unpaired_tx"], net["unpaired_rx"], net["outside_flows"], net["packets"]) == (1, 1, 1, 1)


def test_tag_mismatch_is_counted():
    lines = packet("1-0", "1-1", 5670, 1421, 1, 1000)
    lines[1] = lines[1].replace("tag=5670", "tag=22038")
    net = exp23.network_latency(*exp23.parse_flit_lines(lines), FLOWS_2)
    assert net["flows"][0]["packets"] == 1 and net["flows"][0]["tag_mismatch"] == 1


def test_swap_xy_maps_monitor_labels_to_config_labels():
    # the monitor prints X-Y of ADDRESS; with swap_xy, 0-1 -> 1-1 is flow 1-0 -> 1-1
    lines = packet("0-1", "1-1", 5670, 1421, 1, 1000)
    assert exp23.network_latency(*exp23.parse_flit_lines(lines), FLOWS_2)["flows"][0]["packets"] == 0
    assert exp23.network_latency(*exp23.parse_flit_lines(lines), FLOWS_2, swap_xy=True)["flows"][0]["packets"] == 1


def test_driver_is_software_minus_network_latency():
    lines = packet("1-0", "1-1", 5670, 1421, 1, 1000, stall=50) + packet("1-0", "1-1", 5670, 1421, 1, 9000)
    net = exp23.network_latency(*exp23.parse_flit_lines(lines), FLOWS_2, software={"F4": [3000, 2900]})
    f4 = net["flows"][0]
    assert (f4["latency_min"], f4["latency_max"]) == (1434, 1484)
    assert (f4["driver_min"], f4["driver_max"]) == (1466, 1516)
    # counts differ: no driver
    net = exp23.network_latency(*exp23.parse_flit_lines(lines), FLOWS_2, software={"F4": [3000]})
    assert net["flows"][0]["driver_min"] is None


def synthetic_f_log(path):
    """Log F plus FLIT lines: for each software packet of each flow, TX
    header 700 cycles after the `->` mark, RX header 6 (m + 1) later, stall
    900 + k (k-th packet of the flow), no gap. Monitor labels are X-Y of
    ADDRESS (the swap of the config labels in log F)."""
    c = cfg()
    tr = exp23.load(LOG_F, c)
    clk = exp23.Clock(tr.unit, c["clock_hz"])
    assert tr.meta["swap_xy"]
    out = []
    expected = {}
    for f in c["flows"]:
        tag = "TAG " + f["tag"]
        sends = sorted(mk.time for mk in tr.lane_marks(f["src_pe"]) if mk.kind == "send" and mk.label == tag)
        p = 3 + -(-int(f["tag"]) // 4)
        src, dst = parsers.swap_node(f["src_pe"]), parsers.swap_node(f["dst_pe"])
        m = exp23._hops(src, dst)
        for k, s in enumerate(sends):
            t0 = int(clk.cycles(s)) + 700
            out += packet(src, dst, f["tag"], p, m, t0, stall=900 + k)
        expected[f["name"]] = (len(sends), 6 * (m + 1) + p + 1)
    with open(LOG_F) as fi, open(path, "w") as fo:
        fo.write(fi.read())
        fo.write("\n".join(out) + "\n")
    return expected


def test_analyze_log_f_with_flit_lines(tmp_path):
    log = tmp_path / "F_flit.events.txt"
    expected = synthetic_f_log(str(log))
    # listings of run F: reference_head.json holds the instrumentation bound
    m = exp23.analyze(str(log), cfg(), str(tmp_path / "out"), listing=os.path.join(EXP, "logs", "F.image.lst"),
                      listing_without=os.path.join(EXP, "logs", "F.noinstr.lst"))
    net = m["network"]
    assert net["packets"] == 166 and net["identity_errors"] == 0 and net["outside_flows"] == 0
    rows = {r["flow"]: r for r in net["flows"]}
    assert {k: (r["packets"], r["L0"]) for k, r in rows.items()} == expected
    assert {k: r["L0"] for k, r in rows.items()} == {"F1": 324, "F2": 1717, "F3": 322, "F4": 1434, "F5": 2241}
    sw = exp23.software_latencies(exp23.load(LOG_F, cfg()), cfg(), exp23.Clock(exp23.load(LOG_F, cfg()).unit,
                                                                                cfg()["clock_hz"]))
    for k, r in rows.items():
        n = expected[k][0]
        assert (r["latency_minus_L0_min"], r["latency_minus_L0_max"]) == (900, 900 + n - 1)
        assert r["header_at_model"] == n and r["tag_mismatch"] == 0
        # driver = software latency - (L0 + stall)
        drv = [s - (r["L0"] + 900 + i) for i, s in enumerate(sw[k])]
        assert (r["driver_min"], r["driver_max"]) == (exp23.exact(min(drv)), exp23.exact(max(drv)))
    # outputs, and the numbers of the paper do not change
    for f in ("network.tex", "network.csv", "network_packets.csv"):
        assert (tmp_path / "out" / f).exists()
    assert exp23.check(str(tmp_path / "out" / "metrics.json"), os.path.join(EXP, "reference_head.json")) == []


def test_log_f_has_no_flit_lines(tmp_path):
    m = exp23.analyze(LOG_F, cfg(), str(tmp_path))
    assert m["network"] is None
    assert not (tmp_path / "network.tex").exists()


def test_simulate_keeps_flit_lines_in_events():
    with open(os.path.join(EXP, "simulate.sh")) as f:
        s = f.read()
    assert "FLIT (TX|RX|END) |TIMER t=" in s


def test_monitor_testbench_verilator(tmp_path):
    if shutil.which("verilator") is None:
        pytest.skip("verilator ausente")
    r = subprocess.run(["sh", os.path.join(EXP, "rtl", "test", "run.sh"), str(tmp_path)],
                       capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-4000:]
    assert "lint bind: ok" in r.stdout
    assert "CHK " not in r.stdout, out
    tot = {}
    for line in r.stdout.splitlines():
        if line.startswith("CHKSUM"):
            for kv in line.split()[3:]:
                k, v = kv.split("=")
                tot[k] = tot.get(k, 0) + int(v)
    assert tot["send_ok"] == 2 and tot["recv_pkts"] == 2
    assert tot["send_err"] + tot["recv_err"] + tot["recv_spurious"] + tot["recv_missing"] == 0
    tx, rx = exp23.parse_flit_lines(r.stdout.splitlines())
    # schedule of tb_pe_checker.sv: tags and source decoded from the payload
    assert [(d["src"], d["dst"], d["tag"], d["size"], d["block"], d["gap"]) for d in tx] == \
        [("0-0", "1-0", 18, 8, 2, 1), ("0-0", "1-0", 5, 5, 0, 0)]
    assert [(d["src"], d["dst"], d["tag"], d["size"], d["stall"], d["gap"]) for d in rx] == \
        [("0-0", "1-0", 18, 8, 8, 2), ("0-0", "1-0", 5, 5, 1, 0)]
    c = {"flows": [{"name": "P1", "source": "a", "target": "b", "tag": "18", "src_pe": "0-0", "dst_pe": "1-0"},
                   {"name": "P2", "source": "a", "target": "b", "tag": "5", "src_pe": "0-0", "dst_pe": "1-0"}]}
    net = exp23.network_latency(tx, rx, c)
    p1, p2 = net["flows"]
    assert net["identity_errors"] == 0 and net["packets"] == 2
    # m = 1: L0 = 12 + p + 1; header after 12 edges
    assert (p1["L0"], p1["latency_min"], p1["header_minus_model_max"], p1["latency_minus_L0_min"]) == (21, 31, 0, 10)
    assert (p2["L0"], p2["latency_min"], p2["header_minus_model_max"], p2["latency_minus_L0_min"]) == (18, 19, 0, 1)
    assert p1["tag_mismatch"] == 0 and p2["tag_mismatch"] == 0
    # handshake of each received packet (5 and 4 edges after its last flit)
    # and the rises of the timer line of the source PE (edges 20 and 40
    # after the release of reset)
    from rttools.paper import ttcheck
    ends, timers = ttcheck.parse_lines(r.stdout.splitlines())
    assert [(e["src"], e["dst"], e["tag"], e["cyc"] - x["last"]) for e, x in zip(ends, rx)] == \
        [("0-0", "1-0", 18, 6), ("0-0", "1-0", 5, 5)]
    assert [(x["pe"], x["cyc"]) for x in timers] == [("0-0", 24), ("0-0", 44)]
