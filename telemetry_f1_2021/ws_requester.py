import asyncio
from websockets import connect
import time

# Client simulator for web socket connection to a server located in the below mentioned IP address and port. 

async def hello(uri):
    async with connect(uri) as websocket:
        while True:
            await websocket.send("getPacketCarTelemetryData")
            message = await websocket.recv()
            print(message)
            time.sleep(.05)

asyncio.run(hello("ws://130.61.139.189:8001"))
