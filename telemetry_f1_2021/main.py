import copy
import json
import pickle
from pathlib import Path

from telemetry_f1_2021.packets import HEADER_FIELD_TO_PACKET_TYPE
from telemetry_f1_2021.packets import PacketSessionData
from telemetry_f1_2021.listener import TelemetryListener

from oracledb import OracleJSONDatabaseConnection

# using time module
import time


def _get_listener():
    try:
        print('Starting listener on localhost:20777')
        return TelemetryListener()
    except OSError as exception:
        print(f'Unable to setup connection: {exception.args[1]}')
        print('Failed to open connector, stopping.')
        exit(127)


# get weather data and insert it into database.
def main():
    # Get connection to db.
    dbhandler = OracleJSONDatabaseConnection()

    listener = _get_listener()
    #print(type(PacketSessionData))
    #print(PacketSessionData._fields_)

    try:
        while True:
            packet = listener.get()
            # ts stores the time in seconds
            ts = time.time()
            
            if isinstance(packet, PacketSessionData):
                #print(packet)
                # packet.m_weather_forecast_samples
                save_packet(dbhandler, packet, ts)

    except KeyboardInterrupt:
        print('Stop the car, stop the car Checo.')
        print('Stop the car, stop at pit exit.')
        print('Just pull over to the side.')
        dbhandler.close_pool()

    dbhandler.close_pool()

    



def save_oracle_db(dbhandler, dict_object):
    res = dbhandler.insert('f1_2021_weather', dict_object)
    if res == 0:
        print('INSERT {} ERR'.format(dict_object['timestamp']))
    else:
        print('INSERT {} OK'.format(dict_object['timestamp']))



def save_packet(dbhandler, packet, timestamp):
    assert isinstance(packet, PacketSessionData)
    dict_object = packet.to_dict()
    dict_object['timestamp'] = timestamp
    #print('Store {}'.format(json.dumps(dict_object, indent=2)))

    # Load into Oracle DB
    save_oracle_db(dbhandler, dict_object)




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

        with open(f'{root_dir}/example_packets/json/{packet_name}.json', 'w') as fh:
            json.dump(packet.to_dict(), fh, indent=2)

    print('Done!')


if __name__ == '__main__':
    main()
