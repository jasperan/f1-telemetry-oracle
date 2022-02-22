import asyncio
from websockets import connect

async def hello(uri):
    async with connect(uri) as websocket:
        await websocket.send("getPacketCarTelemetryData")
        await websocket.recv()

asyncio.run(hello("ws://130.61.139.189:8001"))