"""Trace model shared by the viewers: slices on lanes and point marks."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field

from rttools.tui.model.timeunit import TimeUnit

IDLE_LABELS = frozenset({"IDLE", "idle"})


@dataclass(frozen=True)
class Slice:
    """Interval [start, end) of `label` on `lane`. kind: task, idle,
    kernel or packet."""
    lane: str
    start: int
    end: int
    label: str
    kind: str = "task"
    detail: str = ""

    @property
    def duration(self):
        return self.end - self.start


@dataclass(frozen=True)
class Mark:
    """Point event on a lane. kind: send, recv, release, deadline, miss,
    event."""
    lane: str
    time: int
    kind: str
    label: str


@dataclass
class Trace:
    name: str
    unit: TimeUnit
    lanes: list = field(default_factory=list)
    slices: list = field(default_factory=list)
    marks: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self.reindex()

    def reindex(self):
        """Sorts the slices and marks of each lane; adds missing lanes in
        order of appearance."""
        seen = set(self.lanes)
        for s in self.slices:
            if s.lane not in seen:
                self.lanes.append(s.lane)
                seen.add(s.lane)
        for m in self.marks:
            if m.lane not in seen:
                self.lanes.append(m.lane)
                seen.add(m.lane)
        self._by_lane = {lane: [] for lane in self.lanes}
        for s in sorted(self.slices, key=lambda s: (s.start, s.end)):
            self._by_lane[s.lane].append(s)
        self._maxend = {}
        for lane, v in self._by_lane.items():
            acc, m = [], None
            for sl in v:
                m = sl.end if m is None else max(m, sl.end)
                acc.append(m)
            self._maxend[lane] = acc
        self._marks_by_lane = {lane: [] for lane in self.lanes}
        for m in sorted(self.marks, key=lambda m: m.time):
            self._marks_by_lane[m.lane].append(m)
        self._mark_times = {lane: [m.time for m in v] for lane, v in self._marks_by_lane.items()}
        times = [s.start for s in self.slices] + [s.end for s in self.slices] + [m.time for m in self.marks]
        self.t0 = min(times) if times else 0
        self.t1 = max(times) if times else 0
        self._event_times = sorted(set(
            [s.start for s in self.slices] + [s.end for s in self.slices] + [m.time for m in self.marks]))

    def lane_slices(self, lane):
        return self._by_lane.get(lane, [])

    def lane_marks(self, lane):
        return self._marks_by_lane.get(lane, [])

    def _first_candidate(self, lane, t):
        """Index of the first slice of `lane` whose end is above t (slices
        are sorted by start; _maxend is the running maximum of the ends)."""
        return bisect_right(self._maxend.get(lane, []), t)

    def slices_between(self, lane, t0, t1):
        """Slices of `lane` that intersect [t0, t1); a zero-length slice
        counts when t0 <= start < t1."""
        lst = self._by_lane.get(lane, [])
        out = []
        for s in lst[self._first_candidate(lane, t0 - 1):]:
            if s.start >= t1:
                break
            if s.end > t0 or (s.start == s.end and s.start >= t0):
                out.append(s)
        return out

    def slice_at(self, lane, t):
        """Last slice of `lane` (by start) that contains t."""
        found = None
        for s in self._by_lane.get(lane, [])[self._first_candidate(lane, t):]:
            if s.start > t:
                break
            if s.start <= t < s.end:
                found = s
        return found

    def marks_between(self, lane, t0, t1):
        """Marks of `lane` with t0 <= time < t1."""
        lst = self._marks_by_lane.get(lane, [])
        times = self._mark_times.get(lane, [])
        return lst[bisect_left(times, t0):bisect_left(times, t1)]

    def next_event(self, t):
        i = bisect_right(self._event_times, t)
        return self._event_times[i] if i < len(self._event_times) else None

    def prev_event(self, t):
        i = bisect_left(self._event_times, t) - 1
        return self._event_times[i] if i >= 0 else None

    def labels(self):
        """Distinct slice labels in order of appearance."""
        out = []
        seen = set()
        for s in sorted(self.slices, key=lambda s: s.start):
            if s.label not in seen:
                seen.add(s.label)
                out.append(s.label)
        return out

    def is_idle(self, s):
        return s.kind == "idle" or s.label in IDLE_LABELS
