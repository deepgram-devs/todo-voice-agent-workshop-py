"""Deepgram Voice Agent session: Settings, events, functions, personalities.

This file is the heart of the voice layer. Reading it top to bottom is
Module 2 of the workshop. You won't need to edit it for the core modules.

One AgentSession is one browser tab talking to one Deepgram connection.
The browser only handles microphone, speaker, and what's on screen; every
decision about the agent — what it listens with, what it thinks with, what
it can do — is made here, in Python, with the Deepgram SDK.
"""

import asyncio
import inspect
import json

from deepgram import AsyncDeepgramClient
from deepgram.agent.v1.types import (
    AgentV1InjectAgentMessage,
    AgentV1InjectUserMessage,
    AgentV1SendFunctionCallResponse,
    AgentV1Settings,
    AgentV1SettingsAgent,
    AgentV1SettingsAgentListen,
    AgentV1SettingsAgentListenProvider_V2,
    AgentV1SettingsAudio,
    AgentV1SettingsAudioInput,
    AgentV1SettingsAudioOutput,
    AgentV1UpdatePrompt,
    AgentV1UpdateSpeak,
)
from deepgram.core.events import EventType
from deepgram.types.speak_settings_v1 import SpeakSettingsV1
from deepgram.types.speak_settings_v1provider import SpeakSettingsV1Provider_Deepgram
from deepgram.types.think_settings_v1 import ThinkSettingsV1
from deepgram.types.think_settings_v1functions_item import ThinkSettingsV1FunctionsItem
from deepgram.types.think_settings_v1provider import ThinkSettingsV1Provider_OpenAi

import todos

# --- Settings: everything the agent needs to know, in one message ---

AGENT_PROMPT = """You are the voice of the user's to-do list. Help them add items, hear what's on the list, mark things done, and delete things — using the functions you've been given.

Rules:
- When the user wants to add a task, call add_item. Rephrase their words into a short task if needed.
- When they ask what's on the list or what's left, call list_items.
- When they say they finished something, call complete_item.
- Deleting is permanent. When the user asks to delete something, do NOT call delete_item yet. Ask them to confirm, naming the item. Call delete_item only after they have clearly said yes. If they say no, never mind, or change the subject, leave the list alone and say so.
- When the user says undo or wants something back, call undo_delete.
- Always confirm what you did, briefly.
- Be warm and a little dry. You may be gently unimpressed by how long items have been on the list, but never mean, and never guilt-trip.
- Keep responses to one or two short sentences — this is a spoken conversation.
- NEVER use markdown, asterisks, bullet points, numbered-list formatting, or emoji. Your words are read aloud exactly as written."""

GREETING = "Hi! I'm your to-do list. Ask me what's on it, or give me something new to remember."


def build_settings():
    return AgentV1Settings(
        audio=AgentV1SettingsAudio(
            input=AgentV1SettingsAudioInput(encoding="linear16", sample_rate=16000),
            output=AgentV1SettingsAudioOutput(encoding="linear16", sample_rate=24000, container="none"),
        ),
        agent=AgentV1SettingsAgent(
            # LISTEN: Flux turns your speech into text, and decides when your
            # turn is over (so the agent knows when to reply — and when to shut
            # up if you interrupt).
            listen=AgentV1SettingsAgentListen(
                provider=AgentV1SettingsAgentListenProvider_V2(
                    type="deepgram", model="flux-general-en", version="v2"
                ),
            ),
            # THINK: the LLM. Managed by Deepgram — no second API key needed.
            think=ThinkSettingsV1(
                provider=ThinkSettingsV1Provider_OpenAi(type="open_ai", model="gpt-4o-mini", temperature=0.7),
                prompt=AGENT_PROMPT,
                functions=[ThinkSettingsV1FunctionsItem(**f) for f in todos.FUNCTION_DEFINITIONS],
            ),
            # SPEAK: Flux TTS turns the reply back into a voice.
            speak=SpeakSettingsV1(
                provider=SpeakSettingsV1Provider_Deepgram(type="deepgram", model="flux-hannah-en", version="v2"),
            ),
            greeting=GREETING,
        ),
    )


# --- Personalities (Module 5, opt-in) ---
# A personality is three knobs turned at once, live, mid-conversation:
#   1. UpdatePrompt  — who the agent thinks it is
#   2. UpdateSpeak   — which Flux voice it speaks with
#   3. expressivity  — how theatrically it delivers (-2 flat ... 2 dramatic)
# The conversation history survives the swap. Try it mid-chat.

PERSONAS = {
    "classic": {
        "label": "Classic",
        "voice": "flux-hannah-en",
        "expressivity": 0,
        "prompt": AGENT_PROMPT,
    },
    "sergeant": {
        "label": "Drill Sergeant",
        "voice": "flux-cliff-en",
        "expressivity": 2,
        "prompt": """You are DRILL SERGEANT TODO, the loudest to-do list in the barracks. Manage the user's task list using the functions you've been given: add_item, list_items, complete_item, delete_item.

Rules:
- Bark. Short sentences. Call the user "RECRUIT".
- Completed tasks earn a HOORAH. Unfinished tasks earn theatrical disappointment — at the TASKS, never genuinely at the user.
- Still be genuinely helpful: always call the right function and confirm what happened.
- One to two sentences per reply. You are loud, not long-winded.
- NEVER use markdown, asterisks, bullet points, or emoji. Your words are read aloud exactly as written.""",
    },
    "passive": {
        "label": "Passive-Aggressive",
        "voice": "flux-alexis-en",
        "expressivity": -1,
        "prompt": """You are an exquisitely polite, quietly judgmental to-do list. Manage the user's task list using the functions you've been given: add_item, list_items, complete_item, delete_item.

Rules:
- Perfectly courteous, faintly wounded. "Of course. Adding it to the list. The list you have."
- You may note, mildly, how long things have been on the list. Never insult the user directly — you would simply never.
- Still be genuinely helpful: always call the right function and confirm what happened.
- One to two short sentences. Sighs are conveyed through word choice, not stage directions.
- NEVER use markdown, asterisks, bullet points, or emoji. Your words are read aloud exactly as written.""",
    },
    "pirate": {
        "label": "Pirate",
        "voice": "flux-rufus-en",
        "expressivity": 2,
        "prompt": """You are the to-do list of a pirate captain. Manage the user's task list using the functions you've been given: add_item, list_items, complete_item, delete_item.

Rules:
- Full pirate: "arr", "aye", "the list o' deeds". Tasks are "quests". Completing one deserves a hearty cheer.
- Still be genuinely helpful: always call the right function and confirm what happened.
- One to two short sentences per reply, delivered with gusto.
- NEVER use markdown, asterisks, bullet points, or emoji. Your words are read aloud exactly as written.""",
    },
}


# --- Small helpers for the SDK's message objects ---
# Known events arrive as typed objects (with attributes); events newer than
# the SDK arrive as plain dicts. These two helpers hide the difference.


def event_type(message):
    if isinstance(message, dict):
        return message.get("type")
    return getattr(message, "type", None)


def to_dict(message):
    if isinstance(message, dict):
        return message
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    return message.dict(exclude_none=True)


class AgentSession:
    """One browser tab ⇄ one Deepgram Voice Agent connection.

    `send_json` and `send_audio` are how this session talks back to the
    browser: JSON events for the event log and screen, raw PCM for the
    speaker. server.py provides them.
    """

    def __init__(self, api_key, send_json, send_audio):
        self._api_key = api_key
        self._send_json = send_json
        self._send_audio = send_audio
        self._agent = None
        self.close_code = 1000
        self.close_reason = ""

    async def log(self, tag, text):
        # A line for the browser's event log (and the terminal).
        print(f"[dg] {text}")
        await self._send_json({"type": "Log", "tag": tag, "text": text})

    # --- Connection ---

    async def run(self):
        """Connect to Deepgram and stay connected until either side hangs up."""
        client = AsyncDeepgramClient(api_key=self._api_key)
        keepalive = None
        try:
            async with client.agent.v1.connect() as agent:
                self._agent = agent
                print("[dg] Connected to Deepgram")
                agent.on(EventType.MESSAGE, self._on_message)
                agent.on(EventType.ERROR, self._on_error)

                # The on-screen list mirrors the Python list whenever a
                # function changes it.
                todos.set_on_change(self._todos_changed)
                await self._send_todos()

                keepalive = asyncio.create_task(self._keep_alive())
                # start_listening() runs until Deepgram closes the connection.
                await agent.start_listening()
        except asyncio.CancelledError:
            raise  # the browser went away — let the `async with` close the socket
        except Exception as exc:
            self.close_code = 4002
            self.close_reason = "Deepgram connection error"
            print(f"[dg] Deepgram error: {exc}")
            await self._send_json({"type": "Error", "description": str(exc)})
        finally:
            if keepalive:
                keepalive.cancel()
            self._agent = None
            print("[dg] Deepgram closed")

    async def _keep_alive(self):
        # Deepgram hangs up on a silent connection. A KeepAlive every 5 seconds
        # keeps a muted or quiet session open.
        while True:
            await asyncio.sleep(5)
            if self._agent:
                await self._agent.send_keep_alive()

    async def _on_error(self, exc):
        await self.log("error", f"Deepgram error: {exc}")

    # --- Messages from the browser ---

    async def send_audio(self, chunk):
        """Microphone audio from the browser → Deepgram."""
        if self._agent:
            await self._agent.send_media(chunk)

    async def handle_browser_message(self, msg):
        """Typed text and persona clicks from the browser."""
        if not self._agent:
            return
        kind = msg.get("type")
        if kind == "InjectUserMessage":
            # The agent treats typed text exactly as if you had spoken it —
            # same functions, same reply, same voice on the way back. Deepgram
            # echoes it back as a user ConversationText, which is what lands
            # in the event log.
            await self._agent.send_inject_user_message(AgentV1InjectUserMessage(content=msg.get("content", "")))
        elif kind == "ApplyPersona":
            await self.apply_persona(msg.get("persona"))
        else:
            await self.log("error", f"Unknown message from the browser: {kind}")

    # --- Messages from Deepgram ---

    async def _on_message(self, message):
        if isinstance(message, bytes):
            # Binary frames are the agent's voice: raw audio for the browser to play.
            await self._send_audio(message)
            return

        kind = event_type(message)

        if kind == "Welcome":
            # Settings must be the first thing we send. Everything the agent
            # needs to know — how to listen, think, and speak — goes in one message.
            await self._agent.send_settings(build_settings())
            await self._send_json(to_dict(message))
            await self.log("system", "Settings sent (Flux STT + gpt-4o-mini + Flux TTS)")
            return

        if kind == "FunctionCallRequest":
            await self._handle_function_calls(message)
            return

        # Everything else — SettingsApplied, ConversationText, UserStartedSpeaking,
        # EndOfTurn, LatencyReport, AgentAudioDone, PromptUpdated, SpeakUpdated,
        # Error, Warning, History... — goes to the browser as-is. agent.js turns
        # each one into a line in the event log.
        await self._send_json(to_dict(message))

    # When the agent decides it needs one of YOUR functions, Deepgram sends a
    # FunctionCallRequest. We run the matching handler from todos.py and send
    # the result back as a FunctionCallResponse. Until that response arrives,
    # the agent has nothing to say — that silence is called "dead air".
    # CHALLENGE "Cover the dead air": a handler may be slow (delete_item is
    # `async` so it can be). If it hasn't answered within 400ms, have the agent
    # fill the silence. behavior="queue" says "after whatever you're saying,
    # not instead of it" — and unlike the default behavior it isn't refused
    # mid-turn. Fast handlers (all of ours, normally) cancel it in time.
    async def _handle_function_calls(self, message):
        for fn in message.functions:
            handler = todos.FUNCTION_HANDLERS.get(fn.name)
            args = json.loads(fn.arguments) if fn.arguments else {}

            filler = asyncio.ensure_future(self._filler_after(0.4))
            if handler is None:
                result = f"Unknown function: {fn.name}"
            else:
                try:
                    result = handler(args)
                    if inspect.isawaitable(result):
                        result = await result
                except Exception as exc:
                    result = f"Error running {fn.name}: {exc}"
            filler.cancel()

            content = result if isinstance(result, str) else json.dumps(result)

            # Send the result back so the agent can answer
            await self._agent.send_function_call_response(
                AgentV1SendFunctionCallResponse(id=fn.id, name=fn.name, content=content)
            )
            # ...and tell the browser, so the event log tells the whole story.
            await self._send_json(
                {"type": "FunctionCall", "name": fn.name, "arguments": fn.arguments or "", "result": content}
            )

    async def _filler_after(self, seconds):
        await asyncio.sleep(seconds)
        if self._agent:
            await self.log("system", "Function is slow — injecting filler speech")
            await self._agent.send_inject_agent_message(
                AgentV1InjectAgentMessage(message="One second, let me find that.", behavior="queue")
            )

    # --- The on-screen list ---

    def _todos_changed(self, items):
        # Called synchronously from todos.notify_change(); hop back onto the event loop.
        asyncio.ensure_future(self._send_todos())

    async def _send_todos(self):
        await self._send_json({"type": "TodoList", "items": todos.todos})

    # --- Personalities ---

    async def apply_persona(self, key):
        persona = PERSONAS.get(key)
        if not persona or not self._agent:
            return
        await self._agent.send_update_prompt(AgentV1UpdatePrompt(prompt=persona["prompt"]))
        await self._agent.send_update_speak(
            AgentV1UpdateSpeak(
                speak=SpeakSettingsV1(
                    provider=SpeakSettingsV1Provider_Deepgram(
                        type="deepgram",
                        model=persona["voice"],
                        version="v2",
                        expressivity=persona["expressivity"],
                    ),
                ),
            )
        )
        await self.log("system", f"Switching personality to {persona['label']}...")
