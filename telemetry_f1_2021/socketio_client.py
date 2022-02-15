import asyncio
import socketio

sio = socketio.AsyncClient()

@sio.event
async def connect():
    print('connection established')

@sio.event
async def get_message():
    print('get_message emit')
    await sio.emit('get_message')

@sio.event
async def disconnect():
    print('disconnected from server')

async def main():
    await sio.connect('http://localhost:8080')
    await sio.get_message()
    #await sio.wait()

if __name__ == '__main__':
    asyncio.run(main())