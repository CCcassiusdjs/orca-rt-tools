from rttools.bench.kernel import TaskControlBlock

class RateMonotonicScheduling():
    @classmethod
    def schedule(self: "RateMonotonicScheduling", r: "list[TaskControlBlock]"):
        # RM: shortest period first; a task without a period goes last
        return sorted(r, key=lambda e: e._period if e._period is not None else float("inf"))

class LeastSlackTimeScheduling():
    @classmethod
    def schedule(self: "LeastSlackTimeScheduling", r: "list[TaskControlBlock]"):
        return sorted(r, key=lambda e: e._capacity - e._current_capacity, reverse=False)

class LeastLaxityFirstScheduling():
    @classmethod
    def schedule(self: "LeastLaxityFirstScheduling", r: "list[TaskControlBlock]"):
        return sorted(r, key=lambda e: (e._deadline - e._period), reverse=False)

class EarliestDeadlineFirst():
    @classmethod
    def schedule(self: "EarliestDeadlineFirst", r: "list[TaskControlBlock]"):
        return sorted(r, key=lambda e: e._next_deadline if e._next_deadline is not None else float("inf"))

class DeadlineMonotonicSchedule():
    @classmethod
    def schedule(self: "DeadlineMonotonicSchedule", r: "list[TaskControlBlock]"):
        return sorted(r, key=lambda e: e._deadline if e._deadline is not None else float("inf"))

class RoundRobinSchedule():
    @classmethod
    def schedule(self: "RoundRobinSchedule", r: "list[TaskControlBlock]"):
        # the engine already puts the preempted task at the queue tail: the
        # arrival order (FIFO) produces the round robin
        return list(r)
        

