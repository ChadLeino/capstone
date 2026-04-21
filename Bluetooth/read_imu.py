import asyncio
import csv
import time
from bleak import BleakClient, BleakScanner

TARGET_ADDRESSES = [
    "D4:3F:17:2F:EC:51",
    "D6:DC:FD:A3:9D:59",
]

NOTIFY_CHAR = "0000ffe4-0000-1000-8000-00805f9a34fb"
CSV_FILE = "imu_angles.csv"

start_time = None
csv_file = None
csv_writer = None


def to_int16(lo, hi):
    value = (hi << 8) | lo
    if value >= 32768:
        value -= 65536
    return value


class IMUStreamParser:
    def __init__(self, label):
        self.label = label
        self.buffer = bytearray()

    def handle_notify(self, sender, data):
        global start_time, csv_writer, csv_file

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

            yaw, roll, pitch, packet_name = result
            t_s = time.time() - start_time

            csv_writer.writerow([t_s, self.label, yaw, roll, pitch, packet_name])
            csv_file.flush()

            print(
                f"{self.label:>4} | "
                f"{t_s:8.3f} s | "
                f"yaw: {yaw:8.3f} | "
                f"roll: {roll:8.3f} | "
                f"pitch: {pitch:8.3f} | "
                f"{packet_name}"
            )

    def parse_packet(self, packet):
        packet_type = packet[1]

        if packet_type == 0x53:
            # Standard WIT angle frame: roll, pitch, yaw
            roll_raw = to_int16(packet[2], packet[3])
            pitch_raw = to_int16(packet[4], packet[5])
            yaw_raw = to_int16(packet[6], packet[7])

            roll = roll_raw / 32768.0 * 180.0
            pitch = pitch_raw / 32768.0 * 180.0
            yaw = yaw_raw / 32768.0 * 180.0

            return yaw, roll, pitch, "0x53"

        if packet_type == 0x61:
            # Older working stream type from your previous script.
            # We decode the first 3 int16 values as roll, pitch, yaw.
            # If yaw/roll/pitch look swapped physically, tell me and I’ll remap them.
            v1_raw = to_int16(packet[2], packet[3])
            v2_raw = to_int16(packet[4], packet[5])
            v3_raw = to_int16(packet[6], packet[7])

            roll = v1_raw / 32768.0 * 180.0
            pitch = v2_raw / 32768.0 * 180.0
            yaw = v3_raw / 32768.0 * 180.0

            return yaw, roll, pitch, "0x61"

        return None


async def find_devices():
    print("Scanning for IMUs...")
    devices = await BleakScanner.discover(timeout=8.0)

    found = {}
    target_set = {addr.upper() for addr in TARGET_ADDRESSES}

    for device in devices:
        print(f"Found: {device.name} | {device.address}")
        addr = device.address.upper()
        if addr in target_set:
            found[addr] = device

    return found


async def connect_imu(device, label):
    client = BleakClient(device)
    parser = IMUStreamParser(label)

    print(f"Connecting to {label} at {device.address}...")
    await client.connect()
    print(f"{label} connected: {client.is_connected}")

    await client.start_notify(NOTIFY_CHAR, parser.handle_notify)
    return client


async def main():
    global start_time, csv_file, csv_writer

    found_devices = await find_devices()

    if not found_devices:
        print("No target IMUs found.")
        return

    csv_file = open(CSV_FILE, "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["t_s", "imu", "yaw_deg", "roll_deg", "pitch_deg", "packet_type"])
    csv_file.flush()

    print(f"Created {CSV_FILE} and wrote header.")

    clients = []

    try:
        start_time = time.time()

        for i, addr in enumerate(TARGET_ADDRESSES, start=1):
            addr_upper = addr.upper()
            label = f"IMU{i}"

            if addr_upper not in found_devices:
                print(f"{label} not found: {addr}")
                continue

            try:
                client = await connect_imu(found_devices[addr_upper], label)
                clients.append(client)
            except Exception as e:
                print(f"Failed to connect to {label}: {e}")

        if not clients:
            print("No IMUs connected.")
            return

        print("Recording... Stop with Ctrl+C in the terminal.")

        while True:
            await asyncio.sleep(1)

    finally:
        for client in clients:
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