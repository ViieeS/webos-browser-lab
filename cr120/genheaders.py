"""Lists generated headers (gen/...) reachable by #include from the given source files.

OSE's content/browser includes chrome/browser/web_applications headers through neva installable
code without a gn dep on their mojom/proto targets, so ninja may compile it before those headers
exist. Building the printed paths as ninja targets first removes the race.
Generated headers that do not exist yet are not scanned, so run again after building them.
usage (in the container, from src): python3 /src/genheaders.py out/c1 <file>...
"""
import os
import re
import sys

out, starts = sys.argv[1], sys.argv[2:]
gen = os.path.join(out, "gen")
inc = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M)
seen, missing = set(), set()
stack = list(starts)
while stack:
    path = stack.pop()
    if path in seen:
        continue
    seen.add(path)
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    for name in inc.findall(text):
        if os.path.exists(name):
            stack.append(name)
        elif os.path.exists(os.path.join(gen, name)):
            stack.append(os.path.join(gen, name))
        elif re.search(r"\.(mojom[-a-z]*|pb|pbzero)\.h$|_buildflags\.h$|/grit/", name):
            missing.add("gen/" + name)
print("\n".join(sorted(missing)))
