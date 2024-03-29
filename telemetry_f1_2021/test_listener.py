import datetime
import copy
import json
from pathlib import Path
from re import A

from telemetry_f1_2021.packets import HEADER_FIELD_TO_PACKET_TYPE
from telemetry_f1_2021.packets import PacketSessionData, PacketMotionData, PacketLapData, PacketEventData, PacketParticipantsData, PacketCarDamageData
from telemetry_f1_2021.packets import PacketCarSetupData, PacketCarTelemetryData, PacketCarStatusData, PacketFinalClassificationData, PacketLobbyInfoData, PacketSessionHistoryData
from telemetry_f1_2021.listener import TelemetryListener
# using time module
import time
import argparse



cli_parser = argparse.ArgumentParser(
    description="Script that records telemetry F1 2021 weather data into an Autonomous JSON Database"
)

cli_parser.add_argument('-g', '--gamehost', type=str, help='Gamehost identifier (something unique)', required=True)
args = cli_parser.parse_args()


global listener

def _get_listener():
    try:
        print('Starting listener on localhost:20777')
        return TelemetryListener()
    except OSError as exception:
        print('Unable to setup connection: {}'.format(exception.args[1]))
        print('Failed to open connector, stopping.')
        exit(127)

listener = _get_listener()



# get weather data and insert it into database.
def main():

    try:
        read_data_inf()
    except KeyboardInterrupt:
        print('Stop the car, stop the car Checo.')
        print('Stop the car, stop at pit exit.')
        print('Just pull over to the side.')
    except Exception as e:
        print(e)




def read_data_inf():
    try:
        while True:
            packet = listener.get()
            # ts stores the time in seconds
            ts = time.time()
            #print('{}'.format(PacketSessionData.__class__))
            if isinstance(packet, PacketSessionData):
                save_packet_weather(packet, ts)
                save_packet('PacketSessionData', packet)
            elif isinstance(packet, PacketMotionData):
                save_packet('PacketMotionData', packet)
            elif isinstance(packet, PacketLapData):
                save_packet('PacketLapData', packet)
            elif isinstance(packet, PacketEventData):
                save_packet('PacketEventData', packet)
            elif isinstance(packet, PacketParticipantsData):
                save_packet('PacketParticipantsData', packet)
            elif isinstance(packet, PacketCarSetupData):
                save_packet('PacketCarSetupData', packet)
            elif isinstance(packet, PacketCarTelemetryData):
                save_packet('PacketCarTelemetryData', packet)
            elif isinstance(packet, PacketCarStatusData):
                save_packet('PacketCarStatusData', packet)
            elif isinstance(packet, PacketFinalClassificationData):
                save_packet('PacketFinalClassificationData', packet)
            elif isinstance(packet, PacketLobbyInfoData):
                save_packet('PacketLobbyInfoData', packet)
            elif isinstance(packet, PacketCarDamageData):
                save_packet('PacketCarDamageData', packet)
            elif isinstance(packet, PacketSessionHistoryData):
                save_packet('PacketSessionHistoryData', packet)
    except Exception as e:
        print(e)



def save_weather_object(collection_name, dict_object):
    print('{} | INSERT {} OK'.format(datetime.datetime.now(), dict_object['timestamp']))



def save_oracle_db(collection_name, dict_object):
    print('{} | INSERT INTO {} OK'.format(datetime.datetime.now(), collection_name))



# method used only for weather data for AIHack2022
def save_packet_weather(packet, timestamp):
    dict_object = packet.to_dict()
    dict_object['timestamp'] = int(timestamp) # get integer timestamp for building the time series. We'll ignore 1/2 of all packets since we get 2 per second but it's not relevant for weather.
    dict_object['gamehost'] = args.gamehost

    # Load into Oracle DB
    save_weather_object('f1_2021_weather', dict_object)



def save_packet(collection_name, packet):
    dict_object = packet.to_json()
    # Load into Oracle DB
    save_oracle_db(collection_name, dict_object)



def save_packets():
    samples = {}
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
