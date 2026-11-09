"""The browser tools the model can call, as JSON Schemas (Anthropic shape: name, description, input_schema)."""

from __future__ import annotations

from typing import Any

from .browser import ActionResult, Browser


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


REF = {"type": "string", "description": "Element ref from the LATEST snapshot, e.g. e7."}

TOOLS: list[dict[str, Any]] = [
    {"name": "click", "description": "Click a link, button or checkbox.",
     "input_schema": _schema({"ref": REF, "element": {"type": "string", "description": "What you are clicking, in words."}}, ["ref"])},
    {"name": "type", "description": "Type text into a textbox or searchbox. submit=true presses Enter (submits the form).",
     "input_schema": _schema({"ref": REF, "text": {"type": "string"}, "submit": {"type": "boolean"}}, ["ref", "text"])},
    {"name": "select_option", "description": "Choose an option in a dropdown (combobox) by its visible text.",
     "input_schema": _schema({"ref": REF, "option": {"type": "string"}}, ["ref", "option"])},
    {"name": "check", "description": "Tick (checked=true) or untick a checkbox.",
     "input_schema": _schema({"ref": REF, "checked": {"type": "boolean"}}, ["ref"])},
    {"name": "handle_dialog", "description": "Accept or dismiss the open confirmation dialog. Read its text first.",
     "input_schema": _schema({"accept": {"type": "boolean"}}, ["accept"])},
    {"name": "navigate", "description": "Open a URL path on the current site, e.g. /index.html.",
     "input_schema": _schema({"url": {"type": "string"}}, ["url"])},
    {"name": "go_back", "description": "Go back to the previous page.", "input_schema": _schema({}, [])},
    {"name": "finish", "description": "Stop and report to the user: the result, or why the goal is impossible.",
     "input_schema": _schema({"answer": {"type": "string"}}, ["answer"])},
]


def execute(browser: Browser, name: str, args: dict[str, Any]) -> ActionResult:
    """Map a tool call onto a browser action. Bad calls become errors the model can read."""
    actions = {
        "click": lambda: browser.click(args["ref"]),
        "type": lambda: browser.type(args["ref"], args["text"], bool(args.get("submit", False))),
        "select_option": lambda: browser.select_option(args["ref"], args["option"]),
        "check": lambda: browser.check(args["ref"], bool(args.get("checked", True))),
        "handle_dialog": lambda: browser.handle_dialog(bool(args["accept"])),
        "navigate": lambda: browser.navigate(args["url"]),
        "go_back": browser.back,
    }
    if name not in actions:
        return ActionResult(False, f"Unknown tool '{name}'.", browser.snapshot())
    try:
        return actions[name]()
    except KeyError as missing:
        return ActionResult(False, f"Missing argument {missing} for {name}.", browser.snapshot())
