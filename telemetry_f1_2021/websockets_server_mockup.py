# using time module
import argparse
import asyncio
import datetime
import json

import pika
import websockets

from telemetry_f1_2021.listener import TelemetryListener

global _CURRENT_PACKET
# Initialize message queue from where we're getting the data.
connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost', heartbeat=600, blocked_connection_timeout=300))
channel = connection.channel()
# declare queue, in case the receiver is initialized before the producer.
channel.queue_declare(queue='PacketCarTelemetryData')

cli_parser = argparse.ArgumentParser(
    description="Script that records telemetry F1 2021 weather data into a RabbitMQ queue"
)

cli_parser.add_argument('-g', '--gamehost', type=str, help='Gamehost identifier (something unique)', required=True)
args = cli_parser.parse_args()



def _get_listener():
    try:
        print('Starting listener on localhost:20777')
        return TelemetryListener()
    except OSError as exception:
        print(f'Unable to setup connection: {exception.args[1]}')
        print('Failed to open connector, stopping.')
        exit(127)



# instead of having a random packet and randomizing, get from rabbitmq queue.
def save_packet(collection_name):
    print(f'{datetime.datetime.now()} | WS MOCKUP {collection_name} OK')
    channel.basic_qos(prefetch_count=1)
    f = open(f'./example_packets/json/{collection_name}.json')
    body = json.load(f)
    f.close()
    try:
        _CURRENT_PACKET = body
        print(_CURRENT_PACKET)
    except AttributeError:
        #print('AttributeError: {}'.format(e))
        _CURRENT_PACKET = {}
    #channel.start_consuming()
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
