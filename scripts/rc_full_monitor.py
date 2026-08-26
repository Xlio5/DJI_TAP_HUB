#!/usr/bin/env python3
"""融合 getevent 与 40007/串口 DUML，输出完整 DJI RC 遥控状态。"""

from __future__ import annotations

import argparse
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from math import ceil

import rc_40007_serial_monitor as duml
import rc_getevent_channels as ge


CHANNELS = ["CH1", "CH2", "CH3", "CH4", "CH5", "CH6"]
BUTTONS = [
    "REC",
    "SHOT",
    "L1",
    "L2",
    "L3",
    "R1",
    "R2",
    "R3",
    "BTN",
    "STOP",
    "FOCUS",
    "RTH",
    "C1",
    "C2",
    "C3",
    "UP",
    "DOWN",
    "LEFT",
    "RIGHT",
    "AIRCRAFT",
    "BACK",
]


@dataclass
class ValueState:
    value: int | str | None = None
    raw: int | None = None
    code: str = "-"
    source: str = "-"
    updated_at: float = 0.0
    changes: int = 0

    def update(self, value: int | str, raw: int | None, code: str, source: str, now: float) -> bool:
        changed = self.value != value or self.raw != raw
        if changed:
            self.changes += 1
        self.value = value
        self.raw = raw
        self.code = code
        self.source = source
        self.updated_at = now
        return changed


def clear_screen() -> None:
    if os.name == "nt":
        os.system("cls")
    else:
        print("\033[2J\033[H", end="")


def age_ms(st: ValueState, now: float) -> int:
    return int((now - st.updated_at) * 1000) if st.updated_at else -1


def event_lines_from_adb(serial: str | None, duration: float) -> tuple[subprocess.Popen[str], object]:
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    getevent_args = ["getevent", "-lt"]
    if duration > 0:
        cmd += ["shell", "timeout", str(max(1, ceil(duration)))] + getevent_args
    else:
        cmd += ["shell"] + getevent_args
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
    return proc, proc.stdout


def getevent_reader(
    serial: str | None,
    duration: float,
    out: queue.Queue[tuple[str, object]],
) -> None:
    proc, lines = event_lines_from_adb(serial, duration)
    out.put(("note", f"getevent started: all input devices"))
    try:
        for line in lines:
            match = ge.EVENT_RE.search(line)
            if not match:
                if "Usage: getevent" in line:
                    out.put(("note", line.strip()))
                continue
            event_type = match.group("type")
            code = match.group("code")
            value = ge.parse_value(match.group("value"))
            if value is None:
                continue
            if event_type == "EV_ABS" and code in ge.AXIS_TO_RC:
                out.put(("axis", (code, value)))
            elif event_type == "EV_KEY" and code in ge.KEY_NAMES:
                out.put(("key", (code, value != 0)))
    finally:
        proc.terminate()
        out.put(("note", "getevent stopped"))


def start_duml_sources(args: argparse.Namespace, out: queue.Queue[tuple[str, object]]) -> set[str]:
    raw_events: queue.Queue[tuple[str, bytes | None, str | None]] = queue.Queue()
    source_names: set[str] = set()
    if args.adb40007 is not None:
        serial = args.adb40007 or args.adb_serial or None
        name = f"adb40007:{serial or 'default'}:{args.adb_host}:{args.adb_port}"
        source_names.add(name)
        threading.Thread(
            target=duml.adb_40007_reader,
            args=(name, serial, args.adb_host, args.adb_port, raw_events),
            daemon=True,
        ).start()
    if args.tcp:
        host, _, port_text = args.tcp.partition(":")
        port = int(port_text or "40007")
        name = f"tcp:{host}:{port}"
        source_names.add(name)
        threading.Thread(target=duml.tcp_reader, args=(name, host, port, raw_events), daemon=True).start()
    if args.serial:
        name = f"serial:{args.serial}"
        source_names.add(name)
        threading.Thread(target=duml.serial_reader, args=(name, args.serial, args.baud, raw_events), daemon=True).start()

    def parser_loop() -> None:
        parsers = {name: duml.DumlStreamParser() for name in source_names}
        while True:
            name, data, note = raw_events.get()
            if note:
                out.put(("note", f"{name}: {note}"))
            if not data:
                continue
            parser_for_source = parsers.setdefault(name, duml.DumlStreamParser())
            for pkt in parser_for_source.feed(data):
                st = duml.decode_rc_packet(pkt)
                if st:
                    out.put(("duml", (name, st)))

    threading.Thread(target=parser_loop, daemon=True).start()
    return source_names


def update_from_duml(
    source: str,
    st: duml.RcState,
    axes: dict[str, ValueState],
    buttons: dict[str, ValueState],
    mode: ValueState,
    dial: ValueState,
    now: float,
) -> bool:
    changed = False
    for idx, name in enumerate(CHANNELS):
        changed |= axes[name].update(st.ch[idx], None, st.kind, source, now)
    key_values = {
        "REC": st.rec,
        "SHOT": st.shot,
        "BTN": st.btn,
        "STOP": st.stop,
        "FOCUS": st.focus,
        "RTH": st.rth,
        "C1": st.c1,
        "C2": st.c2,
        "C3": st.c3,
        "UP": st.up,
        "DOWN": st.down,
        "LEFT": st.left,
        "RIGHT": st.right,
        "AIRCRAFT": st.aircraft,
        "BACK": st.back,
    }
    for key, value in key_values.items():
        changed |= buttons[key].update(value, None, st.kind, source, now)
    changed |= mode.update(st.mode, None, st.kind, source, now)
    changed |= dial.update(st.dial, None, st.kind, source, now)
    return changed


def render(
    axes: dict[str, ValueState],
    buttons: dict[str, ValueState],
    mode: ValueState,
    dial: ValueState,
    notes: list[str],
    start: float,
) -> None:
    now = time.time()
    clear_screen()
    print("DJI RC full monitor")
    print(f"elapsed: {now - start:6.1f}s    Ctrl+C to stop")
    print("")
    print("Channels:")
    print("  ch    value     raw      code       source        age_ms changes")
    for name in CHANNELS:
        st = axes[name]
        value = "-" if st.value is None else str(st.value)
        raw = "-" if st.raw is None else str(st.raw)
        print(f"  {name:<5} {value:>6} {raw:>7} {st.code:<10} {st.source:<13} {age_ms(st, now):>7} {st.changes:>7}")
    print("")
    print("Buttons:")
    print("  key       value code       source        age_ms changes")
    for name in BUTTONS:
        st = buttons[name]
        value = "-" if st.value is None else str(st.value)
        print(f"  {name:<9} {value:>5} {st.code:<10} {st.source:<13} {age_ms(st, now):>7} {st.changes:>7}")
    print("")
    print("Switches:")
    print(f"  MODE      {str(mode.value or '-'):>5} {mode.code:<10} {mode.source:<13} {age_ms(mode, now):>7} {mode.changes:>7}")
    print(f"  DIAL      {str(dial.value if dial.value is not None else '-'):>5} {dial.code:<10} {dial.source:<13} {age_ms(dial, now):>7} {dial.changes:>7}")
    if notes:
        print("")
        print("Notes:")
        for note in notes[-5:]:
            print(f"  {note}")


def print_change(label: str, state: ValueState, start: float) -> None:
    value = "-" if state.value is None else str(state.value)
    raw = "" if state.raw is None else f" raw={state.raw}"
    print(f"{time.time() - start:8.3f}s {label:<9} value={value:<5}{raw} code={state.code} source={state.source}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Full DJI RC monitor from getevent plus 40007/serial DUML")
    parser.add_argument("-s", "--adb-serial", help="ADB serial for getevent and default adb40007")
    parser.add_argument("--no-getevent", action="store_true", help="do not read Android getevent")
    parser.add_argument("--adb40007", nargs="?", const="", help="read 40007 via adb exec-out; optional serial")
    parser.add_argument("--adb-host", default="127.0.0.1", help="Android-side 40007 host, default 127.0.0.1")
    parser.add_argument("--adb-port", type=int, default=40007, help="Android-side 40007 port, default 40007")
    parser.add_argument("--tcp", help="direct TCP DUML source, e.g. 192.168.5.249:40007")
    parser.add_argument("--serial", help="V3s serial source, e.g. COM5")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--refresh", type=float, default=0.2)
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--changes", action="store_true", help="print changed fields instead of dashboard")
    parser.add_argument("--no-wake", action="store_true", help="do not wake Android device")
    args = parser.parse_args()

    if args.adb40007 is None and not args.tcp and not args.serial:
        args.adb40007 = ""
    if args.no_getevent and args.adb40007 is None and not args.tcp and not args.serial:
        parser.error("set at least one source when --no-getevent is used: --adb40007, --tcp, or --serial")

    events: queue.Queue[tuple[str, object]] = queue.Queue()
    axes = {name: ValueState() for name in CHANNELS}
    buttons = {name: ValueState() for name in BUTTONS}
    mode = ValueState()
    dial = ValueState()
    notes: list[str] = []
    start = time.time()
    next_render = 0.0

    if not args.no_getevent:
        if not args.no_wake:
            ge.maybe_wake_device(args.adb_serial)
        threading.Thread(target=getevent_reader, args=(args.adb_serial, args.duration, events), daemon=True).start()
    start_duml_sources(args, events)

    if not args.changes:
        render(axes, buttons, mode, dial, notes, start)
    else:
        print("monitoring full RC state; move sticks or press keys, Ctrl+C to stop", flush=True)

    try:
        while True:
            now = time.time()
            if args.duration > 0 and now - start >= args.duration:
                break
            try:
                kind, payload = events.get(timeout=0.05)
            except queue.Empty:
                if not args.changes and now >= next_render:
                    render(axes, buttons, mode, dial, notes, start)
                    next_render = now + args.refresh
                continue

            changed_labels: list[tuple[str, ValueState]] = []
            now = time.time()
            if kind == "note":
                notes.append(str(payload))
            elif kind == "axis":
                code, raw = payload  # type: ignore[misc]
                name = ge.AXIS_TO_RC.get(code)
                if name in axes:
                    st = axes[name]
                    if st.update(ge.normalize_axis(code, raw), raw, code, "getevent", now):
                        changed_labels.append((name, st))
            elif kind == "key":
                code, pressed = payload  # type: ignore[misc]
                name = ge.KEY_TO_RC.get(code)
                if name in buttons:
                    st = buttons[name]
                    if st.update(1 if pressed else 0, None, code, "getevent", now):
                        changed_labels.append((name, st))
            elif kind == "duml":
                source, st = payload  # type: ignore[misc]
                before = {name: axes[name].changes for name in CHANNELS}
                before_buttons = {name: buttons[name].changes for name in BUTTONS}
                before_mode = mode.changes
                before_dial = dial.changes
                update_from_duml(source, st, axes, buttons, mode, dial, now)
                for name in CHANNELS:
                    if axes[name].changes != before[name]:
                        changed_labels.append((name, axes[name]))
                for name in BUTTONS:
                    if buttons[name].changes != before_buttons[name]:
                        changed_labels.append((name, buttons[name]))
                if mode.changes != before_mode:
                    changed_labels.append(("MODE", mode))
                if dial.changes != before_dial:
                    changed_labels.append(("DIAL", dial))

            if args.changes:
                for label, state in changed_labels:
                    print_change(label, state, start)
            elif now >= next_render:
                render(axes, buttons, mode, dial, notes, start)
                next_render = now + args.refresh
    except KeyboardInterrupt:
        pass

    if not args.changes:
        render(axes, buttons, mode, dial, notes, start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
