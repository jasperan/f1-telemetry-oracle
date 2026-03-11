# using time module
import argparse
import asyncio
import datetime
import json

import pika
import websockets

global _CURRENT_PACKET
# Initialize message queue from where we're getting the data.
connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost', heartbeat=600, blocked_connection_timeout=300))
channel = connection.channel()
# declare our queues
channel.queue_declare(queue='PacketCarTelemetryData')
channel.queue_declare(queue='PacketSessionData')



cli_parser = argparse.ArgumentParser()
cli_parser.add_argument('-g', '--gamehost', type=str, help='Gamehost identifier (something unique)', required=True)
args = cli_parser.parse_args()



# instead of having a random packet and randomizing, get from rabbitmq queue.
def save_packet(collection_name):
    print(f'{datetime.datetime.now()} | WS {collection_name} OK')
    channel.basic_qos(prefetch_count=1)
    # consume queue
    method, properties, body = channel.basic_get(queue=collection_name, auto_ack=True)
    del method, properties
    try:
        _CURRENT_PACKET = body.decode()
        print(_CURRENT_PACKET)
    except AttributeError:
        _CURRENT_PACKET = {}
    print(_CURRENT_PACKET)
    return json.dumps(_CURRENT_PACKET)



async def handler(websocket):
    while True:
        message = await websocket.recv()
        print(message)

        if message == 'getPacketCarTelemetryData':
            result = save_packet('PacketCarTelemetryData')
        elif message == 'getPacketSessionData':
            result = save_packet('PacketSessionData')

        await websocket.send(result)




async def main():
    #async with websockets.serve(handler, "", 8001, ssl=ssl_context):
    async with websockets.serve(handler, "", 8001):
        await asyncio.Future()  # run forever



if __name__ == "__main__":
    asyncio.run(main())
