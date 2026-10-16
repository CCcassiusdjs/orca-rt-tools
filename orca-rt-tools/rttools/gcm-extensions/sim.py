from enum import Enum
from math import ceil
from gcm.terminal import error


class KernelInfo():
    SCHEDULE_IRQ_WCET: int = None    # scheduler wcet (cycles)
    SCHEDULE_IRQ_FREQ: int = None    # number of sched. IRQs per second
    SCHEDULE_APP_TIME: float = None  # app time per sched. event

    NET_IRQ_WCET_RECV_1: int = None  # driver time, malloc
    NET_IRQ_WCET_RECV_2: int = None  # driver time, recv done
    NET_IRQ_WCET_SEND: int = None    # driver time, dma activation

    CPU_SPEED: int = None   # cpu speed, in Hertz (Hz)

    def __init__(self, sfreq, swcet, netd1, netd2, netd3, cpu_speed, mwcet):
        self.SCHEDULE_IRQ_FREQ = sfreq
        self.SCHEDULE_IRQ_WCET = swcet
        self.NET_IRQ_WCET_RECV_1 = netd1
        self.NET_IRQ_WCET_RECV_2 = netd2
        self.NET_IRQ_WCET_SEND = netd3
        self.MALLOC_WCET = mwcet

        self.CPU_SPEED = cpu_speed

        self.SCHEDULE_APP_TIME = (self.CPU_SPEED / self.SCHEDULE_IRQ_FREQ) \
            - self.SCHEDULE_IRQ_WCET

        if (self.SCHEDULE_APP_TIME < 0):
            error("Kernel SCHEDULE_IRQ_FREQ is too large for the given "
                  "SCHEDULE_IRQ_WCET. Scheduler won't have enough time to "
                  "schedule tasks, nor any task will execute")


UCX_OS = KernelInfo(
    sfreq=200,
    swcet=1000,
    netd1=0,
    netd2=20,
    netd3=0,
    cpu_speed=2500000,  # 2.5MHz
    mwcet=1000
)


class AppTask:
    _wcet: int = None  # wcet, in cycles
    _name: str = None

    def __init__(self, name: str, wcet: int):
        self._wcet = wcet
        self._name = name

    def __str__(self):
        return f"{self._name} ({self._wcet})"


class AppMessageType(Enum):
    INCOMING = 1
    OUTGOING = 2


class AppMessage():
    _from: AppTask
    _to: AppTask
    _payload: int   # payload data, in bytes

    def __init__(self, payload, task_from, task_to):
        self._type = type
        self._payload = payload
        self._from = task_from
        self._to = task_to

    def __str__(self):
        return f"{self._from._name} [{self._payload}]-> ({self._to._name})"


class SystemEventType(Enum):
    APP_TIME = 0
    KERNEL_TIME = 1
    SEND_ISR = 2
    RECV_ISR_1 = 3
    RECV_ISR_2 = 4


class SystemEvent():
    _type: SystemEventType = None
    _duration: int = None
    _initial_time: int = None
    _label: str = None
    _group: str = None

    def __init__(self, itime, etype, duration, label, group):
        self._type = etype
        self._duration = duration
        self._initial_time = itime
        self._label = label
        self._group = group

    def __str__(self):
        return "\t".join([
            str(self._initial_time),
            str(self._type),
            self._label,
            self._group])


class KernelTracer():

    _event_queue: list[SystemEvent] = None
    _global_timer: int = None

    def trace(self):
        return "\n".join([str(x) for x in self._event_queue])

    def report(self):
        info = []
        info.append("")
        return ""

    def __init__(self, tasks: list[AppTask], imsg: list[AppMessage],
                 kinfo: KernelInfo):

        self._global_timer = 0
        self._event_queue = []

        for t in tasks:

            num_of_tasks = ceil(t._wcet / UCX_OS.SCHEDULE_APP_TIME)

            # build the trace
            for m in imsg:
                if m._to == t:

                    # first message interruption
                    e: SystemEvent = SystemEvent(
                        self._global_timer,
                        SystemEventType.RECV_ISR_1,
                        # ## m._payload,  # !TODO malloc time
                        UCX_OS.MALLOC_WCET,
                        f"RECV IRQ1 ({m._from._name} --> {m._to._name})",
                        t._name)

                    self._event_queue.append(e)
                    self._global_timer += int(e._duration)

                    # second message interruption
                    e = SystemEvent(
                        self._global_timer,
                        SystemEventType.RECV_ISR_2,
                        # ##UCX_OS.NET_IRQ_WCET_RECV_2,
                        m._payload,
                        f"RECV IRQ2 ({m._from._name} --> {m._to._name})",
                        t._name)

                    self._event_queue.append(e)
                    self._global_timer += int(e._duration)

            # add the necessary number of time slices
            for i in range(0, num_of_tasks):
                e: SystemEvent = SystemEvent(self._global_timer,
                                             SystemEventType.KERNEL_TIME,
                                             UCX_OS.SCHEDULE_IRQ_WCET,
                                             "KERNEL",
                                             t._name)
                self._event_queue.append(e)
                self._global_timer += int(e._duration)

                e: SystemEvent = SystemEvent(self._global_timer,
                                             SystemEventType.APP_TIME,
                                             UCX_OS.SCHEDULE_APP_TIME,
                                             f"TASK {t._name}",
                                             t._name)
                self._event_queue.append(e)
                self._global_timer += int(e._duration)

            # add outgoing messages
            for m in imsg:
                if m._from == t:
                    # dma activation
                    e: SystemEvent = SystemEvent(
                        self._global_timer,
                        SystemEventType.SEND_ISR,
                        UCX_OS.NET_IRQ_WCET_SEND,
                        f"SEND IRQ ({m._from._name} --> {m._to._name})",
                        t._name)

                    self._event_queue.append(e)
                    self._global_timer += int(e._duration)
