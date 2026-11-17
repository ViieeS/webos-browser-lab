"""List source files a ninja target needs that are missing from the tree (OSE snapshot drops some).
Runs inside the cr120 container from src/: python3 /src/missing.py out/c1 content_shell
"""
import os
import subprocess
import sys

out, target = sys.argv[1], sys.argv[2]
inputs = subprocess.run(["ninja", "-C", out, "-t", "inputs", target], capture_output=True,
                        text=True, check=True).stdout.split()
for path in inputs:
    if path.startswith("../../") and not os.path.exists(os.path.join(out, path)):
        print(path[len("../../"):])
