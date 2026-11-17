// The same tight loop as the in-page check: JIT on ~0.1 s, LLInt-only several times slower.
const f = () => { let s = 0; for (let i = 0; i < 3e7; i++) s += i % 7; return s; };
f();
const t = Date.now();
f();
print("loop_ms=" + (Date.now() - t));
