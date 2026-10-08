"""Characterized task costs of application E and their sequence per PE.

    python -m rttools.bench_t.main

The costs c^(v) are characterized per task (thesis scale: 10 times the
cycles of pkt-sim/software/ucx-os/app/weird_a.c) and include the
scheduler cost (SCHEDULER_CYCLES) of the dispatch of the task. Each list
gives the tasks of one cluster in dispatch order. The command prints the
sequence of each PE computed by ORT/BENCH (rttools/bench_t/estimate.py)
and the CPU demand of the PE per iteration.
"""
import sys

SCHEDULER_CYCLES = 110000

TASK_SETS = {
    "ABDF": [("A", 285300), ("B", 586000), ("D", 140000), ("F", 808000)],
    "C": [("C", 963300)],
    "EHI": [("E", 527000), ("I", 753700), ("H", 453000)],
    "GJ": [("G", 1098800), ("J", 1075700)],
}


def main():
    from rttools.bench_t import estimate
    for cluster, tasks in TASK_SETS.items():
        seq = estimate.sequence(tasks, SCHEDULER_CYCLES)
        for name, _ in tasks:
            print(f"{cluster} {name} start {seq[name]['start']} finish {seq[name]['finish']}")
        print(f"{cluster} demand {estimate.demand(tasks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
