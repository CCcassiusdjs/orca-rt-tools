"""Time units of traces and conversion for display.

A trace stores integer time values in a raw unit (for example, $time of a
SystemVerilog module with `timescale 100ps, or cycles of the bench). The
TUI converts the raw values to seconds, nanoseconds, milliseconds or
clock cycles. The conversion to cycles needs a clock frequency.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

SI = {"fs": 1e-15, "ps": 1e-12, "ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1.0}

# display modes, in the order the TUI cycles through them
DISPLAY_MODES = ("raw", "cycles", "ns", "us", "ms")


@dataclass(frozen=True)
class TimeUnit:
    """Raw unit of a trace.

    seconds: duration of one raw unit in seconds (None if unknown).
    name: label of the raw unit, for example "100 ps" or "cycle".
    clock_hz: clock frequency for the conversion to cycles (None if unknown).
    assumed: True when the parser could not read the unit from the input.
    """
    seconds: float | None
    name: str
    clock_hz: float | None = None
    assumed: bool = False

    def with_clock(self, clock_hz):
        return replace(self, clock_hz=clock_hz)

    def to_seconds(self, raw):
        if self.seconds is None:
            return None
        return raw * self.seconds

    def to_cycles(self, raw):
        s = self.to_seconds(raw)
        if s is None or self.clock_hz is None:
            return None
        return s * self.clock_hz

    def convert(self, raw, mode):
        """Converts a raw value (or interval) to the display mode.
        Returns None when the conversion needs a value that is unknown."""
        if mode == "raw":
            return raw
        if mode == "cycles":
            return self.to_cycles(raw)
        s = self.to_seconds(raw)
        if s is None:
            return None
        return s / SI[mode]

    def from_display(self, value, mode):
        """Inverse of convert(); returns a raw value or None."""
        if mode == "raw":
            return value
        if mode == "cycles":
            if self.seconds is None or self.clock_hz is None:
                return None
            return value / self.clock_hz / self.seconds
        if self.seconds is None:
            return None
        return value * SI[mode] / self.seconds

    def available_modes(self):
        return [m for m in DISPLAY_MODES if self.convert(1, m) is not None]

    def describe(self):
        text = "raw unit " + self.name
        if self.clock_hz:
            text += ", clock " + format_frequency(self.clock_hz)
        if self.assumed:
            text += " (assumed)"
        return text


def unit_from_text(number, suffix, clock_hz=None, assumed=False):
    """TimeUnit for a timescale such as ("100", "ps")."""
    return TimeUnit(int(number) * SI[suffix], f"{int(number)} {suffix}", clock_hz, assumed)


def cycle_unit(clock_hz=None):
    """Raw unit equal to one clock cycle."""
    seconds = None if not clock_hz else 1.0 / clock_hz
    return TimeUnit(seconds, "cycle", clock_hz)


def format_frequency(hz):
    for div, name in ((1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz")):
        if hz >= div:
            return f"{hz / div:g} {name}"
    return f"{hz:g} Hz"


MODE_SUFFIX = {"raw": "", "cycles": " cyc", "ns": " ns", "us": " µs", "ms": " ms"}


def format_value(value, mode, decimals=4):
    """Formats a converted value with thousands separators; integer modes
    (raw, cycles) keep 2 decimals only for fractional values."""
    if value is None:
        return "?"
    if mode in ("raw", "cycles") and abs(value - round(value)) < 1e-9:
        text = f"{int(round(value)):,}"
    else:
        text = f"{value:,.{2 if mode in ('raw', 'cycles') else decimals}f}"
        text = text.rstrip("0").rstrip(".")
    return text + MODE_SUFFIX[mode]


# presets offered by the TUI for logs of the manycore RTL (500 MHz clock)
RTL_CLOCK_HZ = 500e6
RTL_PRESETS = {
    "100ps": unit_from_text(100, "ps", RTL_CLOCK_HZ),   # manycore_pe without `timescale
    "1ns": unit_from_text(1, "ns", RTL_CLOCK_HZ),       # manycore_pe with `timescale 1ns/100ps
}
