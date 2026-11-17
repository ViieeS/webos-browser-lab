// The JS-only part of bench.html, for a jsc shell: same tests and checksums, so a 64-bit jsc on
// the TV compares directly with the browser's 32-bit JIT. Each test runs 3 times; the best counts.
const tests = [
  ["int loop", () => { let s = 0; for (let i = 0; i < 3e6; i++) s = (s + i * 7) | 0; return s; }, 699351136],
  ["math sin/cos/pow", () => {
      let s = 0;
      for (let i = 1; i < 2e5; i++) s += Math.sin(i) * Math.cos(i / 3) + Math.pow(i % 17, 0.5) + Math.atan2(i, 7);
      return Math.round(s * 1000) / 1000; }, 837242.606],
  ["objects", () => {
      const a = []; for (let i = 0; i < 2e5; i++) a.push({ x: i, y: i * 2 });
      return a.reduce((t, o) => t + o.x + o.y, 0); }, 59999700000],
  ["strings", () => {
      let s = ""; for (let i = 0; i < 5e4; i++) s += String.fromCharCode(65 + i % 26);
      return s.split("A").length; }, 1925],
];
let total = 0;
for (const [name, fn, want] of tests) {
  let best = Infinity, got;
  for (let r = 0; r < 3; r++) {
    const t0 = Date.now(); got = fn(); best = Math.min(best, Date.now() - t0);
  }
  const ok = !Number.isInteger(want) ? Math.abs(got - want) < 0.01 : got === want;
  total += best;
  print(`BENCH ${name} ${best} ${ok ? "ok" : "WRONG " + got}`);
}
print(`BENCH total ${total}`);
