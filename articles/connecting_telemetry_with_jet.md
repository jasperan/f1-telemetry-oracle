# Connecting F1 2021 Telemetry with Oracle JET

In this article, we're going to talk about how to use telemetry data from the F1 2021 videogame developed by Codemasters, and display this data in real time using Oracle JET.

# Introduction

Oracle JET (JavaScript Extension Toolkit) is a technology developed by Oracle that acts as an extension of commands for developing both mobile applications and browser-based user interfaces with ease.

TODO

On the other hand, we're able to extract telemetry data using the in-game's telemetry features. This includes packets of the following types:
- Motion data
- Session data
- Lap data
- Event data
- Participants data
- Car setup data
- Car telemetry data
- Car status data
- Final classification data
- Lobby information data
- Car damage data
- Session history data

For example, we're able to obtain this kind of information:

```python
class CarTelemetryData(Packet):
    _fields_ = [
        ("speed", ctypes.c_uint16),  # Speed of car in kilometres per hour
        ("throttle", ctypes.c_float),  # Amount of throttle applied (0.0 to 1.0)
        ("steer", ctypes.c_float),
        # Steering (-1.0 (full lock left) to 1.0 (full lock right))
        ("brake", ctypes.c_float),  # Amount of brake applied (0.0 to 1.0)
        ("clutch", ctypes.c_uint8),  # Amount of clutch applied (0 to 100)
        ("gear", ctypes.c_int8),  # Gear selected (1-8, N=0, R=-1)
        ("engine_rpm", ctypes.c_uint16),  # Engine RPM
        ("drs", ctypes.c_uint8),  # 0 = off, 1 = on
        ("rev_lights_percent", ctypes.c_uint8),  # Rev lights indicator (percentage)
        ("rev_lights_bit_value", ctypes.c_uint16),
        # Rev lights (bit 0 = leftmost LED, bit 14 = rightmost LED)
        ("brakes_temperature", ctypes.c_uint16 * 4),  # Brakes temperature (celsius)
        ("tyre_surface_temperature", ctypes.c_uint8 * 4),
        # tyre surface temperature (celsius)
        ("tyre_inner_temperature", ctypes.c_uint8 * 4),
        # tyre inner temperature (celsius)
        ("engine_temperature", ctypes.c_uint16),  # Engine temperature (celsius)
        ("tyre_pressure", ctypes.c_float * 4),  # tyre pressure (PSI)
        ("surface_type", ctypes.c_uint8 * 4),  # Driving surface, see appendices
    ]
```

All packet types and definitions are accessible in [this file](https://github.com/jasperan/f1-telemetry-oracle/blob/main/telemetry_f1_2021/cleaned_packets.py), together with all variable definitions.

# Architecture

In telemetry, packets typically come in an orderly fashion. However, there are instances where these packets arrive later due to network conditions out of our control. To prevent accidental packet reordering, and to preserve data integrity, we've chosen to implement the communication architecture with message queues.

Message queues have been around for decades and are a way to asynchronously communicate a consumer and a producer. It's been a precursor of inter-process communication inside Operating Systems like UNIX-based OS's, and it's expanded the functionality to many other areas. We believe that message queues fit perfectly into our narrative.

Therefore, messages are stored in a queue until they are processed / consumed by a consumer. Once they are consumed, they are eliminated from the queue. Every message is processed only once, and by only one consumer. In case of having several consumers, each consumer will process different messages.

The chosen message queue provider for our architecture is [RabbitMQ](https://www.rabbitmq.com/), a widely known, completely open-source message broker able to integrate all the above mentioned functionalities. We created a producer ([mq_producer.py](../telemetry_f1_2021/mq_producer.py)) and a consumer of the data / receiver ([mq_receiver.py](../telemetry_f1_2021/mq_receiver.py)). The purpose of the producer is to obtain messages from the F1 2021 game, and add them to our message queue. Complementarily, the receiver will consume the messages from the queue, and "inject" these messages into our Oracle JET-powered dashboard in order to have real-time visualizations of what's actually going on inside the game.

This is a depiction of the architecture:

![architecture](https://github.com/jasperan/f1-telemetry-oracle/blob/main/img/arch.PNG?raw=true)


# Message queues

In this section, we're going to explain the code we've used to implement this message broker architecture.

## Producer

We use [the telemetry_f1_2021 listener Python library](https://github.com/jasperan/f1-telemetry-oracle) for encoding / decoding of the in-game packets, which facilitates us reading these packets in human-readable format.

We bind port 20777 to listen for UDP packets coming from the F1 2021 game. This port can be changed, however the default port in the in-game's settings is configured to 20777. If you're planning to change this, make sure to change the in-game telemetry settings as well.



```python
from telemetry_f1_2021.packets import HEADER_FIELD_TO_PACKET_TYPE
from telemetry_f1_2021.packets import PacketSessionData, PacketMotionData, PacketLapData, PacketEventData, PacketParticipantsData, PacketCarDamageData
from telemetry_f1_2021.packets import PacketCarSetupData, PacketCarTelemetryData, PacketCarStatusData, PacketFinalClassificationData, PacketLobbyInfoData, PacketSessionHistoryData
from telemetry_f1_2021.listener import TelemetryListener

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
```

With the following code, we declare a blocking connection using the Pika Python client. It's worth mentioning that RabbitMQ is able to communicate with multiple protocols. Pika is a Python client recommended by the RabbitMQ team. It uses the AMQP 0-9-1 protocol for messaging. We specify the host to be our local address for testing, since we're running the F1 2021 game in the same computer as the message queue producer / receiver. In case of having the receiver somewhere else, change the host to point to that IPv4 address.
We also declare a queue name. In our case, as it seemed relevant for the architecture, we're using one queue per packet type, to have them distinguished. There is another important reason to make this decision: not all packet types come with the same frequency. Typically, most packet types are sent out by the F1 2021 game with a frequency of 20Hz (20 times per second), however there are some exceptions. If we just included the same queue for all packet types, we'd receive different types of data into the same queue (not ideal) and at a different pace (not cool, and would make visualizations incorrect, not in real time, which is what we're looking for).

```python
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
```

We declare our save_packet function as:

```python
def save_packet(collection_name, packet, channel):
    dict_object = packet.to_dict()

    channel.basic_publish(exchange='', routing_key=collection_name, body='{}'.format(dict_object))

    print('{} | MQ {} OK'.format(datetime.datetime.now(), collection_name)) # simple debug
```

So, every time a packet comes in each one of these queues, it will be inserted into the queue.

## Consumer

# Credits

Note that a great deal of work regarding the F1 2021 telemetry decoding has already been done by [Chris Hannam](https://github.com/chrishannam). Our repository simply has extended the functionality to integrate with RabbitMQ and Oracle databases.
