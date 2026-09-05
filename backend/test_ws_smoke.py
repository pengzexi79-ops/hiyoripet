# backend/test_ws_smoke.py
# 本地冒烟测试：连 WS → ping/pong → text-input（无 FOXTOKEN_KEY 时预期走 error 路径）。
# 用法：先 `uvicorn server:app`，另开终端 `python test_ws_smoke.py`
import asyncio
import json
import os
import websockets

URL = os.environ.get("PET_WS_URL", "ws://localhost:8000/ws")


async def main():
    async with websockets.connect(URL) as ws:
        await ws.send(json.dumps({"type": "ping"}))
        print("<-", await ws.recv())
        await ws.send(json.dumps({"type": "text-input", "text": "你好，你是谁？"}))
        print("(已发送 text-input，等待后端响应…)")
        for _ in range(30):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                print("<-", msg)
                m = json.loads(msg)
                if m.get("type") in ("error", "ai-response"):
                    break
            except asyncio.TimeoutError:
                print("(接收超时，结束)")
                break


if __name__ == "__main__":
    asyncio.run(main())
