#!/usr/bin/env python3
"""Live six-panel Euler-angle viewer for IMU1 and IMU2.

Connects to the same two WIT IMUs as verify_imus.py. Press Enter to start the
live graph, then close the plot window or press Ctrl+C to stop.
"""

import argparse
import asyncio
import time
from collections import deque

import matplotlib.pyplot as plt
from bleak import BleakClient, BleakScanner

from verify_imus import AXES, IMUS, NOTIFY_CHAR, WitFrameParser, new_state, update_state


class LivePlotter:
    def __init__(self, args):
        self.args = args
        self.clients = {}
        self.parsers = {label: WitFrameParser() for label in IMUS}
        self.states = {label: new_state() for label in IMUS}
        self.samples = {label: deque() for label in IMUS}
        self.start_time = None

    async def connect_all(self):
        while len(self.clients) < len(IMUS):
            missing = [label for label in IMUS if label not in self.clients]
            print("Scanning for: " + ", ".join(missing), flush=True)
            devices = await BleakScanner.discover(timeout=self.args.scan_seconds)
            found = {device.address.upper(): device for device in devices}
            for label in missing:
                device = found.get(IMUS[label])
                if device is None:
                    continue
                client = None
                try:
                    print(f"Connecting {label} ({IMUS[label]})...", flush=True)
                    client = BleakClient(device)
                    await client.connect()
                    if not client.is_connected:
                        raise RuntimeError("connection was not established")
                    self.clients[label] = client
                    print(f"{label} connected.", flush=True)
                except Exception as exc:
                    print(f"{label} connection failed: {exc}", flush=True)
                    if client:
                        await client.disconnect()
            if len(self.clients) < len(IMUS):
                await asyncio.sleep(self.args.retry_seconds)

    def callback(self, label):
        def receive(_sender, data):
            if self.start_time is None:
                return
            received_s = time.perf_counter() - self.start_time
            for packet in self.parsers[label].feed(data):
                update_state(self.states[label], packet, received_s)
                # Add a point only when an orientation packet arrives; accel,
                # gyro, and magnetometer frames do not create duplicate lines.
                if packet[1] in (0x53, 0x61):
                    angles = tuple(self.states[label][f"angle_{axis}_deg"] for axis in AXES)
                    self.samples[label].append((received_s, *angles))
        return receive

    def make_figure(self):
        figure, graphs = plt.subplots(2, 3, figsize=(14, 7), sharex=True)
        lines = {}
        for row, label in enumerate(IMUS):
            for column, axis in enumerate(AXES):
                graph = graphs[row][column]
                (line,) = graph.plot([], [], color=f"C{column}", linewidth=1.4)
                graph.set(title=f"{label} {axis.upper()} orientation",
                          ylabel="Degrees", ylim=(-185, 185))
                graph.grid(True, alpha=0.3)
                lines[label, axis] = (graph, line)
        for graph in graphs[-1]:
            graph.set_xlabel(f"Seconds (last {self.args.window:g})")
        figure.suptitle("Live IMU orientation — close this window to stop")
        figure.tight_layout()
        return figure, lines

    async def show(self):
        plt.ion()
        figure, lines = self.make_figure()
        plt.show(block=False)
        while plt.fignum_exists(figure.number):
            now = time.perf_counter() - self.start_time
            cutoff = now - self.args.window
            for label in IMUS:
                data = self.samples[label]
                while data and data[0][0] < cutoff:
                    data.popleft()
                if not data:
                    continue
                times = [sample[0] for sample in data]
                for index, axis in enumerate(AXES, start=1):
                    graph, line = lines[label, axis]
                    line.set_data(times, [sample[index] for sample in data])
                    graph.set_xlim(max(0, cutoff), max(self.args.window, now))
            figure.canvas.draw_idle()
            figure.canvas.flush_events()
            await asyncio.sleep(0.05)
        plt.close(figure)

    async def run(self):
        try:
            await self.connect_all()
            print("Both IMUs are connected. Press Enter to open the live plot.", flush=True)
            await asyncio.to_thread(input)
            await asyncio.gather(*(client.start_notify(NOTIFY_CHAR, self.callback(label))
                                   for label, client in self.clients.items()))
            self.start_time = time.perf_counter()
            print("Live plot running. Close its window or press Ctrl+C to stop.", flush=True)
            await self.show()
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


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", type=float, default=15.0,
                        help="visible history in seconds (default: 15)")
    parser.add_argument("--scan-seconds", type=float, default=5.0)
    parser.add_argument("--retry-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if args.window <= 0:
        parser.error("--window must be positive")
    return args


if __name__ == "__main__":
    try:
        asyncio.run(LivePlotter(parse_args()).run())
    except KeyboardInterrupt:
        pass
