import asyncio
import websockets
import datetime
import copy
import json
import pickle
from pathlib import Path
import random
from telemetry_f1_2021.packets import HEADER_FIELD_TO_PACKET_TYPE
from telemetry_f1_2021.packets import PacketSessionData, PacketMotionData, PacketLapData, PacketEventData, PacketParticipantsData, PacketCarDamageData
from telemetry_f1_2021.packets import PacketCarSetupData, PacketCarTelemetryData, PacketCarStatusData, PacketFinalClassificationData, PacketLobbyInfoData, PacketSessionHistoryData
from telemetry_f1_2021.listener import TelemetryListener
import time
# using time module
import argparse
#import ssl
import pika


#ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

# Generate with Lets Encrypt, copied to this location, chown to current user and 400 permissions
#ssl_cert = "/home/$USER/websocket/fullchain.pem"
#ssl_key = "/home/$USER/websocket/privkey.pem"

#ssl_context.load_cert_chain(ssl_cert, keyfile=ssl_key)

_CURRENT_PACKET = str()
# Initialize message queue from where we're getting the data.
connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
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
        print('Unable to setup connection: {}'.format(exception.args[1]))
        print('Failed to open connector, stopping.')
        exit(127)



# instead of having a random packet and randomizing, get from rabbitmq queue.
def save_packet(collection_name):
    print('{} | WS {} OK'.format(datetime.datetime.now(), collection_name))
    channel.basic_qos(prefetch_count=1)
    # consume queue
    method, properties, body = channel.basic_get(queue='PacketCarTelemetryData', auto_ack=True)
    del method, properties
    #swapped_body = body.decode().replace("\'", "\"")
    try:
        _CURRENT_PACKET = body.decode()
    except AttributeError:
        _CURRENT_PACKET = '{}'
    #channel.start_consuming()
    print(_CURRENT_PACKET)
    return _CURRENT_PACKET



async def handler(websocket):
    while True:
        message = await websocket.recv()
        print(message)

        if message == 'getPacketCarTelemetryData':
            result = save_packet('PacketCarTelemetryData')

        await websocket.send(result)




async def main():



    #async with websockets.serve(handler, "", 8001, ssl=ssl_context):
    async with websockets.serve(handler, "", 8001):
        await asyncio.Future()  # run forever



if __name__ == "__main__":
    asyncio.run(main())
