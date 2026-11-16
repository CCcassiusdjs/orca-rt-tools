import sys
from sys import argv

from rttools.terminal.terminal import header, info, error

from rttools.gff.orca import import_graph as orca_import

from rttools.bench.scheduling import (
	RoundRobinSchedule,
	RateMonotonicScheduling,
	DeadlineMonotonicSchedule,
	EarliestDeadlineFirst,
)
from rttools.bench.engine import SingleCoreEngine

# policies available on the command line
ALGORITHMS = {
	"RR": RoundRobinSchedule,
	"RM": RateMonotonicScheduling,
	"DM": DeadlineMonotonicSchedule,
	"EDF": EarliestDeadlineFirst,
}

DEFAULT_HORIZON = 1000


def main_bench(argv):

	header("This is ORT/BENCH")

	if len(argv) not in (3, 4):
		info("Usage: bench <filename> <mode> <algorithm> [<horizon>]")
		info("algorithms: " + ", ".join(ALGORITHMS.keys()))
		return 1

	filename = argv[0]
	mode = argv[1]
	algo = argv[2]
	horizon = int(argv[3]) if len(argv) == 4 else DEFAULT_HORIZON

	# select algorithm
	algorithm = ALGORITHMS.get(algo.upper())
	if algorithm is None:
		error("Unable to find algorithm '" + algo + "'; options: " + ", ".join(ALGORITHMS.keys()))
		return 1

	# read file
	graph = orca_import(filename)

	engine: SingleCoreEngine = SingleCoreEngine(graph, algorithm)
	end = engine.simulate(horizon, False)

	for (b, e, n) in engine.merged_trace():
		print(f"{b} {e} {n}")
	info("simulation ended at", end, "deadline misses:", len(engine._misses))
	return 0


if __name__ == "__main__":
	sys.exit(main_bench(argv[1::]))
