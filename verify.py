"""Pre-flight check:  uv run verify.py      (or:  python verify.py)

Starts the local server, connects to it the way the browser does, and
exercises the whole loop against the live Deepgram Voice Agent API with no
microphone involved: Settings, the greeting, typed input (InjectUserMessage),
the function-calling round trip using the real handlers from todos.py, and
the personality swap (UpdatePrompt + UpdateSpeak).

Facilitators: run this the morning of a workshop, on the venue wifi.
If it prints PASS, the room is going to be fine.

Needs DEEPGRAM_API_KEY in .env (or the environment).
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).parent
PORT = int(os.environ.get("PORT", "3000"))
URL = f"http://localhost:{PORT}"


async def main():
    print("[verify] starting server...")
    server = subprocess.Popen([sys.executable, str(ROOT / "server.py")], stdout=subprocess.DEVNULL)
    try:
        return await run_checks()
    finally:
        server.terminate()
        server.wait(timeout=5)


async def run_checks():
    seen = set()
    audio_bytes = 0
    function_calls = []
    phase = "settings"
    agent_done = 0
    failure = None

    async with aiohttp.ClientSession() as http:
        for _ in range(40):
            try:
                async with http.get(f"{URL}/health") as r:
                    if r.status == 200:
                        break
            except aiohttp.ClientError:
                pass
            await asyncio.sleep(0.25)
        else:
            print(f"[verify] FAIL — server never came up on port {PORT}")
            return 1

        async with http.ws_connect(f"{URL}/agent") as ws:

            async def send(obj):
                await ws.send_str(json.dumps(obj))

            async def advance():
                nonlocal phase, failure
                if phase == "settings" and agent_done >= 1:
                    phase = "add"
                    print('[verify] typed input: "Add buy oat milk to my list"')
                    await send({"type": "InjectUserMessage", "content": "Add buy oat milk to my list"})
                elif phase == "add" and agent_done >= 2:
                    phase = "persona"
                    print("[verify] applying personality swap (UpdatePrompt + UpdateSpeak)")
                    await send({"type": "ApplyPersona", "persona": "pirate"})
                    await asyncio.sleep(1.5)
                    print('[verify] typed input: "What is on my list?"')
                    await send({"type": "InjectUserMessage", "content": "What is on my list?"})
                elif phase == "persona" and agent_done >= 3:
                    names = [f["name"] for f in function_calls]
                    if "add_item" not in names:
                        failure = "add_item was never called"
                    elif "list_items" not in names:
                        failure = "list_items was never called"
                    elif "PromptUpdated" not in seen:
                        failure = "PromptUpdated never received"
                    elif "SpeakUpdated" not in seen:
                        failure = "SpeakUpdated never received"
                    elif audio_bytes < 100000:
                        failure = f"suspiciously little audio: {audio_bytes} bytes"
                    phase = "done"

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    audio_bytes += len(msg.data)
                    continue
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                event = json.loads(msg.data)
                kind = event.get("type")
                seen.add(kind)

                if kind == "SettingsApplied":
                    print("[verify] SettingsApplied (Flux STT v2 + gpt-4o-mini + Flux TTS v2 accepted)")
                elif kind == "ConversationText":
                    print(f"[verify] {event['role']}: {event['content']}")
                elif kind == "FunctionCall":
                    function_calls.append(event)
                    print(f"[verify] {event['name']}({event['arguments']}) → \"{event['result']}\"")
                elif kind == "PromptUpdated":
                    print("[verify] PromptUpdated")
                elif kind == "SpeakUpdated":
                    print("[verify] SpeakUpdated (Flux voice + expressivity accepted)")
                elif kind == "AgentAudioDone":
                    agent_done += 1
                    await advance()
                elif kind == "Error":
                    failure = f"API error: {json.dumps(event)}"
                    phase = "done"

                if phase == "done":
                    break

            if phase != "done" and failure is None:
                failure = f"connection closed early (close code {ws.close_code})"

    print("\n[verify] events seen:", ", ".join(sorted(seen)))
    print("[verify] audio bytes received:", audio_bytes)
    print("[verify] function calls:", ", ".join(f["name"] for f in function_calls) or "none")
    if failure:
        print(f"\n[verify] RESULT: FAIL — {failure}")
        return 1
    print("\n[verify] RESULT: PASS — the whole loop works.")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(asyncio.wait_for(main(), timeout=120))
    except asyncio.TimeoutError:
        print("\n[verify] RESULT: FAIL — timed out after 120s")
        code = 1
    sys.exit(code)
