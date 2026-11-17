"""Copy a file from the TV through one telnet session: the TV prints it as base64 between markers.

The reverse of tvstream.py, for core dumps and logs; no listening socket is needed on either side.
usage: tvfetch.py <tv ip> <remote path> <local file>
"""
import base64
import hashlib
import socket
import sys
import time

ip, remote, local = sys.argv[1:4]
sock = socket.create_connection((ip, 23), timeout=120)
time.sleep(1)
sock.settimeout(0.5)
try:
    while sock.recv(1 << 20):
        pass
except socket.timeout:
    pass
sock.settimeout(120)
# The markers are built by the shell, so the echoed command line cannot match them.
sock.sendall(f"stty -echo; M=FETCH; md5sum {remote}; echo $M-BEGIN; base64 {remote}; echo $M-END\n".encode())
buf = bytearray()
t0 = time.time()
while b"FETCH-END" not in buf[-200:]:
    chunk = sock.recv(1 << 20)
    if not chunk:
        sys.exit("connection closed before FETCH-END")
    buf += chunk
    if len(buf) % (8 << 20) < len(chunk):
        print(f"{len(buf) / 1e6:.0f} MB {len(buf) / (time.time() - t0) / 1e6:.2f} MB/s", flush=True)
text = bytes(buf).replace(b"\r", b"")
head, body = text.split(b"FETCH-BEGIN\n", 1)
body = body.split(b"FETCH-END", 1)[0]
raw = base64.b64decode(body)
open(local, "wb").write(raw)
got = hashlib.md5(raw).hexdigest()
print("md5 ok" if got.encode() in head else f"md5 MISMATCH {got}: {head[-200:]!r}")
