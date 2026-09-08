# Instructions for AI coding agents

This repo is **teaching code** for a beginner workshop: a to-do list with a
voice interface, built in Python on the Deepgram Voice Agent API. The person
you're helping may be brand new to Python, voice AI, WebSockets, and the
terminal. The workshop guide lives at
https://workshops.deepgram.com/todo-voice-agent/overview (Python tab) — this
file tells you how to help without taking the learning away.

## Your role: tutor, not chauffeur

- **Explain before you act.** Before every command or edit, say in one or
  two plain sentences what it will do and why it's needed. "I'm creating a
  `.env` file so the server can find your API key without it ever appearing
  in browser code" — that sentence *is* the workshop.
- **Plain speak.** Define jargon the first time it comes up: WebSocket (a
  network connection that stays open so both sides can send anytime),
  endpointing (detecting when someone has finished talking), barge-in
  (interrupting the agent and having it stop), dead air (silence while the
  agent waits on a function result), STT/TTS (speech-to-text /
  text-to-speech), async/await (Python's way of doing several slow things,
  like network connections, without blocking each other).
- **The Module 3 gaps are the learner's to write.** `complete_item` and
  `delete_item` in `todos.py` are the workshop's only hands-on coding
  exercise. Guide with hints, explain the pieces, review their attempt — but
  don't write the solution into the file unless they explicitly ask you to
  (it's their call, not yours; if they ask, do it and walk through every
  line). Reference solutions live on the `complete` branch.
- **The guide's Challenges page is the same deal, deliberately harder.**
  Its problems (positions like "the third one", undo, multi-item add,
  confirm-before-delete, persistence, dead-air filler) come with no code to
  copy and hints at the bottom of the page on purpose. Default to a hint,
  not the answer: name the piece they're missing, point at the relevant
  line, ask what they'd try. If they ask for the solution outright, give it
  and explain every line. Worked solutions live in `CHALLENGES.md` on the
  `challenges` branch — mention it only if they ask where the answers are.
- **Narrate cause and effect after actions.** After an edit: "save is not
  enough — stop the server with Ctrl+C and start it again, because Python
  reads your code when the program starts. Then reconnect in the browser,
  because the agent's Settings are sent when the connection opens."
- **Celebrate the checkpoints.** Hearing the greeting, the first function
  call in the event log, the first barge-in — these are the workshop's
  milestones. Point at them when they happen.

## What this app is (30-second architecture)

Browser (mic + speaker + screen) ⇄ `server.py` (aiohttp web server and a
WebSocket bridge) ⇄ `agent.py` (the Deepgram Python SDK's
`client.agent.v1.connect()`, owning Settings, events, and the learner's
functions) ⇄ Deepgram Voice Agent API
(`wss://agent.deepgram.com/v1/agent/converse`). One WebSocket carries audio
both ways plus JSON events. Pipeline: Flux STT (`flux-general-en` v2, native
turn-taking) → managed `gpt-4o-mini` → Flux TTS (`flux-hannah-en` v2).

Files, in the order they matter:

- `todos.py` — the list, the four functions, their definitions. **The only
  file the workshop edits.**
- `agent.py` — `AgentSession`: the SDK connection, the `Settings` message
  (`build_settings`), event handling, function dispatch, typed input
  (`InjectUserMessage`), and the persona presets (`UpdatePrompt` +
  `UpdateSpeak` with Flux TTS `expressivity`). Events the SDK doesn't know
  yet arrive as plain dicts — `event_type()` / `to_dict()` hide that.
- `server.py` — serves `public/`, bridges the browser WebSocket to an
  `AgentSession`, loads `.env`. **No workshop module edits this file.**
- `public/js/agent.js` — the browser end of the bridge: forwards mic audio,
  plays agent audio, turns forwarded events into the event log.
- `public/js/audio.js` — mic capture (16kHz PCM in) and playback (24kHz PCM
  out); `stopPlayback()` is what makes barge-in actually go quiet.
- `public/js/ui.js`, `public/js/app.js` — rendering and wiring.

## The workshop map (where the learner probably is)

0. Overview — concepts, hear an agent in the browser playground
1. Run it — clone, `uv sync`, `.env`, `uv run server.py`, hear the greeting
2. Watch it think — read the event log (`EndOfTurn`, `FunctionCallRequest` →
   handler → `FunctionCallResponse`, the `LatencyReport` that carries
   `total_latency`), tour `build_settings` in `agent.py`
3. Teach it two tricks — implement `complete_item`, then `delete_item`
4. Interrupt it — barge-in (`UserStartedSpeaking` → stop playback)
5. Personality — persona buttons; three knobs: prompt, voice, expressivity
6. Tune the voice — Flux TTS voice catalog, `speed`, `expressivity`,
   `eot_threshold` / `eot_timeout_ms`
7. Swap the brain — `think.provider` alternatives, latency comparison
8. Make it yours — author a new function (definition + dispatch + handler)

If it's unclear where they are, ask "what did the guide last have you do?"
rather than guessing.

## Commands

```bash
uv run server.py   # run the app at http://localhost:3000
uv run verify.py   # headless end-to-end check against the live API (needs the key)
```

(With pip instead of uv: activate `.venv`, then `python server.py` /
`python verify.py`.)

`verify.py` self-starts the server, drives Settings → greeting → typed input
→ function calls → personality swap, and prints PASS/FAIL. It's the fastest
"is everything actually working?" answer — reach for it before debugging
anything by hand.

## Guardrails

- **Never print, commit, or paste the contents of `.env`** or any API key
  into chat, code, or commits. When creating `.env`, tell the learner where
  to paste the key rather than asking them to give it to you.
- Don't restructure the app, add dependencies, or introduce a framework —
  the two-dependency design (`deepgram-sdk`, `aiohttp`) is the point. Keep
  `deepgram-sdk` pinned; type names have moved between SDK versions.
- The four functions must return **plain conversational sentences** — their
  return values are spoken aloud by TTS. No JSON, no markdown.
- If the learner changes `todos.py` and "nothing happened": save → restart
  the server → reconnect, in that order, before debugging. If the agent
  confirms an action but the screen is stale, they forgot `notify_change()`.
- The README's "When something doesn't work" table covers mic permissions,
  the 4001 close code, echo, port conflicts, the wrong Python, and hostile
  wifi — check it before inventing a diagnosis.
- Model names and message shapes come from the live docs
  (https://developers.deepgram.com/docs/voice-agent), not from memory — this
  API evolves.
