# Connecting F1 2021 Telemetry with Oracle JET

In this article, we're going to talk about how to use telemetry data from F1 2021, a videogame developed by Codemasters and display this data in real time using [Oracle JET](https://oracle.com/jet).

# Introduction

[Oracle JET](https://oracle.com/jet) (JavaScript Extension Toolkit) is a technology developed by Oracle that acts as an extension of commands for developing both mobile applications and browser-based user interfaces with ease. It's targeted for JavaScript developers working on client-side applications. By packaging several open-source JavaScript libraries together with Oracle JavaScript libraries, it makes building applications very simple and efficient; and we also have the advantage of an easier interaction with other Oracle productrs and services (especially Oracle Cloud Infrastructure services).

From the videogame, we're able to extract telemetry data using in-game's telemetry features. This includes packets of the following types:
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

All packet types and definitions are accessible in [this file](https://github.com/jasperan/f1-telemetry-oracle/blob/main/telemetry_f1_2021/cleaned_packets.py) together with all variable definitions.

# Architecture

In telemetry, packets typically come in an orderly fashion. However, there are instances where these packets arrive later due to network conditions out of our control. To prevent accidental packet reordering, and to preserve data integrity, we've chosen to implement the communication architecture with message queues.

Message queues have been around for decades and are a way to asynchronously communicate between a consumer and a producer. It's been a precursor of inter-process communication inside Operating Systems like UNIX-based OSes, and it's expanded the functionality to many other areas. For these reasons, message queues fit perfectly into our narrative.

Messages are stored in a queue until they are processed / consumed by a consumer. Once they are consumed, they are eliminated from the queue. Every message is processed only once, and by only one consumer. In case of having several consumers, each consumer will process different messages.

The message queue provider for our architecture is [RabbitMQ](https://www.rabbitmq.com/), a widely known, completely open-source message broker able to integrate all the above mentioned functionalities. I've created a producer ([mq_producer.py](../telemetry_f1_2021/mq_producer.py)) and a consumer of the data / receiver ([mq_receiver.py](../telemetry_f1_2021/mq_receiver.py)). The purpose of the producer is to obtain messages from the F1 2021 game, and add them to our message queue. Complementarily, the receiver will consume the messages from the queue through **web sockets**, and "inject" these messages into our Oracle JET-powered dashboard in order to have real-time visualizations of what's actually going on inside the game.

This is a depiction of the architecture:

![architecture](https://github.com/jasperan/f1-telemetry-oracle/blob/main/img/arch.PNG?raw=true)


# Message queues

In this section, we're going to explain the code we've used to implement the message broker architecture.

## Producer

We're using [the telemetry_f1_2021 listener Python library](https://github.com/jasperan/f1-telemetry-oracle) for encoding / decoding of the in-game packets, which facilitates us reading these packets in human-readable format.

We bind port 20777 to listen for UDP packets coming from the F1 2021 game. This port can be changed; however, the default port in the in-game's settings is configured to 20777. If you're planning to change this, make sure to change the in-game telemetry settings as well.

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

We also declare a queue name. In our case, as it seemed relevant for the architecture, we're using one queue per packet type, to have them distinguished. There is another important reason to make this decision: not all packet types come with the same frequency.

Typically, most packet types are sent out by the F1 2021 game with a frequency of 20Hz (20 times per second), however there are some exceptions. If we just included the same queue for all packet types, we'd receive different types of data into the same queue (not ideal) and at a different pace (not cool, and would make visualizations incorrect, not in real time, which is what we're looking for).

```python
def main():

    connection = pika.BlockingConnection(
    pika.ConnectionParameters(host='localhost', heartbeat=600, blocked_connection_timeout=300))
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

So every time a packet comes in each one of these queues, it will be inserted into the queue.

## Consumer

From the consumer side, we read messages from the queue and transmit them to the Oracle JET Dashboard.

From the point of view of our Python code, we can create a script like this, which will be useful during development to check for connectivity issues in the message queues. We can run it to see if messages are being popped from the queue and that all network configurations are correct:

```python
def main():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost', heartbeat=600, blocked_connection_timeout=300))
    channel = connection.channel()

    list_packet_types = ['PacketMotionData', 'PacketSessionData', 'PacketLapData', 'PacketEventData', 'PacketParticipantsData',
        'PacketCarSetupData', 'PacketCarTelemetryData', 'PacketCarStatusData', 'PacketFinalClassificationData', 'PacketLobbyInfoData',
        'PacketCarDamageData', 'PacketSessionHistoryData']

    # declare all queues, in case the receiver is initialized before the producer.
    for x in list_packet_types:
        channel.queue_declare(queue='{}'.format(x))

    # this is the function that will be executed every time
    def callback(ch, method, properties, body):
        print(" [x] Received %r" % body.decode())

    # consume all queues
    for x in list_packet_types:
        channel.basic_consume(queue='{}'.format(x), on_message_callback=callback, auto_ack=True)
    

    print(' [*] Waiting for messages. To exit press CTRL+C')
    channel.start_consuming()
```

# Web Sockets

Web sockets are especially important in our case, as they are the way we chose to communicate the front-end (Oracle JET-powered website) and message queues. 

Web sockets are a type of implementation of standard sockets (which sit on the transport layer). However, they communicate through the application layer. Standard sockets, as we know from telecommunications engineering, are located on top of the transport layer, which makes them extremely efficient. On the other hand, web sockets sit on top of the application layer which means that they encapsulate sockets in the transport layer over HTTP and this encapsulation also allows to have an easier programming interface: the programming syntax and know-how is much easier than it would be for us to program them using standard sockets. Most things about connectivity, heartbeats, exceptions, among others are taken out of the equation and presented to us in an easy API.

So, the purpose of the web sockets is to communicate the web front-end to the message queue back-end. When messages are requested by the front-end, they are consumed/popped from the queue and an acknowledgement is sent to the back-end to verify the message was properly received.

It's also important to note that, whilst we benefit from an easier API when using web sockets, we lose a bit of performance. However, in our case, with the amount of KB/s being sent in our architecture, the difference is negligible and it doesn't at all affect the performance of our real-time dashboard in the front-end.

So, to summarize: in our use case, the client will be the front-end implemented in JET, and the server will be our telemetry listener inserting data into the RabbitMQ message queue. The front end makes requests using web sockets and changes display values based upon what we receive.

## WS Server (Back-end)

In the back-end, we'll consume from our message queue and send the requested information to the client:

```python
# this variable stores the most recent packet received from the queue
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
    print('{} | WS {} OK'.format(datetime.datetime.now(), collection_name))
    channel.basic_qos(prefetch_count=1)
    # consume queue
    method, properties, body = channel.basic_get(queue=collection_name, auto_ack=True) # we get 1 packet exactly
    del method, properties # we don't need these two values
    try:
        _CURRENT_PACKET = body.decode()
        print(_CURRENT_PACKET)
    except AttributeError as e: # in case there are no packets in the queue, we just create an empty packet for the front-end to interpret.
        _CURRENT_PACKET = {}
    print(_CURRENT_PACKET)
    return json.dumps(_CURRENT_PACKET)


# this code is run every time a WS request comes in.
async def handler(websocket):
    while True:
        message = await websocket.recv()

        if message == 'getPacketCarTelemetryData':
            result = save_packet('PacketCarTelemetryData')
        elif message == 'getPacketSessionData':
            result = save_packet('PacketSessionData')

        await websocket.send(result)



async def main(): # we declare this python script as a web socket server
    async with websockets.serve(handler, "", 8001):
        await asyncio.Future()  # run forever
```

## WS Client (Front-end)

In the front-end, we'll make periodic requests to the web socket server, and update the value to display using JavaScript. The original JavaScript code for this functionality can be found [in this file](https://github.com/peppertech/FormulaPi/blob/main/src/components/content/index.tsx).

During development, a similar code to check for received web socket request/responses was developed. This code is very basic:

```python
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

asyncio.run(hello("ws://WS_SERVER_IP_ADDRESS:WS_PORT"))
```

Note that the chosen commands __getPacketCarTelemetryData__ and __getPacketSessionData__ have to be accepted commands in the web socket server. In our case, they're consistent with each other, and that's the reason why we get responses.

# Credits

Note that a great deal of work regarding the F1 2021 telemetry decoding has already been done by [Chris Hannam](https://github.com/chrishannam). Our repository simply has extended the functionality to integrate with RabbitMQ and Oracle databases.

Also, a warm thank you to [Wojciech Pluta](https://www.linkedin.com/in/wojciechpluta/) and [John Brock](https://www.linkedin.com/in/johnabrock/) for contributing in the development of the Proof of Concept (POC) dashboard for the [AlmaLinux + Oracle Pi Day 2022](https://314piday.com/), where we presented this POC to showcase the capabilities of Oracle JET together with Raspberry Pi.

Finally, remember to check out the front-end code in [this repository](https://github.com/peppertech/FormulaPi).

## How can I get started on OCI?

Remember that you can always sign up for free with OCI! Your Oracle Cloud account provides a number of Always Free services and a Free Trial with US$300 of free credit to use on all eligible OCI services for up to 30 days. These Always Free services are available for an **unlimited** period of time. The Free Trial services may be used until your US$300 of free credits are consumed or the 30 days has expired, whichever comes first. You can [sign up here for free](https://signup.cloud.oracle.com/?language=en_US&sourceType=:ex:tb:::::RC_WWMK220210P00062:Medium_nachoF12021telemetry&SC=:ex:tb:::::RC_WWMK220210P00062:Medium_nachoF12021telemetry&pcode=WWMK220210P00062).

## Join the conversation!

If you’re curious about the goings-on of Oracle Developers in their natural habitat, come [join us on our public Slack channel](https://join.slack.com/t/oracledevrel/shared_invite/zt-uffjmwh3-ksmv2ii9YxSkc6IpbokL1g?customTrackingParam=:ex:tb:::::)! We don’t mind being your fish bowl 🐠

## License

Written by [Ignacio Guillermo Martínez](https://www.linkedin.com/in/ignacio-g-martinez/) [@jasperan](https://github.com/jasperan), edited by [GreatGhostsss](https://github.com/GreatGhostsss)

Copyright (c) 2021 Oracle and/or its affiliates.

Licensed under the Universal Permissive License (UPL), Version 1.0.

See [LICENSE](https://github.com/jasperan/f1-telemetry-oracle/blob/main/LICENSE) for more details.