#!/usr/bin/env python3
"""同时观测 40007 和 V3s 115200 串口里的 DJI RC DUML 消息。"""

from __future__ import annotations

import argparse
import subprocess
import queue
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path


DUML_SOF = 0x55
DUML_MIN_PKT = 13
DUML_MAX_PKT = 1024


@dataclass
class RcState:
    kind: str
    ch: list[int]
    mode: str = "?"
    btn: int = 0
    stop: int = 0
    focus: int = 0
    shot: int = 0
    rec: int = 0
    rth: int = 0
    up: int = 0
    down: int = 0
    left: int = 0
    right: int = 0
    aircraft: int = 0
    back: int = 0
    c1: int = 0
    c2: int = 0
    c3: int = 0
    dial: int = 0


@dataclass
class DumlPacket:
    raw: bytes
    cmd_set: int
    cmd_id: int
    payload: bytes


def hex_short(data: bytes, limit: int = 48) -> str:
    text = data[:limit].hex(" ")
    if len(data) > limit:
        text += " ..."
    return text


def decode_rc_ae(payload: bytes) -> RcState | None:
    if len(payload) < 17:
        return None
    b0, b1, b2, b4 = payload[0], payload[1], payload[2], payload[4]
    ch: list[int] = []
    for idx in range(6):
        off = 5 + idx * 2
        raw = payload[off] | (payload[off + 1] << 8)
        ch.append(raw - 1024)
    # 实机已确认 CH5/CH6 需要对调才对应物理控件。
    ch[4], ch[5] = ch[5], ch[4]
    mode_bits = b2 & 0x03
    mode = "S" if mode_bits == 0 else "N" if mode_bits == 1 else "F" if mode_bits == 2 else "?"
    return RcState(
        kind="RC/0xAE",
        ch=ch,
        mode=mode,
        btn=(b1 >> 3) & 1,
        stop=(b0 >> 4) & 1,
        focus=(b0 >> 7) & 1,
        shot=(b0 >> 6) & 1,
        rec=b1 & 1,
        rth=(b0 >> 5) & 1,
        up=(b1 >> 7) & 1,
        down=(b1 >> 6) & 1,
        left=(b1 >> 5) & 1,
        right=(b1 >> 4) & 1,
        aircraft=(b1 >> 2) & 1,
        back=(b1 >> 1) & 1,
        c1=(b2 >> 2) & 1,
        c2=(b2 >> 3) & 1,
        c3=(b2 >> 4) & 1,
        dial=b4,
    )


def special_ch(payload: bytes, start: int) -> int:
    byte_off = start // 8
    bit_off = start % 8
    value = 0
    for idx in range(4):
        if byte_off + idx < len(payload):
            value |= payload[byte_off + idx] << (idx * 8)
    raw = (value >> bit_off) & 0x3FF
    mark_byte = (start + 10) // 8
    mark_bit = (start + 10) % 8
    if mark_byte < len(payload):
        raw |= ((payload[mark_byte] >> mark_bit) & 1) << 10
    return raw - 1024


def decode_special_02(payload: bytes) -> RcState | None:
    if len(payload) < 13:
        return None
    starts = [8, 19, 30, 41, 52, 63]
    ch = [special_ch(payload, start) for start in starts]
    mode_bits = (payload[12] >> 2) & 0x03
    mode = "S" if mode_bits == 0 else "N" if mode_bits == 1 else "F" if mode_bits == 2 else "?"
    return RcState(
        kind="SPECIAL/0x02",
        ch=ch,
        mode=mode,
        stop=(payload[12] >> 4) & 1,
        focus=(payload[10] >> 6) & 1,
        shot=payload[12] & 1,
        rec=(payload[12] >> 5) & 1,
    )


def decode_rc_packet(pkt: DumlPacket) -> RcState | None:
    if pkt.cmd_set == 0x06 and pkt.cmd_id == 0xAE:
        return decode_rc_ae(pkt.payload)
    if pkt.cmd_set == 0x01 and pkt.cmd_id == 0x02:
        return decode_special_02(pkt.payload)
    return None


def format_rc(st: RcState) -> str:
    base = (
        f"{st.kind:<12} "
        f"CH1={st.ch[0]:+5d} CH2={st.ch[1]:+5d} CH3={st.ch[2]:+5d} "
        f"CH4={st.ch[3]:+5d} CH5={st.ch[4]:+5d} CH6={st.ch[5]:+5d} "
        f"MODE={st.mode} BTN={st.btn} STOP={st.stop} FOCUS={st.focus} "
        f"SHOT={st.shot} REC={st.rec}"
    )
    if st.kind == "RC/0xAE":
        base += (
            f" C1={st.c1} C2={st.c2} C3={st.c3} DIAL={st.dial} RTH={st.rth} "
            f"UP={st.up} DN={st.down} L={st.left} R={st.right} AC={st.aircraft} BACK={st.back}"
        )
    return base


class DumlStreamParser:
    def __init__(self) -> None:
        self.buf = bytearray()

    def feed(self, data: bytes) -> list[DumlPacket]:
        self.buf.extend(data)
        packets: list[DumlPacket] = []
        while True:
            try:
                sof = self.buf.index(DUML_SOF)
            except ValueError:
                if len(self.buf) > DUML_MAX_PKT:
                    del self.buf[:-3]
                break
            if sof:
                del self.buf[:sof]
            if len(self.buf) < 4:
                break
            ver_len = self.buf[1] | (self.buf[2] << 8)
            pkt_len = ver_len & 0x03FF
            version = (ver_len >> 10) & 0x3F
            if version > 1 or pkt_len < DUML_MIN_PKT or pkt_len > DUML_MAX_PKT:
                del self.buf[0]
                continue
            if len(self.buf) < pkt_len:
                break
            raw = bytes(self.buf[:pkt_len])
            del self.buf[:pkt_len]
            # 这里先不做 CRC 硬拦截，现场抓包阶段优先把同源数据显出来。
            packets.append(DumlPacket(raw=raw, cmd_set=raw[9], cmd_id=raw[10], payload=raw[11:-2]))
        return packets


def tcp_reader(name: str, host: str, port: int, out: queue.Queue[tuple[str, bytes | None, str | None]]) -> None:
    while True:
        try:
            with socket.create_connection((host, port), timeout=5) as sock:
                sock.settimeout(1)
                out.put((name, None, f"connected {host}:{port}"))
                while True:
                    try:
                        data = sock.recv(4096)
                    except socket.timeout:
                        continue
                    if not data:
                        raise OSError("tcp closed")
                    out.put((name, data, None))
        except Exception as exc:
            out.put((name, None, f"tcp reconnect after error: {exc}"))
            time.sleep(1)


def adb_40007_reader(
    name: str,
    serial: str | None,
    host: str,
    port: int,
    out: queue.Queue[tuple[str, bytes | None, str | None]],
) -> None:
    while True:
        cmd = ["adb"]
        if serial:
            cmd += ["-s", serial]
        cmd += ["exec-out", "toybox", "nc", host, str(port)]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            assert proc.stdout is not None
            out.put((name, None, f"adb exec-out toybox nc {host} {port}"))
            while True:
                data = proc.stdout.read1(4096)
                if not data:
                    break
                out.put((name, data, None))
            err = b""
            if proc.stderr is not None:
                err = proc.stderr.read(1024)
            rc = proc.wait(timeout=2)
            msg = f"adb nc exited rc={rc}"
            if err:
                msg += f" stderr={err.decode('utf-8', errors='replace').strip()}"
            raise OSError(msg)
        except Exception as exc:
            out.put((name, None, f"adb reconnect after error: {exc}"))
            time.sleep(1)


def serial_reader(name: str, port: str, baud: int, out: queue.Queue[tuple[str, bytes | None, str | None]]) -> None:
    try:
        import serial  # type: ignore
    except ImportError:
        out.put((name, None, "pyserial missing: pip install pyserial"))
        return
    while True:
        try:
            with serial.Serial(port, baudrate=baud, timeout=0.2) as ser:
                out.put((name, None, f"opened {port} @{baud}"))
                while True:
                    data = ser.read(ser.in_waiting or 1)
                    if data:
                        out.put((name, data, None))
        except Exception as exc:
            out.put((name, None, f"serial reopen after error: {exc}"))
            time.sleep(1)


def file_reader(name: str, path: Path, out: queue.Queue[tuple[str, bytes | None, str | None]]) -> None:
    out.put((name, path.read_bytes(), f"loaded {path}"))


def start_source_threads(args: argparse.Namespace, out: queue.Queue[tuple[str, bytes | None, str | None]]) -> set[str]:
    names: set[str] = set()
    if args.adb is not None:
        serial = args.adb or None
        name = f"adb:{serial or 'default'}:{args.adb_host}:{args.adb_port}"
        names.add(name)
        threading.Thread(
            target=adb_40007_reader,
            args=(name, serial, args.adb_host, args.adb_port, out),
            daemon=True,
        ).start()
    if args.tcp:
        host, _, port_text = args.tcp.partition(":")
        port = int(port_text or "40007")
        name = f"tcp:{host}:{port}"
        names.add(name)
        threading.Thread(target=tcp_reader, args=(name, host, port, out), daemon=True).start()
    if args.serial:
        name = f"serial:{args.serial}"
        names.add(name)
        threading.Thread(target=serial_reader, args=(name, args.serial, args.baud, out), daemon=True).start()
    if args.file:
        name = f"file:{args.file}"
        names.add(name)
        threading.Thread(target=file_reader, args=(name, Path(args.file), out), daemon=True).start()
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor DJI RC DUML messages from adb 40007, TCP 40007, and V3s serial")
    parser.add_argument(
        "--adb",
        nargs="?",
        const="",
        help="ADB source. Optional serial, e.g. --adb 7XJCM630011XC9 or --adb 192.168.5.249:5555",
    )
    parser.add_argument("--adb-host", default="127.0.0.1", help="host to connect inside Android, default 127.0.0.1")
    parser.add_argument("--adb-port", type=int, default=40007, help="port to connect inside Android, default 40007")
    parser.add_argument("--tcp", help="TCP source, e.g. 192.168.5.249:40007")
    parser.add_argument("--serial", help="serial source, e.g. COM5")
    parser.add_argument("--baud", type=int, default=115200, help="serial baud, default 115200")
    parser.add_argument("--file", help="offline binary dump")
    parser.add_argument("--dump-all", action="store_true", help="print non-RC DUML packets too")
    parser.add_argument("--hex", action="store_true", help="print packet hex after decoded line")
    parser.add_argument("--duration", type=float, default=0.0, help="seconds to run; 0 means forever")
    args = parser.parse_args()

    if args.adb is None and not (args.tcp or args.serial or args.file):
        parser.error("set at least one source: --adb, --tcp, --serial, or --file")

    events: queue.Queue[tuple[str, bytes | None, str | None]] = queue.Queue()
    source_names = start_source_threads(args, events)
    parsers = {name: DumlStreamParser() for name in source_names}
    counts = {name: 0 for name in source_names}
    start = time.time()

    while True:
        if args.duration > 0 and time.time() - start >= args.duration:
            break
        try:
            name, data, note = events.get(timeout=0.2)
        except queue.Empty:
            continue
        elapsed = time.time() - start
        if note:
            print(f"{elapsed:8.3f}s [{name}] {note}", flush=True)
        if not data:
            continue
        parser_for_source = parsers.setdefault(name, DumlStreamParser())
        for pkt in parser_for_source.feed(data):
            counts[name] = counts.get(name, 0) + 1
            st = decode_rc_packet(pkt)
            prefix = (
                f"{elapsed:8.3f}s [{name}] #{counts[name]:05d} "
                f"cmd={pkt.cmd_set:02X}/{pkt.cmd_id:02X} len={len(pkt.raw):03d}"
            )
            if st:
                print(f"{prefix} {format_rc(st)}", flush=True)
                if args.hex:
                    print(f"           hex {hex_short(pkt.raw)}", flush=True)
            elif args.dump_all:
                print(f"{prefix} payload={len(pkt.payload):03d} {hex_short(pkt.payload)}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
