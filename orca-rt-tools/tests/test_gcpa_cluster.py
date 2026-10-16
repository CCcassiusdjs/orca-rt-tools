"""CPU time estimate of each PE by ORT/GCPA (rttools.gcpa.method.cluster_time) against the ORT/BENCH
sequence (rttools.bench_t.estimate.sequence): with the same costs, the finish of the last task equals the
estimate (Section 6.3 of the paper)."""
import random

import pytest

from rttools.bench_t import estimate
from rttools.gcpa.method import cluster_time


def test_cluster_time_sums_the_costs():
    assert cluster_time([285300, 586000, 140000, 808000]) == 1819300
    assert cluster_time([]) == 0
    assert cluster_time(["1000", 2000]) == 3000
    with pytest.raises(ValueError):
        cluster_time([1.5])
    with pytest.raises(ValueError):
        cluster_time([-1])


@pytest.mark.parametrize("seed", range(20))
def test_gcpa_equals_the_bench_sequence(seed):
    rng = random.Random(seed)
    costs = [(f"t{i}", rng.randint(0, 200000)) for i in range(rng.randint(1, 8))]
    seq = estimate.sequence(costs, scheduler_cycles=11000)
    assert estimate.demand(costs) == cluster_time(c for _, c in costs) == seq[costs[-1][0]]["finish"]
