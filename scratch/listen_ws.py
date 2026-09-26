import asyncio
import json
import websockets

async def listen():
    try:
        async with websockets.connect('ws://localhost:8088/mock/v2/marketfeed/ws') as ws:
            print("Connected to 8088 WS!")
            for i in range(15):
                msg = await ws.recv()
                try:
                    data = json.loads(msg)
                    print(f"Msg {i}: type={data.get('type')} sym={data.get('symbol')} key={data.get('key')} ltp={data.get('ltp')} oi={data.get('oi')}")
                except Exception:
                    print(f"Msg {i}: raw={msg[:100]}")
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    asyncio.run(listen())
