"""Your to-do list — the data, and the four functions the agent can call.

THIS IS THE FILE YOU WILL EDIT DURING THE WORKSHOP.

The agent doesn't touch this list directly. When you say "add milk", the
agent decides to call add_item(text="buy milk"), Deepgram sends that
request over the WebSocket, and the code in this file runs — right here in
your Python process. Whatever string these functions return is what the
agent gets back, and what it uses to answer you out loud.
"""

import re

# The list starts with a few items so there's something to talk about.
todos = [
    {"id": 1, "text": "Water the cactus — it has been eight months", "done": False},
    {"id": 2, "text": "Return the minotaur's staple gun", "done": False},
    {"id": 3, "text": "Rename all my variables from 'thing2' to something responsible", "done": False},
    {"id": 4, "text": "Cancel the free trial from 2019", "done": False},
    {"id": 5, "text": "Back up the laptop before it senses fear", "done": False},
    {"id": 6, "text": "Finally read the terms and conditions", "done": False},
    {"id": 7, "text": "Teach my to-do list to listen", "done": False},
]

_next_id = 8

# The server registers a callback here so the on-screen list re-renders
# whenever a function changes the data.
_on_change = None


def set_on_change(callback):
    global _on_change
    _on_change = callback


def notify_change():
    if _on_change:
        _on_change(todos)


# Words that appear in almost every item and mean nothing on their own.
# Without this set, "the staple gun one" matches "Water THE cactus" first.
FILLER_WORDS = {"the", "one", "and", "that", "this", "item", "task", "thing", "from", "with"}


def find_todo(item_text):
    """Find a to-do whose text loosely matches what the agent heard.

    "the cactus one" should match "Water the cactus — it has been eight months".
    Returns None when nothing matches.
    """
    lower = str(item_text or "").lower().strip()
    if not lower:
        return None  # nothing to match — never fall through to "the first item"
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


# --- The four functions the agent can call ---
# Each one returns a plain sentence (not JSON, not markdown) because the
# agent reads the result and speaks — nobody wants to hear "curly brace".


def add_item(text):
    global _next_id
    todos.append({"id": _next_id, "text": text, "done": False})
    _next_id += 1
    notify_change()
    return f'Added "{text}". The list now has {len(todos)} items.'


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


def delete_item(item):
    todo = find_todo(item)
    if todo is None:
        return f"I couldn't find anything matching \"{item}\" to delete."
    todos.remove(todo)
    notify_change()
    return f'Deleted "{todo["text"]}". It\'s like it never existed.'


# --- Dispatch map: function name → handler ---
# When Deepgram sends a FunctionCallRequest, agent.py looks up the
# function's name here and calls the handler with the parsed arguments
# (a dict built from the JSON the model produced).
FUNCTION_HANDLERS = {
    "add_item": lambda args: add_item(args.get("text", "")),
    "list_items": lambda args: list_items(),
    "complete_item": lambda args: complete_item(args.get("item", "")),
    "delete_item": lambda args: delete_item(args.get("item", "")),
}

# --- Function definitions: what the agent is told it can do ---
# These descriptions are read by the LLM, not by users. The clearer the
# description, the better the agent picks the right function.
FUNCTION_DEFINITIONS = [
    {
        "name": "add_item",
        "description": "Adds a new item to the to-do list. Call this when the user wants to add, remember, or note down a task.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": 'The task to add, as a short phrase (e.g. "buy oat milk")',
                }
            },
            "required": ["text"],
        },
    },
    {
        "name": "list_items",
        "description": "Reads back the full to-do list. Call this when the user asks what is on the list, what is left, or what they have to do.",
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
                    "description": 'Words from the task to mark done (e.g. "the cactus one" or "water the cactus")',
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
                    "description": 'Words from the task to delete (e.g. "the staple gun one")',
                }
            },
            "required": ["item"],
        },
    },
]
