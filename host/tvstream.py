"""Stream a file to the TV through one telnet session into a single `base64 -d`, with echo off.

tvput.py forks a printf per 800 bytes (~3 MB/min); here the shell runs once and only the pty limits speed.
usage: tvstream.py <tv ip> <local file> <remote path>
"""
import base64
import hashlib
import socket
import sys
import time

ip, local, remote = sys.argv[1:4]
raw = open(local, "rb").read()
b64 = base64.encodebytes(raw)  # 76-char lines, well under the pty's 4096-byte line limit
sock = socket.create_connection((ip, 23), timeout=120)


def drain(wait=0.0):
    sock.settimeout(wait)
    try:
        while sock.recv(1 << 20):
            pass
    except (socket.timeout, BlockingIOError):
        pass
    sock.settimeout(120)


time.sleep(1)
drain(0.5)
sock.sendall(f"stty -echo; base64 -d > {remote}\n".encode())
time.sleep(0.5)
drain(0.2)
step = 64 * 1024
t0 = time.time()
for i in range(0, len(b64), step):
    sock.sendall(b64[i:i + step])
    drain(0)
    if i % (step * 80) == 0:
        print(f"{i * 100 // len(b64)}% {i / (time.time() - t0 + 1e-9) / 1e6:.2f} MB/s", flush=True)
sock.sendall(b"\n\x04")
time.sleep(3)
sock.sendall(f"stty echo; md5sum {remote}\n".encode())
time.sleep(5)
sock.settimeout(5)
out = b""
try:
    while True:
        chunk = sock.recv(1 << 16)
        if not chunk:
            break
        out += chunk
except socket.timeout:
    pass
want = hashlib.md5(raw).hexdigest()
print("md5 ok" if want.encode() in out else f"md5 MISMATCH, want {want}: {out[-300:]!r}")
