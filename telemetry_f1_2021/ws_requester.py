import asyncio
from websockets import connect


# Client simulator for web socket connection to a server located in the below mentioned IP address and port.
# This "client" will make constant requests (of 2 types, interchangeably), to test during development.

async def hello(uri):
    async with connect(uri) as websocket:
        while True:
            await websocket.send("getPacketCarTelemetryData")
            message = await websocket.recv()
            print(message)

            await websocket.send("getPacketSessionData")
            message = await websocket.recv()
            print(message)


asyncio.run(hello("ws://130.61.139.189:8001"))
