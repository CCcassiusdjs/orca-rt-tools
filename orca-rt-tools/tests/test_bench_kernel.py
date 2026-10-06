"""Fix 8 (rttools/bench/kernel.py).

1. SystemEvent.__lt__ devolvia self._time > target._time; a PrioQueue
   (min-heap) removed the latest event first.
2. SystemEvent.__eq__ read target.type (nonexistent attribute; the correct one
   is target._type).
"""
from rttools.bench.kernel import SystemEvent, SystemEventType as T
from rttools.bench.queue import PrioQueue


def test_queue_pops_earliest_first():
    q = PrioQueue()
    for t in (50, 10, 40, 0, 30, 20):
        q.add(SystemEvent(t, T.SCHEDULER_IRQ))
    assert [q.pop().get_time() for _ in range(6)] == [0, 10, 20, 30, 40, 50]


def test_event_ordering():
    assert SystemEvent(1, T.SCHEDULER_IRQ) < SystemEvent(2, T.SCHEDULER_IRQ)
    assert not SystemEvent(2, T.SCHEDULER_IRQ) < SystemEvent(1, T.SCHEDULER_IRQ)


def test_event_equality():
    assert SystemEvent(5, T.TASK_FINISHED_IRQ) == SystemEvent(5, T.TASK_FINISHED_IRQ)
    assert SystemEvent(5, T.TASK_FINISHED_IRQ) != SystemEvent(5, T.SCHEDULER_IRQ)
    assert SystemEvent(5, T.TASK_FINISHED_IRQ) != SystemEvent(6, T.TASK_FINISHED_IRQ)
