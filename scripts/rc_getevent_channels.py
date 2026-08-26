#!/usr/bin/env python3
"""列出 DJI RC getevent 每个通道的实时数值。"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from math import ceil
from dataclasses import dataclass
from typing import Iterable, TextIO


AXIS_RANGES = {
    "ABS_X": (-32768, 32767),
    "ABS_Y": (-32768, 32767),
    "ABS_RX": (-32768, 32767),
    "ABS_RY": (-32768, 32767),
    "ABS_Z": (0, 255),
    "ABS_RZ": (0, 255),
    "ABS_HAT0X": (-1, 1),
    "ABS_HAT0Y": (-1, 1),
}

AXIS_TO_RC = {
    "ABS_X": "CH1?",
    "ABS_Y": "CH2?",
    "ABS_RX": "CH3?",
    "ABS_RY": "CH4?",
    "ABS_Z": "CH5?",
    "ABS_RZ": "CH6?",
    "ABS_HAT0X": "HAT_X",
    "ABS_HAT0Y": "HAT_Y",
}

KEY_NAMES = [
    "KEY_ENTER",
    "KEY_RECORD",
    "KEY_UP",
    "KEY_DOWN",
    "KEY_LEFT",
    "KEY_RIGHT",
    "BTN_GAMEPAD",
    "BTN_EAST",
    "BTN_NORTH",
    "BTN_WEST",
    "BTN_TL",
    "BTN_TR",
    "BTN_SELECT",
    "BTN_START",
    "BTN_THUMBL",
    "BTN_THUMBR",
    "BTN_DPAD_UP",
    "BTN_DPAD_DOWN",
    "BTN_DPAD_LEFT",
    "BTN_DPAD_RIGHT",
]

EVENT_RE = re.compile(
    r"(?:\[\s*(?P<ts>[0-9.]+)\]\s+)?"
    r"(?:\S+:\s+)?(?P<type>EV_ABS|EV_KEY)\s+"
    r"(?P<code>[A-Z0-9_]+)\s+"
    r"(?P<value>\S+)"
)


@dataclass
class AxisState:
    raw: int | None = None
    normalized: int | None = None
    minimum: int | None = None
    maximum: int | None = None
    changes: int = 0
    updated_at: float = 0.0


@dataclass
class KeyState:
    down: bool = False
    changes: int = 0
    updated_at: float = 0.0


def parse_value(text: str) -> int | None:
    if text == "DOWN":
        return 1
    if text == "UP":
        return 0
    try:
        value = int(text, 16)
        if value >= 0x80000000:
            value -= 0x100000000
        return value
    except ValueError:
        return None


def normalize_axis(code: str, raw: int) -> int:
    minimum, maximum = AXIS_RANGES.get(code, (-32768, 32767))
    if maximum <= minimum:
        return raw
    centered = ((raw - minimum) * 2048.0 / (maximum - minimum)) - 1024.0
    value = int(round(centered))
    return max(-1024, min(1024, value))


def event_lines_from_adb(device: str | None, event_path: str, duration: float) -> Iterable[str]:
    cmd = ["adb"]
    if device:
        cmd += ["-s", device]
    if duration > 0:
        cmd += ["shell", "timeout", str(max(1, ceil(duration))), "getevent", "-lt", event_path]
    else:
        cmd += ["shell", "getevent", "-lt", event_path]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            yield line
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


def event_lines_from_file(path: str) -> Iterable[str]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        yield from fh


def maybe_wake_device(device: str | None) -> None:
    base = ["adb"]
    if device:
        base += ["-s", device]
    subprocess.run(base + ["shell", "input", "keyevent", "WAKEUP"], capture_output=True, timeout=5)
    subprocess.run(base + ["shell", "svc", "power", "stayon", "true"], capture_output=True, timeout=5)


def clear_screen() -> None:
    if os.name == "nt":
        os.system("cls")
    else:
        print("\033[2J\033[H", end="")


def render(
    axis_states: dict[str, AxisState],
    key_states: dict[str, KeyState],
    output: TextIO,
    start_time: float,
) -> None:
    now = time.time()
    clear_screen()
    print("DJI RC getevent channel monitor", file=output)
    print(f"elapsed: {now - start_time:6.1f}s    Ctrl+C to stop", file=output)
    print("", file=output)
    print("Axes:", file=output)
    print("  rc      event       raw     norm     min     max  changes  age_ms", file=output)
    for code in AXIS_RANGES:
        state = axis_states[code]
        age_ms = int((now - state.updated_at) * 1000) if state.updated_at else -1
        raw = "-" if state.raw is None else str(state.raw)
        norm = "-" if state.normalized is None else str(state.normalized)
        amin = "-" if state.minimum is None else str(state.minimum)
        amax = "-" if state.maximum is None else str(state.maximum)
        print(
            f"  {AXIS_TO_RC[code]:<7} {code:<9} {raw:>7} {norm:>8} "
            f"{amin:>7} {amax:>7} {state.changes:>8} {age_ms:>7}",
            file=output,
        )
    print("", file=output)
    print("Keys:", file=output)
    print("  key              state  changes  age_ms", file=output)
    for code in KEY_NAMES:
        state = key_states[code]
        age_ms = int((now - state.updated_at) * 1000) if state.updated_at else -1
        text = "DOWN" if state.down else "UP"
        print(f"  {code:<16} {text:<5} {state.changes:>8} {age_ms:>7}", file=output)
    output.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="List DJI RC getevent channel values")
    parser.add_argument("-s", "--serial", help="ADB serial, e.g. 7XJCM630011XC9 or 192.168.5.249:5555")
    parser.add_argument("--event", default="/dev/input/event4", help="input device path, default /dev/input/event4")
    parser.add_argument("--duration", type=float, default=0.0, help="capture seconds; 0 means forever")
    parser.add_argument("--refresh", type=float, default=0.2, help="dashboard refresh interval seconds")
    parser.add_argument("--from-file", help="parse a saved getevent -lt text file")
    parser.add_argument("--changes", action="store_true", help="print every channel change instead of dashboard")
    parser.add_argument("--no-wake", action="store_true", help="do not wake device and keep screen on")
    args = parser.parse_args()

    axis_states = {code: AxisState() for code in AXIS_RANGES}
    key_states = {code: KeyState() for code in KEY_NAMES}
    start_time = time.time()
    next_render_at = 0.0

    if args.from_file:
        lines = event_lines_from_file(args.from_file)
    else:
        if not args.no_wake:
            maybe_wake_device(args.serial)
        lines = event_lines_from_adb(args.serial, args.event, args.duration)

    try:
        for line in lines:
            match = EVENT_RE.search(line)
            if not match:
                continue
            event_type = match.group("type")
            code = match.group("code")
            value = parse_value(match.group("value"))
            if value is None:
                continue

            now = time.time()
            if event_type == "EV_ABS" and code in axis_states:
                state = axis_states[code]
                if state.raw != value:
                    state.changes += 1
                state.raw = value
                state.normalized = normalize_axis(code, value)
                state.minimum = value if state.minimum is None else min(state.minimum, value)
                state.maximum = value if state.maximum is None else max(state.maximum, value)
                state.updated_at = now
                if args.changes:
                    print(
                        f"{now - start_time:8.3f}s axis {AXIS_TO_RC[code]:<7} {code:<9} "
                        f"raw={value:>7} norm={state.normalized:>5} "
                        f"min={state.minimum:>7} max={state.maximum:>7} n={state.changes}"
                    )
            elif event_type == "EV_KEY" and code in key_states:
                state = key_states[code]
                down = value != 0
                if state.down != down:
                    state.changes += 1
                state.down = down
                state.updated_at = now
                if args.changes:
                    text = "DOWN" if state.down else "UP"
                    print(f"{now - start_time:8.3f}s key  {code:<16} {text:<4} n={state.changes}")

            if not args.changes and now >= next_render_at:
                render(axis_states, key_states, sys.stdout, start_time)
                next_render_at = now + args.refresh
            if args.duration > 0 and now - start_time >= args.duration:
                break
    except KeyboardInterrupt:
        pass

    if not args.changes:
        render(axis_states, key_states, sys.stdout, start_time)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
