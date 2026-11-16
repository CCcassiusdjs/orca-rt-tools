from enum import Enum


class SystemEventType(Enum):
    SCHEDULER_IRQ = 0
    TASK_FINISHED_IRQ = 1


class SystemEvent:
    def __init__(self: "SystemEvent", time: int, type: SystemEventType) -> None:
        self._time = time
        self._type = type

    def __lt__(self: "SystemEvent", target: "SystemEvent") -> bool:
        return self._time < target._time

    def __eq__(self: "SystemEvent", target: "SystemEvent") -> bool:
        if not isinstance(target, SystemEvent):
            return NotImplemented
        return self._time == target._time and self._type == target._type

    # __eq__ without __hash__ would make the class unhashable
    __hash__ = object.__hash__

    def __str__(self: "SystemEvent") -> str:
        return str(self._time) + str(self._type)

    def get_time(self: "SystemEvent") -> int:
        return self._time

    def get_type(self: "SystemEvent") -> SystemEventType:
        return self._type



class TaskControlBlock:
    def __eq__(self: "TaskControlBlock", target: "TaskControlBlock"):
        return self._id == target._id

    def __init__(
        self: "TaskControlBlock",
        id: int,
        name: str,
        period: int,
        capacity: int,
        deadline: int,
    ):
        self._id = id
        self._name = name
        self._period = period
        self._capacity = capacity
        self._deadline = deadline

        self._current_capacity = 0
        self._release_time = 0
        self._next_deadline = self._deadline

    def __str__(self: "TaskControlBlock"):
        ss = "[" + str(self._id) + "] " + self._name
        ss += ", p:" + str(self._period)
        ss += ", c:" + str(self._current_capacity) + "/" + str(self._capacity)
        ss += ", d:" + str(self._next_deadline) + "/" + str(self._deadline)
      
        return ss

    def str_log(self: "TaskControlBlock"):
        ss = f'{self._id} {self._name} {self._current_capacity} {self._capacity} {self._next_deadline} {self._period} {self._release_time}'
        return ss 
        
