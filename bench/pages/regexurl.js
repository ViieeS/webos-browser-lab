// Narrowing the 32-bit RegExp JIT crash: the URL regex from Octane regexp, alone, hot.
const re = /(((\w+):\/\/)([^\/:]*)(:(\d+))?)?([^#?]*)(\?([^#]*))?(#(.*))?/;
const inputs = ["http://www.example.com:8080/path/x.html?a=1&b=2#frag", "/relative/path", "", "http://host",
                "ftp://h:21/?q", "noscheme?x#y"];
const want = inputs.map((s) => JSON.stringify(re.exec(s)));
let bad = 0;
for (let i = 0; i < 20000; i++) {
  const k = i % inputs.length;
  const got = JSON.stringify(re.exec(inputs[k]));
  if (got !== want[k]) { if (bad++ < 5) print(`REGEXURL WRONG ${k} ${got}`); }
}
print(`REGEXURL done bad=${bad} first=${want[0]}`);
