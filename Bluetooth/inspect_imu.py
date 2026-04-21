import asyncio
from bleak import BleakClient

ADDRESS = "D6:DC:FD:A3:9D:59"

async def main():
    print(f"Connecting to {ADDRESS}...")
    async with BleakClient(ADDRESS) as client:
        print("Connected:", client.is_connected)

        for service in client.services:
            print(f"\n[Service] {service.uuid} | {service.description}")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"  [Characteristic] {char.uuid}")
                print(f"    Properties: {props}")

asyncio.run(main())