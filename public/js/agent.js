// The browser's half of the conversation: one WebSocket to server.py.
//
// The agent itself lives in Python (agent.py) — that's where the Settings,
// the functions, and the personalities are. This file only carries audio
// and events between the page and the server:
//
//   browser → server   binary: microphone audio (16kHz PCM)
//                      JSON:   { type: 'InjectUserMessage', content }   typed text
//                              { type: 'ApplyPersona', persona }        persona button
//   server → browser   binary: the agent's voice (24kHz PCM)
//                      JSON:   every Deepgram event, forwarded as-is, plus
//                              { type: 'FunctionCall', name, arguments, result }
//                              { type: 'TodoList', items }
//                              { type: 'Log', tag, text }
//
// You won't need to edit this file during the workshop.

// Connection states
export const States = {
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  CONFIGURING: 'configuring',
  CONNECTED: 'connected',
  ERROR: 'error',
};

let ws = null;
let state = States.DISCONNECTED;

// Callbacks the app registers
let onStateChange = null;
let onAudioReceived = null;
let onDebugMessage = null;
let onTodoList = null;
let onConversationText = null;

export function setCallbacks({ onState, onAudio, onDebug, onTodos, onText }) {
  onStateChange = onState;
  onAudioReceived = onAudio;
  onDebugMessage = onDebug;
  onTodoList = onTodos;
  onConversationText = onText;
}

function setState(newState) {
  state = newState;
  if (onStateChange) onStateChange(newState);
}

function debug(tag, text) {
  if (onDebugMessage) onDebugMessage(tag, text);
}

// --- Connection ---

export function connect(apiKey) {
  if (ws) disconnect();

  setState(States.CONNECTING);

  // We connect to OUR server (server.py), which owns the Deepgram
  // connection. That way the API key can live in .env instead of the browser.
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const params = apiKey ? `?apiKey=${encodeURIComponent(apiKey)}` : '';
  const url = `${protocol}//${window.location.host}/agent${params}`;

  const socket = new WebSocket(url);
  socket.binaryType = 'arraybuffer';
  ws = socket;

  socket.onopen = () => {
    debug('system', 'WebSocket connected, waiting for Welcome...');
  };

  socket.onmessage = (event) => {
    if (socket !== ws) return; // a connection we've already moved on from
    if (event.data instanceof ArrayBuffer) {
      // Binary frames are the agent's voice: raw audio to play
      if (onAudioReceived) onAudioReceived(event.data);
      return;
    }

    // Text frames are JSON events
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      debug('error', `Failed to parse message: ${event.data}`);
      return;
    }

    handleMessage(msg);
  };

  socket.onclose = (event) => {
    if (socket !== ws) return; // closed by us, or superseded by a newer connection
    debug('system', `Connection closed: ${event.code} ${event.reason}`);
    ws = null;
    setState(States.DISCONNECTED);
  };

  socket.onerror = () => {
    if (socket !== ws) return;
    debug('error', 'WebSocket error');
    ws = null;
    setState(States.ERROR);
  };
}

export function disconnect() {
  if (ws) {
    ws.close();
  }
  ws = null;
  setState(States.DISCONNECTED);
}

export function isConnected() {
  return state === States.CONNECTED;
}

function send(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(obj));
  }
}

// Send binary audio (microphone chunks) to the agent
export function sendAudio(arrayBuffer) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(arrayBuffer);
  }
}

// Send TYPED text to the agent. The agent treats it exactly as if you had
// spoken it — same functions, same reply, same voice on the way back.
export function sendTextMessage(text) {
  send({ type: 'InjectUserMessage', content: text });
  // No log line here on purpose: the agent echoes your text back as a
  // ConversationText event, and that is what lands in the event log.
}

// Ask the server to swap personality (Module 5). The prompts and voices
// live in agent.py's PERSONAS.
export function applyPersona(personaKey) {
  send({ type: 'ApplyPersona', persona: personaKey });
}

// --- Message handling ---
// Most of these are Deepgram's own events, forwarded by the server. The
// last three (FunctionCall, TodoList, Log) come from server.py itself.

function handleMessage(msg) {
  switch (msg.type) {
    case 'Welcome':
      debug('system', `Welcome received (request_id: ${msg.request_id})`);
      setState(States.CONFIGURING);
      break;

    case 'SettingsApplied':
      debug('system', 'Settings applied — the agent is listening');
      setState(States.CONNECTED);
      break;

    case 'ConversationText':
      // The transcript, both directions. It goes to the chat bubbles AND the
      // event log, so the log reads as one story.
      debug(msg.role === 'user' ? 'user' : 'agent', msg.content);
      if (onConversationText) onConversationText(msg.role, msg.content);
      break;

    case 'EndOfTurn':
      // Flux STT decided you were finished. The LLM's turn starts now.
      debug('system', 'End of turn — Flux STT decided you were finished');
      break;

    case 'UserStartedSpeaking':
      // Barge-in: you started talking, so the agent must stop.
      debug('system', 'You started speaking — any agent audio stops here (barge-in)');
      if (onAudioReceived) onAudioReceived(null); // null = stop playback
      break;

    case 'LatencyReport':
      // Several arrive per turn, one per stage. The one carrying
      // total_latency is the number to watch: from the end of your turn to
      // the agent's first sound.
      if (msg.total_latency !== undefined) {
        debug('system', `Agent speaking (latency: ${msg.total_latency.toFixed(2)}s)`);
      }
      break;

    case 'AgentAudioDone':
      debug('system', 'Agent finished speaking');
      break;

    case 'FunctionCall': {
      // server.py already ran the function (in todos.py) and answered
      // Deepgram. This is the story of what happened.
      debug('function', `Agent is calling ${msg.name}(${msg.arguments})`);
      const result = msg.result || '';
      debug('function', `Result: ${result.substring(0, 100)}${result.length > 100 ? '...' : ''}`);
      break;
    }

    case 'TodoList':
      if (onTodoList) onTodoList(msg.items);
      break;

    case 'Log':
      debug(msg.tag || 'system', msg.text);
      break;

    case 'PromptUpdated':
      debug('system', 'Prompt updated — new personality is live');
      break;

    case 'SpeakUpdated':
      debug('system', 'Voice updated');
      break;

    case 'ThinkUpdated':
      debug('system', 'Think provider updated');
      break;

    case 'InjectionRefused':
      debug('system', `Injection refused: ${msg.message || ''}`);
      break;

    case 'Error':
      debug('error', `Error: ${msg.description || msg.message || JSON.stringify(msg)}`);
      break;

    case 'Warning':
      debug('error', `Warning: ${msg.description || msg.message || JSON.stringify(msg)}`);
      break;

    case 'History':
    case 'FunctionCallResponse':
    case 'AgentThinking':
    case 'AgentStartedSpeaking':
      // Bookkeeping echoes from the API — safe to ignore
      break;

    default:
      debug('system', `Unknown message: ${msg.type}`);
  }
}
