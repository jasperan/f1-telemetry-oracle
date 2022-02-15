import asyncio
from aiohttp import web
import socketio
'''
import pika
import eventlet
import socketio

sio = socketio.Server()
app = socketio.WSGIApp(sio, static_files={
    '/': {'content_type': 'text/html', 'filename': 'index.html'}
})

@sio.event
def connect(sid, environ):
    print('connect ', sid)
    connection = pika.BlockingConnection(
    pika.ConnectionParameters(host='localhost'))
    channel = connection.channel()

    list_packet_types = ['PacketMotionData', 'PacketSessionData', 'PacketLapData', 'PacketEventData', 'PacketParticipantsData',
        'PacketCarSetupData', 'PacketCarTelemetryData', 'PacketCarStatusData', 'PacketFinalClassificationData', 'PacketLobbyInfoData',
        'PacketCarDamageData', 'PacketSessionHistoryData']

    # declare all queues
    for x in list_packet_types:
        channel.queue_declare(queue='{}'.format(x))

    # PacketMotionData -> queue
    sio.emit('PacketMotionData', {})


@sio.event
def message(sid, data):
    print("message ", data)
    sio.emit('PacketExample', {'foo': 'bar'})


@sio.event
def disconnect(sid):
    print('disconnect ', sid)

if __name__ == '__main__':
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app)'''

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

    list_packet_types = ['PacketMotionData', 'PacketSessionData', 'PacketLapData', 'PacketEventData', 'PacketParticipantsData',
        'PacketCarSetupData', 'PacketCarTelemetryData', 'PacketCarStatusData', 'PacketFinalClassificationData', 'PacketLobbyInfoData',
        'PacketCarDamageData', 'PacketSessionHistoryData']

    # declare all queues
    for x in list_packet_types:
        channel.queue_declare(queue='{}'.format(x))

    # PacketMotionData -> queue
    await emit_packets()


async def emit_packets():
    await sio.emit('PacketMotionData', {'a':'b'})

@sio.event
async def chat_message(sid, data):
    print("message ", data)

@sio.event
def disconnect(sid):
    print('disconnect ', sid)

app.router.add_get('/', index)

if __name__ == '__main__':
    web.run_app(app)