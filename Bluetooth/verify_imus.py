#!/usr/bin/env python3
"""Record raw, time-aligned verification data from WIT IMU1 and IMU2.

Connects to both configured IMUs, waits for Enter, then logs a fixed-rate
wide CSV.  Per-device packet arrival times and orientation skew are retained
so questionable data can be traced to either the sensor or BLE timing.
"""

import argparse
import asyncio
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

from bleak import BleakClient, BleakScanner

# Physical sensor labels verified during the IMU1/IMU2 swap check.
IMUS = {"IMU1": "D4:3F:17:2F:EC:51", "IMU2": "D6:DC:FD:A3:9D:59"}
NOTIFY_CHAR = "0000ffe4-0000-1000-8000-00805f9a34fb"
AXES = ("x", "y", "z")
PACKET_NAMES = {0x51: "acceleration", 0x52: "angular_velocity",
                0x53: "euler_angle", 0x54: "magnetic_field",
                0x59: "quaternion", 0x61: "ble_accel_gyro_angle"}


def int16_le(low, high):
    value = low | (high << 8)
    return value - 65536 if value >= 32768 else value


def triplet(packet, scale):
    return tuple(int16_le(packet[i], packet[i + 1]) / 32768.0 * scale
                 for i in (2, 4, 6))


class WitFrameParser:
    """Reassemble WIT frames split/combined by BLE notifications."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        frames = []
        while len(self.buffer) >= 2:
            start = self.buffer.find(0x55)
            if start < 0:
                self.buffer.clear()
                break
            if start:
                del self.buffer[:start]
            if len(self.buffer) < 2:
                break
            kind = self.buffer[1]
            if kind not in PACKET_NAMES:
                del self.buffer[0]
                continue
            # BLE 0x61 has a two-byte header plus nine int16 values:
            # accel XYZ, gyro XYZ, then Euler angle XYZ = 20 bytes total.
            length = 20 if kind == 0x61 else 11
            if len(self.buffer) < length:
                break
            packet = bytes(self.buffer[:length])
            del self.buffer[:length]
            # Standard 11-byte WIT frames include a checksum. BLE 0x61 is a
            # fixed 20-byte combined frame without this 11-byte checksum.
            if kind != 0x61 and (sum(packet[:10]) & 0xFF) != packet[10]:
                continue
            frames.append(packet)
        return frames


def new_state():
    state = {f"accel_{a}_g": None for a in AXES}
    state.update({f"gyro_{a}_dps": None for a in AXES})
    state.update({f"mag_{a}": None for a in AXES})
    state.update({f"angle_{a}_deg": None for a in AXES})
    state.update({f"quat_{a}": None for a in ("w", "x", "y", "z")})
    state.update(temperature_c=None, last_rx_s=None, last_angle_rx_s=None,
                 last_packet_type=None, last_packet_name=None,
                 last_packet_hex=None)
    return state


def update_state(state, packet, received_s):
    kind = packet[1]
    if kind == 0x51:
        for axis, value in zip(AXES, triplet(packet, 16.0)):
            state[f"accel_{axis}_g"] = value
        state["temperature_c"] = int16_le(packet[8], packet[9]) / 100
    elif kind == 0x52:
        for axis, value in zip(AXES, triplet(packet, 2000.0)):
            state[f"gyro_{axis}_dps"] = value
        state["temperature_c"] = int16_le(packet[8], packet[9]) / 100
    elif kind == 0x53:
        for axis, value in zip(AXES, triplet(packet, 180.0)):
            state[f"angle_{axis}_deg"] = value
        state["last_angle_rx_s"] = received_s
    elif kind == 0x61:
        for axis, index in zip(AXES, (2, 4, 6)):
            state[f"accel_{axis}_g"] = int16_le(packet[index], packet[index + 1]) / 32768.0 * 16.0
        for axis, index in zip(AXES, (8, 10, 12)):
            state[f"gyro_{axis}_dps"] = int16_le(packet[index], packet[index + 1]) / 32768.0 * 2000.0
        for axis, index in zip(AXES, (14, 16, 18)):
            state[f"angle_{axis}_deg"] = int16_le(packet[index], packet[index + 1]) / 32768.0 * 180.0
        state["last_angle_rx_s"] = received_s
    elif kind == 0x54:
        for axis, index in zip(AXES, (2, 4, 6)):
            state[f"mag_{axis}"] = int16_le(packet[index], packet[index + 1])
    elif kind == 0x59:
        for name, index in zip(("w", "x", "y", "z"), (2, 4, 6, 8)):
            state[f"quat_{name}"] = int16_le(packet[index], packet[index + 1]) / 32768
    state.update(last_rx_s=received_s, last_packet_type=f"0x{kind:02X}",
                 last_packet_name=PACKET_NAMES[kind], last_packet_hex=packet.hex())


def columns(label):
    p = label.lower()
    result = [f"{p}_last_rx_s", f"{p}_last_angle_rx_s", f"{p}_last_packet_type",
              f"{p}_last_packet_name", f"{p}_last_packet_hex"]
    result += [f"{p}_accel_{a}_g" for a in AXES]
    result += [f"{p}_gyro_{a}_dps" for a in AXES]
    result += [f"{p}_mag_{a}_raw" for a in AXES]
    result += [f"{p}_angle_{a}_deg" for a in AXES]
    result += [f"{p}_quat_{a}" for a in ("w", "x", "y", "z")]
    return result + [f"{p}_temperature_c"]


def values(state):
    result = [state[k] for k in ("last_rx_s", "last_angle_rx_s", "last_packet_type",
                                 "last_packet_name", "last_packet_hex")]
    result += [state[f"accel_{a}_g"] for a in AXES]
    result += [state[f"gyro_{a}_dps"] for a in AXES]
    result += [state[f"mag_{a}"] for a in AXES]
    result += [state[f"angle_{a}_deg"] for a in AXES]
    result += [state[f"quat_{a}"] for a in ("w", "x", "y", "z")]
    return result + [state["temperature_c"]]


class VerificationLogger:
    def __init__(self, args):
        self.args = args
        self.clients = {}
        self.parsers = {label: WitFrameParser() for label in IMUS}
        self.states = {label: new_state() for label in IMUS}
        self.start_time = None
        self.output_file = self.writer = None
        self.rows = 0

    def log(self, text):
        print(text, flush=True)

    async def connect_all(self):
        while len(self.clients) < len(IMUS):
            missing = [label for label in IMUS if label not in self.clients]
            self.log("Scanning for: " + ", ".join(missing))
            devices = await BleakScanner.discover(timeout=self.args.scan_seconds)
            found = {device.address.upper(): device for device in devices}
            for label in missing:
                device = found.get(IMUS[label])
                if not device:
                    continue
                client = None
                try:
                    self.log(f"Connecting {label} ({IMUS[label]})...")
                    client = BleakClient(device)
                    await client.connect()
                    if not client.is_connected:
                        raise RuntimeError("connection was not established")
                    self.clients[label] = client
                    self.log(f"{label} connected.")
                except Exception as exc:
                    self.log(f"{label} connection failed: {exc}")
                    if client:
                        await client.disconnect()
            if len(self.clients) < len(IMUS):
                self.log("Both devices were not found; retrying shortly.")
                await asyncio.sleep(self.args.retry_seconds)

    def callback(self, label):
        def receive(_sender, data):
            if self.start_time is None:
                return
            received_s = time.perf_counter() - self.start_time
            for packet in self.parsers[label].feed(data):
                update_state(self.states[label], packet, received_s)
        return receive

    def open_output(self):
        output = Path(self.args.output or f"imu_verification_{datetime.now():%Y%m%d_%H%M%S}.csv")
        self.output_file = output.open("w", newline="")
        self.writer = csv.writer(self.output_file)
        header = ["host_t_s", "wall_time_iso8601", "angle_skew_s", "pair_in_sync"]
        for label in IMUS:
            header += columns(label)
        self.writer.writerow(header)
        self.output_file.flush()
        return output

    def write_row(self):
        angle_times = [self.states[label]["last_angle_rx_s"] for label in IMUS]
        skew = None if None in angle_times else abs(angle_times[0] - angle_times[1])
        row = [time.perf_counter() - self.start_time,
               datetime.now().astimezone().isoformat(timespec="milliseconds"),
               skew, skew is not None and skew <= self.args.max_skew]
        for label in IMUS:
            row += values(self.states[label])
        self.writer.writerow(row)
        self.output_file.flush()
        self.rows += 1

    async def record(self):
        period, next_tick = 1 / self.args.rate, time.perf_counter()
        while True:
            next_tick += period
            self.write_row()
            await asyncio.sleep(max(0, next_tick - time.perf_counter()))

    async def run(self):
        try:
            await self.connect_all()
            self.log("Both IMUs are connected. Press Enter to begin recording.")
            await asyncio.to_thread(input)
            output = self.open_output()
            await asyncio.gather(*(client.start_notify(NOTIFY_CHAR, self.callback(label))
                                   for label, client in self.clients.items()))
            self.start_time = time.perf_counter()
            self.log(f"Recording at {self.args.rate:g} Hz to {output}. Press Ctrl+C to stop.")
            await self.record()
        finally:
            for client in self.clients.values():
                try:
                    await client.stop_notify(NOTIFY_CHAR)
                except Exception:
                    pass
                try:
                    await client.disconnect()
                except Exception:
                    pass
            if self.output_file:
                self.output_file.close()
                self.log(f"Saved {self.rows} rows.")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="CSV path (default: timestamped imu_verification file)")
    parser.add_argument("--rate", type=float, default=20.0,
                        help="host CSV sample rate in Hz (default: 20)")
    parser.add_argument("--max-skew", type=float, default=0.075,
                        help="largest orientation-packet gap counted as synchronized (default: 0.075 s)")
    parser.add_argument("--scan-seconds", type=float, default=5.0)
    parser.add_argument("--retry-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if not 1 <= args.rate <= 100:
        parser.error("--rate must be between 1 and 100 Hz")
    if args.max_skew < 0:
        parser.error("--max-skew must be non-negative")
    return args


if __name__ == "__main__":
    try:
        asyncio.run(VerificationLogger(parse_args()).run())
    except KeyboardInterrupt:
        pass
