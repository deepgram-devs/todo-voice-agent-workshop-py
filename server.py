"""Local server for the workshop.

It does two jobs:
  1. Serves the frontend files from public/
  2. Bridges a WebSocket between your browser and the Deepgram Voice Agent
     session in agent.py, so your API key can stay on the server (in .env)
     instead of in the browser.

You will not need to edit this file during the workshop.

Run it with:  uv run server.py      (or:  python server.py)
"""

import asyncio
import json
import os
import re
from pathlib import Path

from aiohttp import WSMsgType, web

import todos
from agent import AgentSession

ROOT = Path(__file__).parent
PUBLIC = ROOT / "public"


# Load the .env file if it exists (no dependency needed). It tolerates the
# ways a first-time terminal user actually ends up creating one: Windows
# PowerShell 5 writes UTF-16, cmd.exe keeps the quotes, some editors add a
# byte-order mark, and keys get pasted with stray spaces or quotes.
def load_env(path):
    if not path.exists():
        return
    raw = path.read_bytes()
    if raw[:2] == b"\xff\xfe":
        text = raw[2:].decode("utf-16-le")  # UTF-16 LE with BOM (PowerShell 5's default)
    elif len(raw) > 1 and raw[0] != 0 and raw[1] == 0:
        text = raw.decode("utf-16-le")  # UTF-16 LE without BOM
    else:
        text = raw.decode("utf-8-sig")
    for raw_line in text.splitlines():
        line = raw_line.strip().strip("\"'")  # cmd.exe: echo "A=B" keeps the quotes
        match = re.match(r"^(?:export\s+)?(\w+)\s*=\s*(.*)$", line)
        if not match:
            continue
        value = match.group(2).strip().strip("\"'").strip()
        if value:
            os.environ[match.group(1)] = value


load_env(ROOT / ".env")

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "3000"))
SERVER_API_KEY = os.environ.get("DEEPGRAM_API_KEY") or None


async def index(_request):
    return web.FileResponse(PUBLIC / "index.html")


async def health(_request):
    return web.json_response({"status": "ok"})


# Let the frontend know if a server-side API key is configured
async def config(_request):
    return web.json_response({"hasApiKey": bool(SERVER_API_KEY)})


# The list, for the first render before the agent is connected
async def api_todos(_request):
    return web.json_response(todos.todos)


# WebSocket endpoint on /agent
async def agent_socket(request):
    ws = web.WebSocketResponse(max_msg_size=4 * 1024 * 1024)
    await ws.prepare(request)

    # Use API key from query param, or fall back to server-side .env key
    api_key = request.query.get("apiKey") or SERVER_API_KEY
    if not api_key:
        await ws.close(code=4001, message=b"No API key provided (set DEEPGRAM_API_KEY in .env or pass via frontend)")
        return ws

    print("[ws] Browser connected, opening Deepgram connection...")

    async def send_json(obj):
        if not ws.closed:
            await ws.send_str(json.dumps(obj))

    async def send_audio(chunk):
        if not ws.closed:
            await ws.send_bytes(chunk)

    session = AgentSession(api_key, send_json=send_json, send_audio=send_audio)
    deepgram = asyncio.create_task(session.run())

    async def read_browser():
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                await session.send_audio(msg.data)  # microphone chunks
            elif msg.type == WSMsgType.TEXT:
                try:
                    await session.handle_browser_message(json.loads(msg.data))
                except json.JSONDecodeError:
                    print(f"[ws] Ignoring non-JSON text frame: {msg.data[:80]!r}")
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.ERROR):
                break

    browser = asyncio.create_task(read_browser())

    # Whichever side hangs up first ends the session for both.
    done, pending = await asyncio.wait({deepgram, browser}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    if deepgram in done and not ws.closed:
        reason = session.close_reason or "Deepgram connection closed"
        await ws.close(code=session.close_code if session.close_code != 1000 else 1011, message=reason.encode()[:100])
    print("[ws] Browser disconnected")
    return ws


def make_app():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_get("/api/config", config)
    app.router.add_get("/api/todos", api_todos)
    app.router.add_get("/agent", agent_socket)
    app.router.add_static("/", PUBLIC)  # everything else in public/ — must be last
    return app


if __name__ == "__main__":
    print(f"To-do voice agent running at http://localhost:{PORT}")
    web.run_app(make_app(), host=HOST, port=PORT, print=None, access_log=None)
