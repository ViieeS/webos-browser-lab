"""Minimal Web Inspector client for the TV's WebKit (WEBKIT_INSPECTOR_HTTP_SERVER): stdlib-only
WebSocket plus the Target.sendMessageToTarget envelope the page proxy expects."""
import base64
import json
import os
import re
import socket
import struct
import time
import urllib.request


class WebSocket:
    """Just enough RFC 6455 for one client connection: text frames, masking, fragmentation."""

    def __init__(self, hostport, path):
        host, port = hostport.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=60)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += self.sock.recv(1)
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise SystemExit(f"handshake failed: {head[:200]!r}")
        self.buf = b""

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(1 << 16)
            if not chunk:
                raise EOFError
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text):
        data = text.encode()
        mask = os.urandom(4)
        n = len(data)
        head = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else
                                bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536 else
                                bytes([0x80 | 127]) + struct.pack(">Q", n))
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self):
        parts = []
        while True:
            b0, b1 = self._read(2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            opcode = b0 & 0x0F
            if opcode == 8:
                raise EOFError
            if opcode in (9, 10):
                continue
            parts.append(payload)
            if b0 & 0x80:
                return b"".join(parts).decode("utf-8", "replace")



class Inspector:
    """One connection to the first inspectable page. send() wraps a page command; follow() switches
    to a new page target after a cross-site navigation."""

    def __init__(self, hostport):
        page = urllib.request.urlopen(f"http://{hostport}/", timeout=10).read().decode()
        path = re.search(r"ws=' \+ window.location.host \+ '([^']+)'", page).group(1)
        self.ws = WebSocket(hostport, path)
        self.target = None
        self.next_id = 100
        deadline = time.time() + 10
        while self.target is None and time.time() < deadline:
            m = json.loads(self.ws.recv())
            if m.get("method") == "Target.targetCreated":
                self.target = m["params"]["targetInfo"]["targetId"]
        if not self.target:
            raise SystemExit("no page target")

    def send(self, method, params=None):
        self.next_id += 1
        msg = json.dumps({"id": self.next_id, "method": method, "params": params or {}})
        self.ws.send(json.dumps({"id": self.next_id, "method": "Target.sendMessageToTarget",
                                 "params": {"targetId": self.target, "message": msg}}))
        return self.next_id

    def messages(self, until):
        """Page messages (decoded) until the deadline; follows new page targets on the way."""
        self.ws.sock.settimeout(1)
        while time.time() < until:
            try:
                m = json.loads(self.ws.recv())
            except socket.timeout:
                continue
            if m.get("method") == "Target.targetCreated":
                self.target = m["params"]["targetInfo"]["targetId"]
                yield {"method": "_newTarget"}
            elif m.get("method") == "Target.dispatchMessageFromTarget":
                yield json.loads(m["params"]["message"])
