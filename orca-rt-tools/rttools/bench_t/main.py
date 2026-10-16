"""Characterized task costs of application E and their sequence per PE.

    python -m rttools.bench_t.main [--costs costs.json]

The costs c^(v) are characterized per task (scale of the ORCA RT-Tools reference: 10 times the
cycles of pkt-sim/software/ucx-os/app/weird_a.c) and include the
scheduler cost (SCHEDULER_CYCLES) of the dispatch of the task. Each list
gives the tasks of one cluster in the dispatch order of the UCX/OS
kernel: estimate.dispatch_order on the creation order of app_main
(creation rows of apps/synthetic-app-e/synthetic-app-e.csv; tests/
test_bench_t_estimate.py checks the lists against them). The command
prints the sequence of each PE computed by ORT/BENCH (rttools/bench_t/
estimate.py) and the CPU demand of the PE per iteration. With --costs,
the costs are the static t(v) of rttools.wcet (python -m rttools.wcet
analyze ... --out costs.json; experiments/wcet) in cycles of the platform.
"""
import sys

SCHEDULER_CYCLES = 110000

TASK_SETS = {
    "ABDF": [("A", 285300), ("B", 586000), ("D", 140000), ("F", 808000)],
    "C": [("C", 963300)],
    "EHI": [("E", 527000), ("H", 453000), ("I", 753700)],
    "GJ": [("J", 1075700), ("G", 1098800)],
}


def task_sets(costs_file=None):
    """(task sets, scheduler cycles): the characterized costs above, or
    with --costs the static t(v) of a costs file of rttools.wcet (cycles of
    the platform, not the scale of the ORCA RT-Tools reference) and its dispatch term."""
    if costs_file is None:
        return TASK_SETS, SCHEDULER_CYCLES
    from rttools.wcet import costs
    c = costs.load(costs_file)
    sets = {k: [(n, c["tasks"][n]) for n, _ in v] for k, v in TASK_SETS.items()}
    return sets, c["scheduler_cycles"] or 0


def main(argv=None):
    """python -m rttools.bench_t.main [--costs costs.json]"""
    from rttools.bench_t import estimate
    from rttools.wcet import costs
    args, costs_file = costs.split_flag(list(argv or []))
    if args:
        print("usage: python -m rttools.bench_t.main [--costs costs.json]", file=sys.stderr)
        return 2
    sets, sched = task_sets(costs_file)
    for cluster, tasks in sets.items():
        seq = estimate.sequence(tasks, sched)
        for name, _ in tasks:
            print(f"{cluster} {name} start {seq[name]['start']} finish {seq[name]['finish']}")
        print(f"{cluster} demand {estimate.demand(tasks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
