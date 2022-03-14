#!/usr/bin/env python
import pika, sys, os

def main():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost', heartbeat=600, blocked_connection_timeout=300))
    channel = connection.channel()

    list_packet_types = ['PacketMotionData', 'PacketSessionData', 'PacketLapData', 'PacketEventData', 'PacketParticipantsData',
        'PacketCarSetupData', 'PacketCarTelemetryData', 'PacketCarStatusData', 'PacketFinalClassificationData', 'PacketLobbyInfoData',
        'PacketCarDamageData', 'PacketSessionHistoryData']

    # declare all queues, in case the receiver is initialized before the producer.
    for x in list_packet_types:
        channel.queue_declare(queue='{}'.format(x))


    def callback(ch, method, properties, body):
        print(" [x] Received %r" % body.decode())

    # consume all queues
    for x in list_packet_types:
        channel.basic_consume(queue='{}'.format(x), on_message_callback=callback, auto_ack=True)
    

    print(' [*] Waiting for messages. To exit press CTRL+C')
    channel.start_consuming()



if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrupted')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)