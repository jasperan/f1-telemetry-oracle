import asyncio
from aiohttp import web
import socketio
import pika



sio = socketio.AsyncServer()
app = web.Application()
sio.attach(app)



async def index(request):
    """Serve the client-side application."""
    with open('index.html') as f:
        return web.Response(text=f.read(), content_type='text/html')



@sio.event
async def connect(sid, environ):
    print('connect ', sid)
    connection = pika.BlockingConnection(
    pika.ConnectionParameters(host='localhost'))
    channel = connection.channel()

    '''list_packet_types = ['PacketMotionData', 'PacketSessionData', 'PacketLapData', 'PacketEventData', 'PacketParticipantsData',
        'PacketCarSetupData', 'PacketCarTelemetryData', 'PacketCarStatusData', 'PacketFinalClassificationData', 'PacketLobbyInfoData',
        'PacketCarDamageData', 'PacketSessionHistoryData']'''

    list_packet_types = ['PacketCarTelemetryData']

    # declare all queues
    for x in list_packet_types:
        channel.queue_declare(queue='{}'.format(x))

    # consume all queues
    for x in list_packet_types:
        channel.basic_consume(queue='{}'.format(x), on_message_callback=callback, auto_ack=True)
        channel.start_consuming()
    # PacketMotionData -> queue


async def callback(ch, method, properties, body):
    print(" [x] Received %r" % body.decode())
    await emit_packet(x, body.decode())


async def emit_packet(name_to_send, obj_to_send):
    await sio.emit(name_to_send, obj_to_send)



@sio.event
async def chat_message(sid, data):
    print("message ", data)



@sio.event
def disconnect(sid):
    print('disconnect ', sid)



app.router.add_get('/', index)



if __name__ == '__main__':
    web.run_app(app)