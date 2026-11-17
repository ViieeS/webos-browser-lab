# gdb -batch -x stackscan.py: heuristic backtrace for a static jsc core whose libc frames gdb cannot
# unwind. Prints every stack word of each thread that lands in a jsc function (thumb bit set).
import gdb

for thread in gdb.selected_inferior().threads():
    thread.switch()
    sp = int(gdb.parse_and_eval("$sp"))
    print(f"=== thread {thread.num} sp={sp:#x} pc={int(gdb.parse_and_eval('$pc')):#x}")
    n = min(4000, ((sp | 0xfff) + 1 - sp) // 4 + 1024 * 2)
    while True:
        try:
            mem = gdb.selected_inferior().read_memory(sp, 4 * n)
            break
        except gdb.MemoryError:
            n -= 256

    seen = 0
    for i in range(n):
        w = int.from_bytes(bytes(mem[4 * i:4 * i + 4]), "little")
        if not (w & 1) or not (0x10000 <= w < 0x3000000):
            continue
        sym = gdb.execute(f"info symbol {w - 1:#x}", to_string=True).strip()
        if "No symbol" in sym:
            continue
        print(f"  +{4 * i:#06x} {w:#x} {sym[:160]}")
        seen += 1
        if seen > 40:
            break
