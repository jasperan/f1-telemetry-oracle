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

_CURRENT_PACKET = dict()
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
    '''
    f = open('./example_packets/json/{}.json'.format(collection_name))
    dict_object = json.load(f)
    f.close()

    dict_object['m_car_telemetry_data'][0]['m_speed'] = random.randint(0, 100)
    '''

    '''
    def callback(ch, method, properties, body):
        print(" [x] Received %r" % body.decode())
        swapped_body = body.decode().replace("\'", "\"")
        _CURRENT_PACKET = json.loads(swapped_body)
    '''

    print('{} | WS {} OK'.format(datetime.datetime.now(), collection_name))
    channel.basic_qos(prefetch_count=1)
    # consume queue
    #channel.basic_consume(queue='PacketCarTelemetryData', on_message_callback=callback, auto_ack=True)
    method, properties, body = channel.basic_get(queue='PacketCarTelemetryData', auto_ack=True)
    print(" [x] Received %r" % body.decode())
    swapped_body = body.decode().replace("\'", "\"")
    _CURRENT_PACKET = json.loads(swapped_body)
    #channel.start_consuming()
    print(_CURRENT_PACKET)
    return _CURRENT_PACKET



async def handler(websocket):
    while True:
        message = await websocket.recv()
        print(message)

        if message == 'getPacketCarTelemetryData':
            result = save_packet('PacketCarTelemetryData')

        await websocket.send(json.dumps(result))




async def main():



    #async with websockets.serve(handler, "", 8001, ssl=ssl_context):
    async with websockets.serve(handler, "", 8001):
        await asyncio.Future()  # run forever



if __name__ == "__main__":
    asyncio.run(main())
