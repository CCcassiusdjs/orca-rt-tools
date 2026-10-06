"""Fix 10 (rttools/bench/engine.py, simulate and schedule;
rttools/bench/scheduling.py, RoundRobinSchedule).

Defects of the original loop:
1. self._queue.push(...): PrioQueue only has add (AttributeError).
2. top_event._time + SystemEventType.SCHEDULER_IRQ added an Enum to the
   time (TypeError); the correct operation is to add the quantum.
3. top_event.type = ... created a new attribute; the event type stayed
   unchanged.
4. svg_append called svg_init (nonexistent) and wrote to a fixed path.
5. get_next_release failed with an empty blocked list.
6. RoundRobinSchedule rotated the queue after the engine had already put the preempted task
   at the tail: the double rotation skipped tasks.
7. The deadline was checked only at dispatch, not at completion.

The expected values below come from manual execution of the algorithms.
"""
from rttools.gsl.graph import Graph, GraphNode
from rttools.bench.engine import SingleCoreEngine
from rttools.bench.scheduling import RoundRobinSchedule, EarliestDeadlineFirst


def graph(*tasks):
    g = Graph()
    for t in tasks:
        label, wcet, period, deadline = t
        data = {"label": label, "wcet": str(wcet)}
        if period is not None:
            data["period"] = str(period)
        if deadline is not None:
            data["deadline"] = str(deadline)
        g._nodes.append(GraphNode(g.get_new_id(), data))
    return g


def test_round_robin_trace():
    eng = SingleCoreEngine(graph(("A", 3, 10, 10), ("B", 5, 10, 10)),
                           RoundRobinSchedule, quantum=2)
    end = eng.simulate(10, False)
    assert end == 10
    assert eng._trace == [(0, 2, "A"), (2, 4, "B"), (4, 5, "A"), (5, 7, "B"), (7, 8, "B")]
    assert eng._misses == []


def test_edf_trace_and_second_job():
    # B with deadline 20: at the release of A at t=5 (deadline 10), A preempts B
    eng = SingleCoreEngine(graph(("A", 2, 5, 5), ("B", 4, 20, 20)),
                           EarliestDeadlineFirst, quantum=1)
    eng.simulate(10, False)
    assert eng.merged_trace() == [(0, 2, "A"), (2, 5, "B"), (5, 7, "A"), (7, 8, "B")]
    assert eng._misses == []


def test_deadline_miss_detected_at_completion():
    eng = SingleCoreEngine(graph(("A", 6, 10, 5),), EarliestDeadlineFirst, quantum=4)
    eng.simulate(10, False)
    assert eng.merged_trace() == [(0, 6, "A")]
    assert eng._misses == [("A", 5, 6)]


def test_one_shot_jobs_finish_and_simulation_stops():
    eng = SingleCoreEngine(graph(("A", 3, None, None), ("B", 2, None, None)),
                           RoundRobinSchedule, quantum=20)
    end = eng.simulate(1000, False)
    assert eng.merged_trace() == [(0, 3, "A"), (3, 5, "B")]
    assert end == 5          # with no pending events, the simulation ends


# --- independent review: deadline misses of unfinished jobs and
# --- zero period
from rttools.bench.scheduling import RateMonotonicScheduling
import pytest


def test_starved_job_deadline_miss_reported():
    # RM, quantum 1: A ocupa o processador; B nunca executa e perde o prazo 10
    eng = SingleCoreEngine(graph(("A", 5, 5, 5), ("B", 1, 10, 10)),
                           RateMonotonicScheduling, quantum=1)
    eng.simulate(100, False)
    assert ("B", 10, None) in eng._misses


def test_unfinished_job_miss_reported_once():
    eng = SingleCoreEngine(graph(("A", 50, 10, 10),), EarliestDeadlineFirst, quantum=1)
    eng.simulate(30, False)
    assert eng._misses[0] == ("A", 10, None)
    assert len([m for m in eng._misses if m[1] == 10]) == 1


def test_zero_period_rejected():
    with pytest.raises(ValueError):
        SingleCoreEngine(graph(("A", 0, 0, None),), RateMonotonicScheduling, quantum=1)
