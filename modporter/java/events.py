# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Module 3c - Event transformer.

Converts Fabric API callback registrations into Forge/NeoForge
``@SubscribeEvent`` methods, and event-bus methods back into Fabric callbacks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .editor import JavaSourceEditor
from .scanner import strip_comments_and_strings

# ---------------------------------------------------------------------------
# Fabric callback -> @SubscribeEvent mapping table
# ---------------------------------------------------------------------------

FABRIC_EVENT_MAP = {
    # fabric callback (imports + registration) -> forge/neo event class
    "net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents$ServerStarted": "net.neoforged.neoforge.event.server.ServerStartedEvent",
    "net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents$ServerStopping": "net.neoforged.neoforked.neoforge.event.server.ServerStoppingEvent",
    "net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents$StartServerTick": "net.neoforged.neoforge.event.TickEvent$ServerTickEvent",
    "net.fabricmc.fadvise_placeholder": "",
}


@dataclass
class _Callback:
    """A discovered Fabric callback registration."""

    var: str  # local variable name (often unused)
    listener_name: str  # e.g. ServerTickEvents.END_SERVER_TICK
    event_field: str  # e.g. END_SERVER_TICK
    body_lines: list[str]
    line_start: int
    line_end: int
    lambda_style: str  # "lambda" | "anonymous"
    param: str  # e.g. "server"


def convert_fabric_callbacks_to_subscribe(
    editor: JavaSourceEditor,
    notes: list[str],
    target_engine: str,
) -> None:
    """Rewrite Fabric event callbacks into @SubscribeEvent methods."""
    text = "\n".join(editor.lines)
    code = strip_comments_and_strings(text)
    # Fabric API style: EVENT_HOLDER.FIELD.register(param -> { ... })
    cb_re = re.compile(
        r"([\w.$]+)\.register\s*\(\s*(\w+)\s*->\s*\{"
    )
    results: list[_Callback] = []
    for m in cb_re.finditer(code):
        holder, param = m.group(1), m.group(2)
        # find body via brace balance from the '{' at end of match
        open_brace = code.index("{", m.end() - 1)
        depth = 0
        end = None
        for k in range(open_brace, len(code)):
            ch = code[k]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = k
                    break
        if end is None:
            continue
        # slice from RAW text (strip preserves offsets) so literals survive
        body_text = text[open_brace + 1:end]
        line_start = code[:m.start()].count("\n")
        line_end = code[:end].count("\n")
        cb = _Callback(
            var="",
            listener_name=holder,  # e.g. ServerTickEvents.END_SERVER_TICK
            event_field=holder.rsplit(".")[-1],  # e.g. END_SERVER_TICK
            body_lines=body_text.splitlines(),
            line_start=line_start,
            line_end=line_end,
            lambda_style="lambda",
            param=param,
        )
        results.append(cb)
    if not results:
        return

    # remove callback blocks (bottom-up) and collect @SubscribeEvent methods
    methods: list[str] = []
    for cb in reversed(results):
        start, end = cb.line_start, cb.line_end
        # attach preceding comment lines
        while start > 0 and editor.lines[start - 1].strip().startswith("//"):
            start -= 1
        methods.append(_make_subscribe_method(cb, target_engine))
        del editor.lines[start:end + 1]

    # append the new methods at class end (before final closing brace)
    last_brace = None
    for i in range(len(editor.lines) - 1, -1, -1):
        if editor.get_line(i).strip() == "}":
            last_brace = i
            break
    if last_brace is None:
        last_brace = len(editor.lines)
    editor.lines[last_brace:last_brace] = list(reversed(methods))

    # imports for the events; also drop the now-unused fabric event imports
    removed_fabric_imports = {
        "net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents",
        "net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents",
        "net.fabricmc.fabric.api.itemgroup.v1.ItemGroupEvents",
    }
    if target_engine == "neoforge":
        editor.add_import("net.neoforged.bus.api.SubscribeEvent")
        used = {cb.event_field for cb in results}
        if any("TICK" in u for u in used):
            editor.add_import("net.neoforged.neoforge.event.TickEvent$ServerTickEvent")
        if any("STARTED" in u for u in used):
            editor.add_import("net.neoforged.neoforge.event.server.ServerStartedEvent")
        if any("STOPPING" in u for u in used):
            editor.add_import("net.neoforged.neoforge.event.server.ServerStoppingEvent")
        if any("STOPPED" in u for u in used):
            editor.add_import("net.neoforged.neoforge.event.server.ServerStoppedEvent")
    else:
        editor.add_import("net.minecraftforge.eventbus.api.SubscribeEvent")
    editor.rewrite_imports({}, removed_fabric_imports)
    notes.append(f"Converted {len(results)} Fabric event callback(s) to @SubscribeEvent methods.")

    for cb in results:
        if cb.event_field not in (
            "START_SERVER_TICK", "END_SERVER_TICK", "SERVER_STARTED", "SERVER_STOPPING", "SERVER_STOPPED",
        ):
            editor.add_warning(0, "CONVERT",
                f"Fabric event {cb.listener_name} has no verified Forge/NeoForge equivalent; "
                "check the event catalog for a matching event class.")


def _make_subscribe_method(cb: _Callback, target_engine: str) -> "str":
    """Emit a @SubscribeEvent method from a captured Fabric callback."""
    field = cb.event_field.upper()
    if "STOPPING" in field:
        param_type = "ServerStoppingEvent"
    elif "STOPPED" in field:
        param_type = "ServerStoppedEvent"
    elif "STARTED" in field:
        param_type = "ServerStartedEvent"
    elif "TICK" in field:
        param_type = "ServerTickEvent"
    else:
        param_type = "ServerStartedEvent"  # conservative default + warning below
    pretty = cb.event_field.title().replace("_", "")
    lines = [""]
    lines.append("    @SubscribeEvent")
    lines.append(f"    public static void on{pretty}({param_type} event) {{")
    lines.append(f"        // ModPorter: converted from {cb.listener_name}")
    lines.append(f"        var {cb.param} = event.getServer();")
    body = JavaSourceEditor.reindent(cb.body_lines, "        ")
    for b in body:
        lines.append(b)
    lines.append("    }")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Forge/NeoForge -> Fabric
# ---------------------------------------------------------------------------

SUBSCRIBE_RE = re.compile(
    r"@\w*SubscribeEvent\b[^{]*?(public|protected|private)?\s*(?:static\s+)?[\w<>\[\],\s]+\s+(\w+)\s*\(([^)]*)\)\s*\{"
)


def convert_subscribe_to_fabric_callbacks(
    editor: JavaSourceEditor,
    notes: list[str],
) -> None:
    """Convert @SubscribeEvent methods into Fabric API callback registrations."""
    text = "\n".join(editor.lines)
    code = strip_comments_and_strings(text)
    results = []
    for m in SUBSCRIBE_RE.finditer(code):
        results.append({
            "name": m.group(2),
            "params": m.group(3).strip(),
            "line_start": code[:m.start()].count("\n"),
        })
    for info in reversed(results):
        # find method block via brace balance
        start = info["line_start"]
        depth = 0
        end = None
        seen = False
        for j in range(start, len(editor.lines)):
            seg = strip_comments_and_strings(editor.get_line(j))
            depth += seg.count("{") - seg.count("}")
            if "{" in seg:
                seen = True
            if seen and depth <= 0:
                end = j
                break
        if end is None:
            continue
        body = editor.lines[start:end + 1]
        sig = next((l for l in body if "(" in l), "")
        event_param = re.search(r"\(\s*(?:final\s+)?([\w.$]+)\s+(\w+)\s*\)", sig)
        etype = event_param.group(1) if event_param else "Object"
        pname = event_param.group(2) if event_param else "event"
        body_lines = body[1:-1]
        fabric_event, callback_field = _neo_to_fabric_event(etype)
        call = [
            f"        {fabric_event.split('$')[0].split('.')[-1]}.{callback_field}.register({pname} -> {{",
        ]
        call.extend("    " + b if b.strip() else "" for b in body_lines)
        call.append("        });")
        del editor.lines[start:end + 1]
        # put the callback registration inside onInitialize (first method) or at class start
        insert_at = _find_method_insert(editor, "onInitialize")
        editor.lines[insert_at:insert_at] = ["        // ModPorter: converted @SubscribeEvent " + info["name"] + "()"] + call
    if results:
        editor.rewrite_imports(
            {},
            {
                "net.neoforged.bus.api.SubscribeEvent",
                "net.minecraftforge.eventbus.api.SubscribeEvent",
                "net.neoforged.fml.common.EventBusSubscriber",
                "net.minecraftforge.fml.common.Mod.EventBusSubscriber",
                "net.neoforged.fml.event.lifecycle.FMLClientSetupEvent",
                "net.neoforged.fml.event.lifecycle.FMLCommonSetupEvent",
            },
        )
        notes.append(f"Converted {len(results)} @SubscribeEvent method(s) into Fabric callback registrations.")


def _neo_to_fabric_event(event_type: str) -> tuple[str, str]:
    simple = event_type.split(".")[-1].split("$")[-1]
    table = {
        "ServerTickEvent": ("net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents", "END_SERVER_TICK"),
        "ServerStartedEvent": ("net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents", "SERVER_STARTED"),
        "ServerStoppingEvent": ("net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents", "SERVER_STOPPING"),
        "ServerStoppedEvent": ("net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents", "SERVER_STOPPED"),
        "LevelTickEvent": ("net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents", "END_WORLD_TICK"),
    }
    return table.get(simple, ("net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents", "END_SERVER_TICK"))


def _find_method_insert(editor: JavaSourceEditor, method_name: str) -> int:
    """Return the line index just after the opening brace of the named method."""
    for i, line in enumerate(editor.lines):
        if re.match(rf"^\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:public|protected|private)?\s*(?:static\s+)?[\w<>\[\]]+\s+{method_name}\s*\(", line):
            for j in range(i, min(i + 4, len(editor.lines))):
                if "{" in editor.get_line(j):
                    return j + 1
    # fallback: first line after class opening
    for i, line in enumerate(editor.lines):
        if re.search(r"\bclass\s+\w+.*\{", line):
            return i + 1
    return len(editor.lines)
