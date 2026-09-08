"""Your to-do list — the data, and the functions the agent can call.

THIS IS THE `challenges` BRANCH: every challenge from the guide's
Challenges page is solved here, and CHALLENGES.md in the repo root walks
through each one. Look for the CHALLENGE markers below.

The agent doesn't touch this list directly. When you say "add milk", the
agent decides to call add_item(items=["buy milk"]), Deepgram sends that
request over the WebSocket, and the code in this file runs — right here in
your Python process. Whatever string these functions return is what the
agent gets back, and what it uses to answer you out loud.
"""

import asyncio
import copy
import json
import re
from pathlib import Path

# The list starts with a few items so there's something to talk about.
DEFAULT_TODOS = [
    {"id": 1, "text": "Water the cactus — it has been eight months", "done": False},
    {"id": 2, "text": "Return the minotaur's staple gun", "done": False},
    {"id": 3, "text": "Rename all my variables from 'thing2' to something responsible", "done": False},
    {"id": 4, "text": "Cancel the free trial from 2019", "done": False},
    {"id": 5, "text": "Back up the laptop before it senses fear", "done": False},
    {"id": 6, "text": "Finally read the terms and conditions", "done": False},
    {"id": 7, "text": "Teach my to-do list to listen", "done": False},
]

# CHALLENGE "Make it remember": load from todos.json if there's a saved
# list, otherwise start from the defaults. Saving happens in notify_change().
STORAGE_FILE = Path(__file__).parent / "todos.json"


def load_todos():
    try:
        return json.loads(STORAGE_FILE.read_text())
    except (OSError, ValueError):
        # No file yet, or a corrupt one. Fall through to the defaults.
        return copy.deepcopy(DEFAULT_TODOS)


todos = load_todos()

# _next_id has to survive a restart too, or new items collide with old ones.
_next_id = max((t["id"] for t in todos), default=0) + 1

# The server registers a callback here so the on-screen list re-renders
# whenever a function changes the data.
_on_change = None


def set_on_change(callback):
    global _on_change
    _on_change = callback


def notify_change():
    try:
        STORAGE_FILE.write_text(json.dumps(todos, indent=2, ensure_ascii=False))
    except OSError:
        pass  # Read-only folder — the list still works, it just won't persist.
    if _on_change:
        _on_change(todos)


# CHALLENGE "The third one": list_items numbers the list from 1, so people
# say "the third one" or "number 2". Turn that into a position when we can.
# Deliberately NOT in this table: "one" — "the cactus one" isn't position 1.
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


# Words that appear in almost every item and mean nothing on their own.
# Without this set, "the staple gun one" matches "Water THE cactus" first.
FILLER_WORDS = {"the", "one", "and", "that", "this", "item", "task", "thing", "from", "with"}


def find_todo(item_text):
    """Find a to-do whose text loosely matches what the agent heard.

    "the cactus one" should match "Water the cactus — it has been eight months".
    "the third one" should match whatever is third right now.
    Returns None when nothing matches.
    """
    lower = str(item_text or "").lower().strip()
    if not lower:
        return None  # nothing to match — never fall through to "the first item"

    position = position_from(lower)
    if position and 0 < position <= len(todos):
        return todos[position - 1]

    for todo in todos:
        if lower in todo["text"].lower():
            return todo

    # Otherwise: the item sharing the most meaningful words with what was said.
    words = [w for w in re.split(r"\W+", lower) if len(w) > 2 and w not in FILLER_WORDS]
    best = None
    best_score = 0
    for todo in todos:
        text = todo["text"].lower()
        score = sum(1 for w in words if w in text)
        if score > best_score:
            best = todo
            best_score = score
    return best


def spoken_list(tasks):
    """Turn ["milk", "eggs", "bread"] into: "milk", "eggs" and "bread"."""
    quoted = [f'"{t}"' for t in tasks]
    if len(quoted) == 1:
        return quoted[0]
    return f"{', '.join(quoted[:-1])} and {quoted[-1]}"


# --- The functions the agent can call ---
# Each one returns a plain sentence (not JSON, not markdown) because the
# agent reads the result and speaks — nobody wants to hear "curly brace".


# CHALLENGE "Milk, eggs, and bread": one call can now carry several tasks.
# `text` is still accepted so the old single-item shape keeps working.
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


def list_items():
    if not todos:
        return "The list is empty. Suspiciously empty."
    lines = [f"{i + 1}. {t['text']}{' (done)' if t['done'] else ''}" for i, t in enumerate(todos)]
    done_count = sum(1 for t in todos if t["done"])
    return f"There are {len(todos)} items, {done_count} done. {'. '.join(lines)}"


def complete_item(item):
    todo = find_todo(item)
    if todo is None:
        return f"I couldn't find anything matching \"{item}\" on the list."
    todo["done"] = True
    notify_change()
    return f'Marked "{todo["text"]}" as done. Nice.'


# CHALLENGE "Undo that": remember what we deleted, and where it was.
_last_deleted = None


# CHALLENGE "Cover the dead air": this function is `async` so it CAN be
# slow. Uncomment the sleep below to fake a three-second database lookup,
# then listen for the filler agent.py sends while it waits.
async def delete_item(item):
    global _last_deleted
    # await asyncio.sleep(3)  # pretend lookup

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


# CHALLENGE "Make it remember", the reset: hand the agent a way back to the
# original seven, so nobody has to go delete todos.json by hand.
def reset_list():
    global _next_id, _last_deleted
    todos.clear()
    todos.extend(copy.deepcopy(DEFAULT_TODOS))
    _next_id = 8
    _last_deleted = None
    notify_change()
    return "Reset the list to the original seven items. The cactus is thirsty again."


# --- Dispatch map: function name → handler ---
# When Deepgram sends a FunctionCallRequest, agent.py looks up the
# function's name here and calls the handler with the parsed arguments
# (a dict built from the JSON the model produced).
FUNCTION_HANDLERS = {
    "add_item": lambda args: add_item(items=args.get("items"), text=args.get("text")),
    "list_items": lambda args: list_items(),
    "complete_item": lambda args: complete_item(args.get("item", "")),
    "delete_item": lambda args: delete_item(args.get("item", "")),
    "undo_delete": lambda args: undo_delete(),
    "reset_list": lambda args: reset_list(),
}

# --- Function definitions: what the agent is told it can do ---
# These descriptions are read by the LLM, not by users. The clearer the
# description, the better the agent picks the right function.
FUNCTION_DEFINITIONS = [
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
    {
        "name": "list_items",
        "description": "Reads back the full to-do list, numbered. Call this when the user asks what is on the list, what is left, or what they have to do.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "complete_item",
        "description": "Marks an item on the to-do list as done. Call this when the user says they finished, completed, or did a task.",
        "parameters": {
            "type": "object",
            "properties": {
                "item": {
                    "type": "string",
                    "description": 'Words from the task to mark done (e.g. "the cactus one"), or its position as the list was read back (e.g. "the third one", "number 2"). Pass the user\'s words through; do not resolve the position yourself.',
                }
            },
            "required": ["item"],
        },
    },
    {
        "name": "delete_item",
        "description": "Removes an item from the to-do list entirely. Call this when the user wants to delete, remove, or forget a task.",
        "parameters": {
            "type": "object",
            "properties": {
                "item": {
                    "type": "string",
                    "description": 'Words from the task to delete (e.g. "the staple gun one"), or its position as the list was read back (e.g. "the third one", "number 2"). Pass the user\'s words through; do not resolve the position yourself.',
                }
            },
            "required": ["item"],
        },
    },
    {
        "name": "undo_delete",
        "description": "Restores the most recently deleted item to where it was. Call this when the user says undo, bring that back, or that they deleted something by mistake.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "reset_list",
        "description": "Throws away the current list and restores the original example items. Call this only when the user explicitly asks to reset or start over.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
]
