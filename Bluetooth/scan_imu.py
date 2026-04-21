import asyncio
from bleak import BleakScanner

async def main():
    devices = await BleakScanner.discover(timeout=8.0)
    for d in devices:
        print(f"Name: {d.name} | Address: {d.address}")

asyncio.run(main())