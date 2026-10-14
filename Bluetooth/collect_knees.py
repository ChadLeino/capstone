#!/usr/bin/env python3
"""Collect synchronized data from four WIT IMUs placed around two knees.

Pairing: IMU1 (above) / IMU2 (below) is knee 1; IMU3 (above) / IMU4
(below) is knee 2.  A row is written only when one fresh sample from every
IMU is available within the configured synchronization window.
"""

import argparse
import asyncio
import csv
import math
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from bleak import BleakClient, BleakScanner


# IMU1 and IMU2 were physically verified to be the reverse of the initial map.
IMUS = {
    "IMU1": "D4:3F:17:2F:EC:51",  # above knee 1
    "IMU2": "D6:DC:FD:A3:9D:59",  # below knee 1
    "IMU3": "D0:01:6C:93:1C:F5",  # above knee 2
    "IMU4": "F7:D7:39:21:2A:72",  # below knee 2
}
NOTIFY_CHAR = "0000ffe4-0000-1000-8000-00805f9a34fb"
AXES = ("x", "y", "z")


def to_int16(lo, hi):
    value = (hi << 8) | lo
    return value - 65536 if value >= 32768 else value


def wrap_degrees(angle):
    """Return the signed shortest angular difference in [-180, 180)."""
    return (angle + 180.0) % 360.0 - 180.0


def rotation_matrix(roll_deg, pitch_deg, yaw_deg):
    """WIT roll/pitch/yaw orientation as a sensor-to-world rotation matrix."""
    roll, pitch, yaw = (math.radians(angle)
                        for angle in (roll_deg, pitch_deg, yaw_deg))
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    # Rz(yaw) * Ry(pitch) * Rx(roll), the usual roll/pitch/yaw convention.
    return (
        (cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
        (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
        (-sp, cp * sr, cp * cr),
    )


def transpose(matrix):
    return tuple(zip(*matrix))


def matrix_multiply(left, right):
    return tuple(tuple(sum(left[row][index] * right[index][column]
                           for index in range(3)) for column in range(3))
                 for row in range(3))


def rotation_angle_degrees(rotation):
    """Return the unsigned 3D angle represented by a rotation matrix."""
    cosine = (rotation[0][0] + rotation[1][1] + rotation[2][2] - 1.0) / 2.0
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


class FrameParser:
    """Reassembles WIT angle frames split across BLE notifications."""

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

            packet_type = self.buffer[1]
            packet_length = {0x53: 11, 0x61: 20}.get(packet_type)
            if packet_length is None:
                del self.buffer[0]
                continue
            if len(self.buffer) < packet_length:
                break

            packet = bytes(self.buffer[:packet_length])
            del self.buffer[:packet_length]
            angles = self._parse(packet)
            if angles is not None:
                frames.append(angles)
        return frames

    @staticmethod
    def _parse(packet):
        # 0x53 is the serial angle frame: roll, pitch, yaw. BLE 0x61 is a
        # 20-byte combined frame: accel XYZ, gyro XYZ, then angle XYZ.
        if packet[1] not in (0x53, 0x61):
            return None
        angle_offsets = (14, 16, 18) if packet[1] == 0x61 else (2, 4, 6)
        return tuple(to_int16(packet[index], packet[index + 1]) / 32768.0 * 180.0
                     for index in angle_offsets)


class Collector:
    def __init__(self, args):
        self.args = args
        self.clients = {}
        self.parsers = {label: FrameParser() for label in IMUS}
        self.samples = {label: deque(maxlen=20) for label in IMUS}
        self.start_time = None
        self.writer = None
        self.output_file = None
        self.rows = 0
        self.zero = None
        self.neutral_relative = None

    def log(self, message):
        print(message, file=sys.stderr if self.args.stream_stdout else sys.stdout,
              flush=True)

    async def connect_all(self):
        """Keep scanning and retrying until all four expected devices connect."""
        while len(self.clients) < len(IMUS):
            missing = [label for label in IMUS if label not in self.clients]
            self.log("Scanning for: " + ", ".join(missing))
            devices = await BleakScanner.discover(timeout=self.args.scan_seconds)
            by_address = {device.address.upper(): device for device in devices}

            for label in missing:
                device = by_address.get(IMUS[label])
                if device is None:
                    continue
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
                    try:
                        await client.disconnect()
                    except Exception:
                        pass

            if len(self.clients) < len(IMUS):
                missing = [label for label in IMUS if label not in self.clients]
                self.log("Still waiting for: " + ", ".join(missing))
                await asyncio.sleep(self.args.retry_seconds)

    def notification_callback(self, label):
        def callback(_sender, data):
            if self.start_time is None:
                return
            timestamp = time.perf_counter() - self.start_time
            for angles in self.parsers[label].feed(data):
                self.samples[label].append((timestamp, *angles))
            self.write_available_rows()
        return callback

    def write_available_rows(self):
        """Match the oldest samples that fall inside the allowed time skew."""
        while all(self.samples[label] for label in IMUS):
            heads = {label: self.samples[label][0] for label in IMUS}
            timestamps = {label: sample[0] for label, sample in heads.items()}
            earliest_label = min(timestamps, key=timestamps.get)
            latest_time = max(timestamps.values())
            earliest_time = timestamps[earliest_label]

            if latest_time - earliest_time > self.args.max_skew:
                self.samples[earliest_label].popleft()
                continue

            matched = {label: self.samples[label].popleft() for label in IMUS}
            self.write_row(matched)

    def write_row(self, matched):
        row_time = sum(sample[0] for sample in matched.values()) / len(IMUS)
        axis_index = AXES.index(self.args.axis) + 1
        knee_1_raw = wrap_degrees(matched["IMU2"][axis_index] - matched["IMU1"][axis_index])
        knee_2_raw = wrap_degrees(matched["IMU4"][axis_index] - matched["IMU3"][axis_index])
        if self.zero is None and self.args.zero_at_start:
            self.zero = (knee_1_raw, knee_2_raw)
        offset_1, offset_2 = self.zero or (0.0, 0.0)
        knee_1 = wrap_degrees(knee_1_raw - offset_1)
        knee_2 = wrap_degrees(knee_2_raw - offset_2)

        # Relative orientation of each calf with respect to its thigh.
        relative_1 = matrix_multiply(
            transpose(rotation_matrix(*matched["IMU1"][1:])),
            rotation_matrix(*matched["IMU2"][1:]),
        )
        relative_2 = matrix_multiply(
            transpose(rotation_matrix(*matched["IMU3"][1:])),
            rotation_matrix(*matched["IMU4"][1:]),
        )
        if self.neutral_relative is None:
            # Press Enter with both legs straight. This captures small mounting
            # offsets, so a straight leg is reported as 180 degrees.
            self.neutral_relative = (relative_1, relative_2)
            self.log("Straight-leg calibration captured from the first synchronized row.")
        movement_1 = matrix_multiply(transpose(self.neutral_relative[0]), relative_1)
        movement_2 = matrix_multiply(transpose(self.neutral_relative[1]), relative_2)
        knee_1_angle = 180.0 - rotation_angle_degrees(movement_1)
        knee_2_angle = 180.0 - rotation_angle_degrees(movement_2)

        row = [row_time]
        for label in IMUS:
            row.extend(matched[label])
        row.extend([knee_1_raw, knee_2_raw, knee_1, knee_2,
                    knee_1_angle, knee_2_angle])
        self.writer.writerow(row)
        self.output_file.flush()
        if self.args.stream_stdout:
            self.stdout_writer.writerow(row)
            sys.stdout.flush()
        self.rows += 1

    def open_output(self):
        output = Path(self.args.output or
                      f"knee_capture_{datetime.now():%Y%m%d_%H%M%S}.csv")
        self.output_file = output.open("w", newline="")
        self.writer = csv.writer(self.output_file)
        axis = self.args.axis
        header = ["t_s"]
        for label in IMUS:
            prefix = label.lower()
            header += [f"{prefix}_t_s", f"{prefix}_tilt_x_deg",
                       f"{prefix}_tilt_y_deg", f"{prefix}_tilt_z_deg"]
        header += [f"knee_1_{axis}_raw_deg", f"knee_2_{axis}_raw_deg",
                   f"knee_1_{axis}_deg", f"knee_2_{axis}_deg",
                   "knee_1_angle_deg", "knee_2_angle_deg"]
        self.writer.writerow(header)
        self.output_file.flush()
        if self.args.stream_stdout:
            self.stdout_writer = csv.writer(sys.stdout)
            self.stdout_writer.writerow(header)
            sys.stdout.flush()
        return output

    async def run(self):
        try:
            await self.connect_all()
            self.log("All four IMUs are connected. Press Enter to begin recording.")
            await asyncio.to_thread(input)
            output = self.open_output()
            self.start_time = time.perf_counter()
            for label, client in self.clients.items():
                await client.start_notify(NOTIFY_CHAR, self.notification_callback(label))
            self.log(f"Recording to {output}. Press Ctrl+C to stop.")
            while True:
                await asyncio.sleep(1)
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
                self.log(f"Saved {self.rows} synchronized rows.")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="CSV path (default: timestamped knee_capture file)")
    parser.add_argument("--axis", choices=AXES, default="y",
                        help="sensor axis used for the relative knee angle (default: y)")
    parser.add_argument("--zero-at-start", action="store_true",
                        help="report knee angles relative to the first synchronized pose")
    parser.add_argument("--stream-stdout", action="store_true",
                        help="also write live CSV (with header) to stdout for a downstream program")
    parser.add_argument("--max-skew", type=float, default=0.075,
                        help="largest allowed timestamp gap within one row, in seconds (default: 0.075)")
    parser.add_argument("--scan-seconds", type=float, default=5.0)
    parser.add_argument("--retry-seconds", type=float, default=2.0)
    return parser.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(Collector(parse_args()).run())
    except KeyboardInterrupt:
        pass
