#!/usr/bin/env python3
"""Symbolize a WPEWebProcess core from the TV when gdb cannot unwind (the TV's libc has no unwind info
in our sysroot, and JIT frames have none at all).

Takes pc, lr and every odd stack word that points into libWPEWebKit (thumb return addresses), and
runs addr2line on the unstripped library of the current build. The result is a heuristic backtrace:
stale words from older frames show up too, so read it top down and trust the first coherent run.
usage: corestack.py <core file under browser/build/cores> [stack words, default 3000]
"""
import os
import re
import subprocess
import sys

BUILD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build")
GDB = "/work/buildroot/output/host/bin/arm-webos-linux-gnueabi-gdb"
ADDR2LINE = "/work/buildroot/output/host/bin/arm-webos-linux-gnueabi-addr2line"
LIB = "/work/buildroot/output/build/wpewebkit-2.52.6/lib/libWPEWebKit-2.0.so.1.*"


def container(cmd):
    return subprocess.run(["docker", "run", "--rm", "-v", "wpe-br:/work", "-v", f"{BUILD}:/b", "wpe-br", "sh", "-c", cmd],
                          capture_output=True, text=True).stdout


core = "/b/cores/" + sys.argv[1].rsplit("/", 1)[-1]
words = sys.argv[2] if len(sys.argv) > 2 else "3000"
# gdb's thread number from "info threads"; the reported thread is not always the faulting one.
thread = sys.argv[3] if len(sys.argv) > 3 else "1"
dump = container(f'{GDB} -batch -ex "core-file {core}" -ex "thread {thread}" -ex "info proc mappings" '
                 f'-ex "info registers pc lr sp" -ex "x/{words}xw $sp" 2>&1')
print(next((l for l in dump.splitlines() if "terminated" in l), "?"))
regs = {m[0]: int(m[1], 16) for m in re.findall(r"^(pc|lr|sp)\s+(0x[0-9a-f]+)", dump, re.M)}
maps = [(int(a, 16), int(b, 16), path) for a, b, path in
        re.findall(r"^\s*(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+0x[0-9a-f]+\s+0x[0-9a-f]+\s+(\S+)", dump, re.M)]
lib = [(a, b) for a, b, p in maps if "libWPEWebKit" in p]
base, end = min(a for a, _ in lib), max(b for _, b in lib)


def where(v):
    return next((p.rsplit("/", 1)[-1] for a, b, p in maps if a <= v < b), "anon/JIT")


for name in ("pc", "lr"):
    print(f"{name} {regs[name]:#x} in {where(regs[name])}")
offsets = [regs[n] & ~1 for n in ("pc", "lr") if base <= regs[n] < end]
others = []
for w in re.findall(r"0x[0-9a-f]{8}", "\n".join(l.split(":", 1)[-1] for l in dump.splitlines() if l.startswith("0x"))):
    v = int(w, 16)
    if base <= v < end and v & 1 and (v - 1) not in offsets:
        offsets.append(v - 1)
    elif v & 1 and where(v) not in ("anon/JIT", "libWPEWebKit-2.0.so.1") and len(others) < 15:
        others.append(f"{v:#x} {where(v)}")
print("other libraries on the stack:", *others, sep="\n  ")
rel = " ".join(hex(o - base) for o in offsets[:50])
print(container(f"{ADDR2LINE} -f -C -e {LIB} {rel} | grep -v '^:?\\|^??' | cut -c1-170"))
