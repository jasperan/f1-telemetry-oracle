import datetime
import copy
import json
from pathlib import Path

from telemetry_f1_2021.packets import HEADER_FIELD_TO_PACKET_TYPE
from telemetry_f1_2021.packets import PacketSessionData, PacketMotionData, PacketLapData, PacketEventData, PacketParticipantsData, PacketCarDamageData
from telemetry_f1_2021.packets import PacketCarSetupData, PacketCarTelemetryData, PacketCarStatusData, PacketFinalClassificationData, PacketLobbyInfoData, PacketSessionHistoryData
from telemetry_f1_2021.listener import TelemetryListener
from oracle_database import OracleJSONDatabaseThickConnection
# using time module
import time
import argparse
import oracledb
import yaml
import os

def process_yaml():
	with open("../config.yaml") as file:
		return yaml.safe_load(file)



cli_parser = argparse.ArgumentParser(
    description="Script that records telemetry F1 2021 weather data into an Autonomous JSON Database"
)

cli_parser.add_argument('-g', '--gamehost', type=str, help='Gamehost identifier (something unique)', required=True)
cli_parser.add_argument('-a', '--authentication', type=str, help='Authentication mode', choices=['cloudshell', 'configfile'], required=True)
cli_parser.add_argument('-l', '--lib', type=str, help='Instant Client Lib Directory', required=True, default='/usr/lib/oracle/21/client64/lib/network/admin/')

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
    # You must always call init_oracle_client() to use thick mode in any platform
    oracledb.init_oracle_client(lib_dir=args.lib)

    # Get connection to db.
    dbhandler = OracleJSONDatabaseThickConnection(args.authentication)

    try:
        read_data_inf(dbhandler)
    except KeyboardInterrupt:
        print('Stop the car, stop the car Checo.')
        print('Stop the car, stop at pit exit.')
        print('Just pull over to the side.')
        dbhandler.close_pool()
    except Exception as e:
        print(e)

    dbhandler.close_pool()



def read_data_inf(dbhandler):
    while True:
        packet = listener.get()
        # ts stores the time in seconds
        ts = time.time()
        #print('{}'.format(PacketSessionData.__class__))
        if isinstance(packet, PacketSessionData):
            save_packet_weather(dbhandler, packet, ts)
            save_packet('PacketSessionData', dbhandler, packet)
        elif isinstance(packet, PacketMotionData):
            save_packet('PacketMotionData', dbhandler, packet)
        elif isinstance(packet, PacketLapData):
            save_packet('PacketLapData', dbhandler, packet)
        elif isinstance(packet, PacketEventData):
            save_packet('PacketEventData', dbhandler, packet)
        elif isinstance(packet, PacketParticipantsData):
            save_packet('PacketParticipantsData', dbhandler, packet)
        elif isinstance(packet, PacketCarSetupData):
            save_packet('PacketCarSetupData', dbhandler, packet)
        elif isinstance(packet, PacketCarTelemetryData):
            save_packet('PacketCarTelemetryData', dbhandler, packet)
        elif isinstance(packet, PacketCarStatusData):
            save_packet('PacketCarStatusData', dbhandler, packet)
        elif isinstance(packet, PacketFinalClassificationData):
            save_packet('PacketFinalClassificationData', dbhandler, packet)
        elif isinstance(packet, PacketLobbyInfoData):
            save_packet('PacketLobbyInfoData', dbhandler, packet)
        elif isinstance(packet, PacketCarDamageData):
            save_packet('PacketCarDamageData', dbhandler, packet)
        elif isinstance(packet, PacketSessionHistoryData):
            save_packet('PacketSessionHistoryData', dbhandler, packet)



def save_weather_object(collection_name, dbhandler, dict_object):
    res = dbhandler.insert(collection_name, dict_object)
    if res == 0: # error
        print('{} | INSERT WEATHER OBJECT ERR'.format(datetime.datetime.now()))
    else:
        print('{} | INSERT {} OK'.format(datetime.datetime.now(), dict_object['timestamp']))



def save_oracle_db(collection_name, dbhandler, dict_object):
    res = dbhandler.insert(collection_name, dict_object)
    if res == 0: # error
        print('{} | INSERT {} OBJECT ERR'.format(collection_name, datetime.datetime.now()))
    elif res == -1:
        print('{} | INSERT INTO {} STRUCTURAL ERROR'.format(datetime.datetime.now(), collection_name))
    else:
        print('{} | INSERT INTO {} OK'.format(datetime.datetime.now(), collection_name))



# method used only for weather data for AIHack2022
def save_packet_weather(dbhandler, packet, timestamp):
    dict_object = packet.to_dict()
    dict_object['timestamp'] = int(timestamp) # get integer timestamp for building the time series. We'll ignore 1/2 of all packets since we get 2 per second but it's not relevant for weather.
    dict_object['gamehost'] = args.gamehost

    # Load into Oracle DB
    save_weather_object('f1_2021_weather', dbhandler, dict_object)



def save_packet(collection_name, dbhandler, packet):
    dict_object = packet.to_json()
    # Load into Oracle DB
    save_oracle_db(collection_name, dbhandler, dict_object)



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
