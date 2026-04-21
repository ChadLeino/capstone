import asyncio
import csv
import time
from bleak import BleakClient, BleakScanner

IMUS = {
    "IMU3": "D0:01:6C:93:1C:F5",
    "IMU4": "F7:D7:39:21:2A:72",
}

NOTIFY_CHAR = "0000ffe4-0000-1000-8000-00805f9a34fb"
CSV_FILE = "imu_tilt_dual_wide.csv"

start_time = None
csv_file = None
csv_writer = None

latest = {
    "IMU3": None,
    "IMU4": None,
}

pending = {
    "IMU3": None,
    "IMU4": None,
}


def to_int16(lo, hi):
    value = (hi << 8) | lo
    if value >= 32768:
        value -= 65536
    return value


def maybe_write_row():
    global pending, csv_writer, csv_file

    if pending["IMU3"] is None or pending["IMU4"] is None:
        return

    t3, x3, y3, z3 = pending["IMU3"]
    t4, x4, y4, z4 = pending["IMU4"]

    t_row = (t3 + t4) / 2.0

    csv_writer.writerow([
        t_row,
        t3, x3, y3, z3,
        t4, x4, y4, z4,
    ])
    csv_file.flush()

    pending["IMU3"] = None
    pending["IMU4"] = None


class IMUStreamParser:
    def __init__(self, label):
        self.label = label
        self.buffer = bytearray()

    def handle_notify(self, sender, data):
        global start_time, latest, pending

        if start_time is None:
            return

        self.buffer.extend(data)

        while True:
            if len(self.buffer) < 2:
                return

            start = self.buffer.find(0x55)
            if start == -1:
                self.buffer.clear()
                return

            if start > 0:
                del self.buffer[:start]

            if len(self.buffer) < 2:
                return

            packet_type = self.buffer[1]

            if packet_type == 0x53:
                packet_len = 11
            elif packet_type == 0x61:
                packet_len = 14
            else:
                del self.buffer[0]
                continue

            if len(self.buffer) < packet_len:
                return

            packet = bytes(self.buffer[:packet_len])
            del self.buffer[:packet_len]

            result = self.parse_packet(packet)
            if result is None:
                continue

            tilt_x, tilt_y, tilt_z = result
            t_s = time.perf_counter() - start_time

            sample = (t_s, tilt_x, tilt_y, tilt_z)
            latest[self.label] = sample
            pending[self.label] = sample

            maybe_write_row()

    def parse_packet(self, packet):
        packet_type = packet[1]

        if packet_type == 0x53:
            roll_raw = to_int16(packet[2], packet[3])
            pitch_raw = to_int16(packet[4], packet[5])
            yaw_raw = to_int16(packet[6], packet[7])

            roll = roll_raw / 32768.0 * 180.0
            pitch = pitch_raw / 32768.0 * 180.0
            yaw = yaw_raw / 32768.0 * 180.0

            return roll, pitch, yaw

        if packet_type == 0x61:
            x_raw = to_int16(packet[2], packet[3])
            y_raw = to_int16(packet[4], packet[5])
            z_raw = to_int16(packet[6], packet[7])

            tilt_x = x_raw / 32768.0 * 180.0
            tilt_y = y_raw / 32768.0 * 180.0
            tilt_z = z_raw / 32768.0 * 180.0

            return tilt_x, tilt_y, tilt_z

        return None


async def find_devices():
    print("Scanning for IMU3 and IMU4...")
    devices = await BleakScanner.discover(timeout=8.0)

    found = {}

    for device in devices:
        addr = device.address.upper()
        for label, target_addr in IMUS.items():
            if addr == target_addr.upper():
                found[label] = device

    return found


async def connect_client(device, label):
    client = BleakClient(device)
    print(f"Connecting to {label} at {device.address}...")
    await client.connect()
    print(f"{label} connected: {client.is_connected}")
    return client


async def main():
    global start_time, csv_file, csv_writer, latest, pending

    found_devices = await find_devices()

    missing = [label for label in IMUS if label not in found_devices]
    if missing:
        print("Missing IMUs:")
        for label in missing:
            print(f"  {label} ({IMUS[label]})")
        print("Will not start because both IMUs must be present.")
        return

    print("Both IMUs found.")

    clients = {}
    parsers = {}

    latest = {"IMU3": None, "IMU4": None}
    pending = {"IMU3": None, "IMU4": None}

    try:
        for label in IMUS:
            client = await connect_client(found_devices[label], label)
            if not client.is_connected:
                raise RuntimeError(f"{label} failed to connect")
            clients[label] = client
            parsers[label] = IMUStreamParser(label)

        if len(clients) != 2:
            print("Both IMUs are not connected. Exiting.")
            return

        csv_file = open(CSV_FILE, "w", newline="")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow([
            "t_s",
            "imu3_t_s", "imu3_tilt_x_deg", "imu3_tilt_y_deg", "imu3_tilt_z_deg",
            "imu4_t_s", "imu4_tilt_x_deg", "imu4_tilt_y_deg", "imu4_tilt_z_deg",
        ])
        csv_file.flush()

        for label in IMUS:
            await clients[label].start_notify(
                NOTIFY_CHAR,
                parsers[label].handle_notify
            )

        start_time = time.perf_counter()

        print("Both IMUs connected. Recording started. Press Ctrl+C to stop.")

        while True:
            await asyncio.sleep(1)

    finally:
        for label, client in clients.items():
            try:
                await client.stop_notify(NOTIFY_CHAR)
            except Exception:
                pass
            try:
                await client.disconnect()
            except Exception:
                pass

        if csv_file is not None:
            csv_file.flush()
            csv_file.close()
            print(f"Saved data to {CSV_FILE}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")