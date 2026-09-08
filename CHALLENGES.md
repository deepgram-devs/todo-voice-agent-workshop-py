# Challenges — worked solutions (Python)

This branch solves every challenge on the workshop guide's
[Challenges page](https://workshops.deepgram.com/todo-voice-agent/challenges).
You're meant to arrive here *after* a genuine attempt — the page keeps its
hints at the bottom and this branch one step further away, on purpose. If
you've had your go, welcome. Each section below says what changed, where,
and why it's shaped the way it is.

**In a hurry?** Jump to [Just need it working? Paste-ready outs](#just-need-it-working-paste-ready-outs)
at the bottom — a 20-second version and a 2-minute version.

Run this branch the same way as any other:

```bash
git checkout challenges
uv run server.py
```

Search the code for `CHALLENGE` to find every change.

---

## "The third one" — positions, not just words

**Where:** `todos.py` — `ORDINALS`, `position_from`, the top of `find_todo`,
and the `item` parameter descriptions.

`list_items` already numbers the list from 1, so "the third one" is a
perfectly natural thing to say. The fix has two halves, and the second is
the one people forget:

1. **Resolve the position in your code.** `position_from` looks for a digit
   (`"number 2"`) or an ordinal word (`"third"`) and `find_todo` tries that
   *before* matching text. Out-of-range positions fall through to the text
   match, so "the 2019 one" still finds the free trial.
2. **Tell the model to pass the words through.** The `item` parameter
   description now says a position is acceptable and asks the model *not*
   to resolve it. Without that, the LLM sometimes helpfully substitutes the
   item's text — which usually works, but you've lost control of it.

**The trap:** the word "one". "The cactus one" does not mean position 1, so
"one" is deliberately absent from `ORDINALS`. If you added number words
(one, two, three…) and everything started pointing at the cactus, that's
why.

## "Undo that" — a function that reverses another one

**Where:** `todos.py` — `_last_deleted`, the end of `delete_item`,
`undo_delete`, plus a dispatch entry and a definition.

`delete_item` already had the removed item in a variable for one line; the
whole trick is keeping it — and its `index` — in module-level state that
outlives the call. `undo_delete` then uses `list.insert` to put it back
where it was, and clears `_last_deleted` so a second undo gets a sentence
instead of a duplicate.

Two small choices worth noticing: `delete_item`'s confirmation now *mentions*
undo ("Say undo if that was a mistake"), which is how users learn the
feature exists in a voice UI with no visible buttons; and the new function
has no parameters — the description alone ("undo", "bring that back",
"deleted by mistake") is what makes the model reach for it.

## "Milk, eggs, and bread" — one round trip instead of three

**Where:** `todos.py` — `add_item`, `spoken_list`, and `add_item`'s
definition (and its line in `FUNCTION_HANDLERS`).

Before the change, gpt-4o-mini called `add_item` three times for "add milk,
eggs, and bread" — three `FunctionCallRequest`s, three waits. The fix is a
schema change: an `items` parameter of `"type": "array"`, and a description
that says *when* to use it ("if they name several tasks in one breath, send
them all in a single call"). Tested against the live API: the same sentence
now produces exactly one request with `{"items":["milk","eggs","bread"]}`,
and "add call the plumber" still arrives as a single `text`.

`text` is kept as an optional parameter so the old shape keeps working —
worth doing whenever you change a function's contract. `spoken_list` exists
because the return value is spoken: `"milk", "eggs" and "bread"` reads
aloud; `['milk', 'eggs', 'bread']` does not.

## "Are you sure?" — a feature that lives entirely in the prompt

**Where:** `agent.py` — one rule in `AGENT_PROMPT`.

```
- Deleting is permanent. When the user asks to delete something, do NOT call
  delete_item yet. Ask them to confirm, naming the item. Call delete_item only
  after they have clearly said yes. If they say no, never mind, or change the
  subject, leave the list alone and say so.
```

No Python logic changed. Tested live: "delete the cactus one" gets a
question and no `FunctionCallRequest`; "never mind" leaves the list alone;
"delete the staple gun one" → "yes, I'm sure" fires the call. The wording
matters — "confirm before deleting" on its own is read loosely by smaller
models. Say precisely *when* the function may be called and what to do on a
no. If your model still deletes immediately, make the rule more absolute,
not longer.

## "Make it remember" — two moments in a file's life

**Where:** `todos.py` — `DEFAULT_TODOS`, `STORAGE_FILE`, `load_todos`, the
`todos` and `_next_id` lines, `notify_change`, and `reset_list`.

In the browser version this challenge uses `localStorage`; in Python the
natural home is a file next to the code, `todos.json`. Persistence is two
lines in the right places: **save** inside `notify_change()` (every change
already goes through it) and **load** once, at import time, falling back to
the defaults. Both are wrapped in `try` because a read-only folder or a
half-written file should degrade to "works but forgets", not crash.

The detail that bites: `_next_id`. If it restarts at 8 after a restart, new
items collide with saved ones and the on-screen checkboxes start toggling the
wrong rows. It's now derived from the loaded list. And `reset_list` gives the
agent — and therefore the user — a spoken way back to the original seven,
so nobody has to delete `todos.json` by hand. (`todos.json` is in
`.gitignore`, so your list never ends up in a commit.)

## "Cover the dead air" — filler while a function is slow

**Where:** `todos.py` — `delete_item` is `async` with a commented-out fake
delay; `agent.py` — `_handle_function_calls` and `_filler_after`.

To make it bad on purpose, uncomment the `await asyncio.sleep(3)` at the top
of `delete_item`. Then two discoveries, in the order you'd make them:

1. **A handler can be a coroutine.** `_handle_function_calls` already
   checks `inspect.isawaitable(result)` and awaits it, so an `async def`
   handler just works — the agent waits for the real answer. That alone is
   correct; the silence remains.
2. **`InjectAgentMessage` fills the silence.** The
   [docs](https://developers.deepgram.com/docs/voice-agent-inject-agent-message)
   describe three `behavior` values. `default` is refused whenever a turn is
   in progress (it is — the agent is mid-turn waiting on you). `interrupt`
   would step on any narration the model already produced. `queue` is built
   for exactly this case: it speaks after whatever is already queued, and is
   never refused mid-turn. Tested live: the filler arrives as agent
   `ConversationText` before the function's result, gets spoken, and then
   the real confirmation follows.

The refinement in this branch: the filler is a task scheduled **400 ms**
out (`_filler_after`) that the handler's completion cancels, so fast
functions (all of ours, normally) never trigger it and you don't hear "one
second" before every single add. The simplest version — send the filler
unconditionally as the request arrives — is a fine first pass; this is where
you'd go next.

---

## Break it on purpose

No solutions — these were observations. If you left one broken: the
`UserStartedSpeaking` case in `public/js/agent.js` should stop playback;
handlers should return strings; the last line of `AGENT_PROMPT` bans
markdown; and `eot_threshold` defaults to `0.7`.

## A bug you may have found on the way

If "delete the staple gun one" ever deleted the *cactus*, you found a real
bug in the original matcher: it treated "the" as a meaningful word, and
"the" appears in most items — so the first of them won. `find_todo` ignores
filler words and picks the item sharing the *most* meaningful words with
what was said. The same fix is on the `start` and `complete` branches.

---

# Just need it working? Paste-ready outs

Two speeds. Both assume you did the guide's **Save your progress first** step
(a commit, or copies of `todos.py` and `agent.py`), so nothing you built is
at risk.

## The 20-second out: switch to this branch

Everything on this page solved at once, no pasting:

```bash
git checkout challenges
```

Restart the server and reconnect. To go back to your own code afterwards:

```bash
git checkout -
```

(No git — you downloaded the ZIP? Download this branch the same way:
<https://github.com/deepgram-devs/todo-voice-agent-workshop-py/archive/refs/heads/challenges.zip>,
unzip it next to your folder, and run `uv sync` and `uv run server.py` in it.)

## The 2-minute out: paste one challenge

Each block below is self-contained — it applies to the `complete` branch
code (your code after Module 3) without needing any other challenge. Paste,
save, restart the server, reconnect. Every block was applied on its own to a
fresh copy of `complete` and checked before it was written here.

### "The third one"

Paste this **above** `find_todo` in `todos.py`:

```python
ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}


def position_from(item_text):
    lower = item_text.lower()
    digits = re.search(r"\b(\d+)\b", lower)
    if digits:
        return int(digits.group(1))
    for word in re.split(r"\W+", lower):
        if word in ORDINALS:
            return ORDINALS[word]
    return None
```

Make these the **first lines after the empty check** inside `find_todo`
(right after `return None`):

```python
    position = position_from(lower)
    if position and 0 < position <= len(todos):
        return todos[position - 1]
```

Then, in `FUNCTION_DEFINITIONS`, replace the `item` description for
`complete_item` with:

```python
                    "description": 'Words from the task to mark done (e.g. "the cactus one"), or its position as the list was read back (e.g. "the third one", "number 2"). Pass the user\'s words through; do not resolve the position yourself.',
```

and for `delete_item` with:

```python
                    "description": 'Words from the task to delete (e.g. "the staple gun one"), or its position as the list was read back (e.g. "the third one", "number 2"). Pass the user\'s words through; do not resolve the position yourself.',
```

Say: *"mark the third one done"*.

### "Undo that"

In `todos.py`, **replace the whole `delete_item` function** with this (it
adds the `_last_deleted` variable and the new `undo_delete` function too):

```python
_last_deleted = None


def delete_item(item):
    global _last_deleted
    todo = find_todo(item)
    if todo is None:
        return f"I couldn't find anything matching \"{item}\" to delete."
    index = todos.index(todo)
    todos.remove(todo)
    _last_deleted = {"todo": todo, "index": index}
    notify_change()
    return f'Deleted "{todo["text"]}". Say undo if that was a mistake.'


def undo_delete():
    global _last_deleted
    if _last_deleted is None:
        return "There's nothing to undo — nothing has been deleted recently."
    todo, index = _last_deleted["todo"], _last_deleted["index"]
    todos.insert(min(index, len(todos)), todo)
    _last_deleted = None
    notify_change()
    return f'Brought back "{todo["text"]}". It\'s like it never left.'
```

Add this line to `FUNCTION_HANDLERS`, after the `delete_item` entry:

```python
    "undo_delete": lambda args: undo_delete(),
```

Add this entry at the end of `FUNCTION_DEFINITIONS` (before the closing `]`):

```python
    {
        "name": "undo_delete",
        "description": "Restores the most recently deleted item to where it was. Call this when the user says undo, bring that back, or that they deleted something by mistake.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
```

Say: *"delete the staple gun one"* … *"undo that"*.

### "Milk, eggs, and bread"

In `todos.py`, **replace the whole `add_item` function** with (the helper
comes along):

```python
def spoken_list(tasks):
    """Turn ["milk", "eggs", "bread"] into: "milk", "eggs" and "bread"."""
    quoted = [f'"{t}"' for t in tasks]
    if len(quoted) == 1:
        return quoted[0]
    return f"{', '.join(quoted[:-1])} and {quoted[-1]}"


def add_item(items=None, text=None):
    global _next_id
    tasks = [t for t in (items if items is not None else ([text] if text else [])) if t]
    if not tasks:
        return "I didn't catch what to add. Could you say it again?"
    for task in tasks:
        todos.append({"id": _next_id, "text": task, "done": False})
        _next_id += 1
    notify_change()
    return f"Added {spoken_list(tasks)}. The list now has {len(todos)} items."
```

Change the `add_item` line in `FUNCTION_HANDLERS` to:

```python
    "add_item": lambda args: add_item(items=args.get("items"), text=args.get("text")),
```

Then **replace the whole `add_item` entry** in `FUNCTION_DEFINITIONS` with:

```python
    {
        "name": "add_item",
        "description": "Adds one or more items to the to-do list. Call this when the user wants to add, remember, or note down tasks. If they name several tasks in one breath, send them all in a single call.",
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": 'The tasks to add, each as a short phrase (e.g. ["buy oat milk", "call the plumber"])',
                },
                "text": {
                    "type": "string",
                    "description": "A single task to add. Prefer items.",
                },
            },
            "required": [],
        },
    },
```

Say: *"add milk, eggs, and bread"* and count the function-call lines.

### "Are you sure?"

In `agent.py`, inside `AGENT_PROMPT`, replace the line

```
- When they want something gone, call delete_item.
```

with

```
- Deleting is permanent. When the user asks to delete something, do NOT call delete_item yet. Ask them to confirm, naming the item. Call delete_item only after they have clearly said yes. If they say no, never mind, or change the subject, leave the list alone and say so.
```

No Python logic changes. Say: *"delete the cactus one"*, then *"never mind"*.

### "Make it remember"

Four edits in `todos.py`, top to bottom.

1. Add to the imports at the top:

   ```python
   import copy
   import json
   from pathlib import Path
   ```

2. Change `todos = [` (the line above the seven items) to:

   ```python
   DEFAULT_TODOS = [
   ```

3. Replace the line `_next_id = 8` with:

   ```python
   STORAGE_FILE = Path(__file__).parent / "todos.json"


   def load_todos():
       try:
           return json.loads(STORAGE_FILE.read_text())
       except (OSError, ValueError):
           return copy.deepcopy(DEFAULT_TODOS)


   todos = load_todos()

   # _next_id has to survive a restart too, or new items collide with old ones.
   _next_id = max((t["id"] for t in todos), default=0) + 1
   ```

4. Replace the whole `notify_change` function with:

   ```python
   def notify_change():
       try:
           STORAGE_FILE.write_text(json.dumps(todos, indent=2, ensure_ascii=False))
       except OSError:
           pass  # Read-only folder — the list still works, it just won't persist.
       if _on_change:
           _on_change(todos)
   ```

Add something, restart the server, reconnect, ask what's on the list. To get
the original seven back: delete `todos.json` and restart.

### "Cover the dead air"

Two files. First, make it slow on purpose: in `todos.py`, add
`import asyncio` at the top and replace the first line of `delete_item` with
these two:

```python
async def delete_item(item):
    await asyncio.sleep(3)  # pretend this is a slow lookup
```

Then in `agent.py`, add `AgentV1InjectAgentMessage,` to the
`from deepgram.agent.v1.types import (...)` list, and inside
`_handle_function_calls` insert this right after the `args = ...` line:

```python
            # Give the agent something to say while it waits for our answer.
            # "queue" = after whatever it is already saying, and never refused mid-turn.
            await self._agent.send_inject_agent_message(
                AgentV1InjectAgentMessage(message="One second, let me find that.", behavior="queue")
            )
```

The rest of the function stays as it is — it already awaits an `async`
handler. Say: *"delete the cactus one"*. You'll hear "One second, let me find
that", three seconds of nothing, then the confirmation. (The solved branch
refines this with a timer so the filler only fires when a function is
actually slow — see the section above.)
