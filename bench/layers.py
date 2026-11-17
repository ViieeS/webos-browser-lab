#!/usr/bin/env python3
"""Lists the composited layers of the inspected page (Web Inspector LayerTree) with their nodes and
compositing reasons: tells whether an element scrolls as its own layer or is repainted with the page.
usage: layers.py [css selector to mark, default .vector-sticky-pinned-container] [tv ip:port, default $TV_HOST:9222]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inspector import Inspector  # noqa: E402

selector = sys.argv[1] if len(sys.argv) > 1 else ".vector-sticky-pinned-container"
insp = Inspector(sys.argv[2] if len(sys.argv) > 2 else os.environ["TV_HOST"] + ":9222")


def call(method, params=None):
    ask = insp.send(method, params)
    for msg in insp.messages(time.time() + 20):
        if msg.get("id") == ask:
            if "error" in msg:
                raise SystemExit(f"{method}: {msg['error']}")
            return msg.get("result", {})
    raise SystemExit(f"{method}: no reply")


root = call("DOM.getDocument")["root"]["nodeId"]
marked = set(call("DOM.querySelectorAll", {"nodeId": root, "selector": selector})["nodeIds"])
call("LayerTree.enable")
layers = call("LayerTree.layersForNode", {"nodeId": root})["layers"]
print(f"{len(layers)} composited layers; {len(marked)} nodes match {selector}")
for layer in layers:
    reasons = call("LayerTree.reasonsForCompositingLayer", {"layerId": layer["layerId"]}).get("compositingReasons", {})
    why = ",".join(k for k, v in reasons.items() if v)
    mark = "*" if layer.get("nodeId") in marked else " "
    print(f"{mark} {layer.get('name', '')[:50]:50} {int(layer['bounds']['width'])}x{int(layer['bounds']['height'])} "
          f"paints={layer.get('paintCount')} {why}")
