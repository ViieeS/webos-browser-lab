// Which RegExp shapes crash or misbehave with the 32-bit RegExp JIT (jsc --useRegExpJIT=true).
// Each case prints before it runs, so the last printed line names the crasher.
const cases = [
  ["literal", /abc/, "xxabcxx"],
  ["class", /[a-z]+\d/, "hello5"],
  ["alt", /cat|dog|bird/, "a bird"],
  ["anchors", /^\s*(\w+)\s*$/, "  word  "],
  ["greedy-group", /(ab)+c/, "ababc"],
  ["lazy", /a.*?b/, "aXXbYYb"],
  ["nested-parens", /((a|b)c)+d/, "acbcd"],
  ["backref", /(\w)\1/, "hello"],
  ["ignorecase", /HeLLo/i, "say hello"],
  ["unicode", /\u{1F600}/u, "x\u{1F600}"],
  ["global-replace", /o/g, "foo boo"],
  ["split", /,\s*/, "a, b,c"],
  ["sticky", /foo/y, "foofoo"],
  ["lookahead", /a(?=b)/, "ab"],
  ["lookbehind", /(?<=a)b/, "ab"],
  ["named", /(?<y>\d{4})-(?<m>\d\d)/, "2026-11"],
  ["dotall", /a.b/s, "a\nb"],
  ["long-input", /x+y/, "x".repeat(100000) + "y"],
];
for (const [name, re, input] of cases) {
  print(`REGEX ${name} ...`);
  let r;
  for (let i = 0; i < 2000; i++) {
    re.lastIndex = 0;
    r = re.flags.includes("g") ? input.replace(re, "0") : name === "split" ? input.split(re).join("|") : JSON.stringify(re.exec(input));
  }
  print(`REGEX ${name} ok ${String(r).slice(0, 60)}`);
}
print("REGEX done");
