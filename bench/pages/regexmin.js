// One variant per process (a crash kills it): jsc --useRegExpJIT=true regexmin.js -- <index>
const variants = [
  /(((\w+):\/\/)([^\/:]*)(:(\d+))?)?([^#?]*)(\?([^#]*))?(#(.*))?/,  // 0 original
  /((\w+):\/\/)?([^#?]*)/,                                           // 1 one optional nested group
  /(((\w+):\/\/))?x/,                                                // 2 doubly nested optional
  /((a)(b))?c/,                                                      // 3 tiny nested optional
  /(a(b)?)?c/,                                                       // 4 optional inside optional
  /(ab)?(cd)?(ef)?(gh)?(ij)?(kl)?(mn)?/,                             // 5 many flat optionals
  /(\?([^#]*))?(#(.*))?/,                                            // 6 tail of the original
  /(#(.*))?/,                                                        // 7 one nested optional with .*
  /([^#?]*)(\?([^#]*))?/,                                            // 8
  /(((\w+):\/\/)([^\/:]*)(:(\d+))?)?/,                               // 9 head of the original
];
const i = Number(arguments[0]);
const re = variants[i];
const inputs = ["http://www.example.com:8080/path/x.html?a=1&b=2#frag", "/relative/path", "", "abcdefgh", "ac", "x"];
let r;
for (let n = 0; n < 20000; n++) r = re.exec(inputs[n % inputs.length]);
print(`REGEXMIN ${i} ok ${re.source}`);
