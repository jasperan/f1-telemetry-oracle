import datetime
import copy
import json
import pickle
from pathlib import Path

from telemetry_f1_2021.packets import HEADER_FIELD_TO_PACKET_TYPE
from telemetry_f1_2021.packets import PacketSessionData, PacketMotionData, PacketLapData, PacketEventData, PacketParticipantsData, PacketCarDamageData
from telemetry_f1_2021.packets import PacketCarSetupData, PacketCarTelemetryData, PacketCarStatusData, PacketFinalClassificationData, PacketLobbyInfoData, PacketSessionHistoryData
from telemetry_f1_2021.listener import TelemetryListener


# using time module
import pika
import argparse

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


def main():

    connection = pika.BlockingConnection(
    pika.ConnectionParameters(host='localhost'))
    channel = connection.channel()


    list_packet_types = ['PacketMotionData', 'PacketSessionData', 'PacketLapData', 'PacketEventData', 'PacketParticipantsData',
        'PacketCarSetupData', 'PacketCarTelemetryData', 'PacketCarStatusData', 'PacketFinalClassificationData', 'PacketLobbyInfoData',
        'PacketCarDamageData', 'PacketSessionHistoryData']

    # declare all queues
    for x in list_packet_types:
        channel.queue_declare(queue='{}'.format(x))

    listener = _get_listener()

    try:
        while True:
            packet = listener.get()
            if isinstance(packet, PacketSessionData):
                save_packet('PacketSessionData', packet, channel)
            elif isinstance(packet, PacketMotionData):
                save_packet('PacketMotionData', packet, channel)
            elif isinstance(packet, PacketLapData):
                save_packet('PacketLapData', packet, channel)
            elif isinstance(packet, PacketEventData):
                save_packet('PacketEventData', packet, channel)
            elif isinstance(packet, PacketParticipantsData):
                save_packet('PacketParticipantsData', packet, channel)
            elif isinstance(packet, PacketCarSetupData):
                save_packet('PacketCarSetupData', packet, channel)
            elif isinstance(packet, PacketCarTelemetryData):
                save_packet('PacketCarTelemetryData', packet, channel)
            elif isinstance(packet, PacketCarStatusData):
                save_packet('PacketCarStatusData', packet, channel)
            elif isinstance(packet, PacketFinalClassificationData):
                save_packet('PacketFinalClassificationData', packet, channel)
            elif isinstance(packet, PacketLobbyInfoData):
                save_packet('PacketLobbyInfoData', packet, channel)
            elif isinstance(packet, PacketCarDamageData):
                save_packet('PacketCarDamageData', packet, channel)
            elif isinstance(packet, PacketSessionHistoryData):
                save_packet('PacketSessionHistoryData', packet, channel)
            

    except KeyboardInterrupt:
        print('Stop the car, stop the car Checo.')
        print('Stop the car, stop at pit exit.')
        print('Just pull over to the side.')
        connection.close()



def save_packet(collection_name, packet, channel):
    dict_object = packet.to_dict()

    channel.basic_publish(exchange='', routing_key=collection_name, body='{}'.format(dict_object))

    print('{} | MQ {} OK'.format(datetime.datetime.now(), collection_name))



def save_packets():
    samples = {}
    listener = _get_listener()
    packets_to_capture = copy.deepcopy(HEADER_FIELD_TO_PACKET_TYPE)

    # remove FinalClassification and LobbyInfo
    for k in [(2021, 1, 8), (2021, 1, 9)]:
        del HEADER_FIELD_TO_PACKET_TYPE[k]

    while len(samples) != len(list(HEADER_FIELD_TO_PACKET_TYPE)):
        packet = listener.get()

        key = (
            packet.m_header.m_packet_format,
            packet.m_header.m_packet_version,
            packet.m_header.m_packet_id,
        )

        if key in list(packets_to_capture):
            packet_type = HEADER_FIELD_TO_PACKET_TYPE[key].__name__
            samples[packet_type] = packet
            del packets_to_capture[key]

    root_dir = Path(__file__).parent

    for packet_name, packet in samples.items():
        '''
        with open(f'{root_dir}/example_packets/{packet_name}.pickle', 'wb') as fh:
            print(f'Saving packet: {root_dir}/example_packets/{packet_name}.pickle')
            pickle.dump(packet, fh, protocol=pickle.HIGHEST_PROTOCOL)
        '''

        with open('{}/example_packets/json/{}.json'.format(root_dir, packet_name), 'w') as fh:
            json.dump(packet.to_dict(), fh, indent=2)

    print('Done!')



if __name__ == '__main__':
    main()
