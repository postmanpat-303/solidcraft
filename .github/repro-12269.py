"""Temporary fork-only repro driver for #12269.

Runs the real desktop app under Xvfb with software Vulkan, turns the radial
context menu on, then right-clicks and right-press-holds a solid body under
several navigation presets (the gestures the issue says crash the app).
Prints CRASH REPRODUCED and the app log tail when the process dies.
"""

import json
import os
import socket
import subprocess
import sys
import time

PORT = 7707
TOKEN_FILE = os.path.expanduser(f"~/.local/share/solidcraft/control/{PORT}.token")

app_log = open("app.log", "w")
app = subprocess.Popen(
    ["./target/release/solidcraft", "--sample", "--control", str(PORT)],
    stdout=app_log,
    stderr=subprocess.STDOUT,
)


def alive():
    return app.poll() is None


def crash(where):
    print(f"CRASH REPRODUCED: the app died at {where} (exit {app.poll()})")
    app_log.flush()
    try:
        with open("app.log") as fh:
            print("--- app.log tail ---")
            print(fh.read()[-4000:])
    except OSError:
        pass
    sys.exit(1)


token = None
sock = None
for _ in range(90):
    if not alive():
        crash("startup")
    try:
        with open(TOKEN_FILE) as fh:
            token = fh.read().strip() or None
        if token:
            sock = socket.create_connection(("127.0.0.1", PORT), timeout=10)
            break
    except OSError:
        pass
    time.sleep(2)
if sock is None:
    print("FAIL: the control socket never came up")
    app_log.flush()
    with open("app.log") as fh:
        print(fh.read()[-4000:])
    sys.exit(2)
sock.settimeout(120)
conn = sock.makefile("rw")
first = True


def call(method, params=None):
    global first
    req = {"id": int(time.time() * 1000) % 100000, "method": method, "params": params or {}}
    if first:
        req["token"] = token
        first = False
    conn.write(json.dumps(req) + "\n")
    conn.flush()
    line = conn.readline()
    print(f"> {method} {json.dumps(params)}")
    if not line:
        if not alive():
            crash(method)
        print(f"FAIL: the control connection closed during {method} but the app is still running")
        app_log.flush()
        with open("app.log") as fh:
            print(fh.read()[-4000:])
        sys.exit(2)
    print(f"< {line.strip()[:800]}")
    if not alive():
        crash(method)
    return json.loads(line)


call("engine.execute", {"command": "solid.cylinder", "params": {"diameter": 30, "height": 20}})
call("ui.prefs", {"radial_context_menu": True, "ui_scale": 2.5})
call("ui.camera", {"fit": True})
time.sleep(2)
at = call("ui.at", {"world": [15, 0, 10]}).get("result")
if not isinstance(at, list) or len(at) != 2:
    print(f"FAIL: ui.at did not return a screen point: {at}")
    sys.exit(2)
x, y = at
print(f"body side surface sits at screen point ({x}, {y})")

for preset in ["inventor", "fusion", "blender", "nx"]:
    call("ui.prefs", {"nav": preset, "radial_context_menu": True})
    call("ui.click", {"x": x, "y": y, "button": "right"})
    time.sleep(1)
    if not alive():
        crash(f"still right-click on the body ({preset})")
    call("ui.menu")
    call("ui.menu", {"close": True})
    call("ui.drag", {"x0": x, "y0": y, "x1": x + 3, "y1": y + 3, "button": "right", "hold": 45})
    time.sleep(1)
    if not alive():
        crash(f"right press-hold radial flick on the body ({preset})")
    call("ui.menu")
    call("ui.menu", {"close": True})
    print(f"OK: {preset} survived both gestures")

call("ui.prefs", {"nav": "inventor", "radial_context_menu": True})
call("ui.click", {"x": x, "y": y, "button": "right"})
time.sleep(1)
call("ui.screenshot", {"path": "shot-menu.png"})
call("ui.menu", {"close": True})

if not alive():
    crash("end of script")
print("NOT REPRODUCED: the app survived every gesture")
app_log.flush()
