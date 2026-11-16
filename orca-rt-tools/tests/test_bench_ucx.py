"""ORT/BENCH over the hyperperiod under the UCX-OS round robin with a
periodic tick (rttools/bench/ucx.py)."""
from rttools.bench import ucx
from rttools.bench_t import estimate


def test_one_period_equals_estimate_sequence():
    ts = [("A", 28530), ("B", 58600), ("D", 14000), ("F", 80800)]
    seq = estimate.sequence(ts, 11000)
    sim = ucx.simulate([{"name": n, "cost": c, "period": 1} for n, c in ts], 250000, 3, 11000, boundary=1)
    for n, _ in ts:
        for j in range(3):
            job = sim["jobs"][n][j]
            assert (job.start - 250000 * j, job.finish - 250000 * j) == (seq[n]["start"], seq[n]["finish"])
    assert sim["states"][1] == sim["states"][2] and sim["complete"]


def test_round_robin_with_tick_and_resume_cost():
    """y (50 cycles every tick) before x (150 cycles every 4 ticks), P = 100,
    sigma = 10: x runs after y in each tick and pays sigma at each resume."""
    sim = ucx.simulate([{"name": "y", "cost": 50, "period": 1}, {"name": "x", "cost": 150, "period": 4}],
                       100, 4, 10)
    x0 = sim["jobs"]["x"][0]
    assert (x0.start, x0.finish, x0.dispatches) == (60, 380, 4)
    assert [(j.start, j.finish) for j in sim["jobs"]["y"]] == [(10, 50), (110, 150), (210, 250), (310, 350)]
    assert sim["slices"][:4] == [(0, 50, "y"), (50, 100, "x"), (100, 150, "y"), (150, 200, "x")]
    assert all(j.finish <= j.deadline for js in sim["jobs"].values() for j in js)
    assert ucx.busy_per_phase(sim["slices"], 100, 4) == [100, 100, 100, 80]


def test_completion_at_tick_schedules_from_idle():
    """A job that ends at a tick leaves the idle task current: the tick
    starts from the first task of the circular list."""
    sim = ucx.simulate([{"name": "a", "cost": 40, "period": 1}, {"name": "b", "cost": 60, "period": 1}], 100, 2, 0)
    assert [(j.start, j.finish) for j in sim["jobs"]["a"]] == [(0, 40), (100, 140)]
    assert [(j.start, j.finish) for j in sim["jobs"]["b"]] == [(40, 100), (140, 200)]


def test_overload_misses_and_backlog():
    sim = ucx.simulate([{"name": "x", "cost": 300, "period": 4}, {"name": "y", "cost": 50, "period": 1}], 100, 8, 10)
    x = sim["jobs"]["x"]
    assert x[0].finish > x[0].deadline
    assert x[1].start == x[0].finish        # pending release: next job without a scheduler event
