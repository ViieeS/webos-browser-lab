"""Block until a file contains a regex, or a timeout passes. Prints the matching line or TIMEOUT.
usage: waitfor.py <file> <regex> <seconds>
"""
import re
import sys
import time

path, pattern, seconds = sys.argv[1], re.compile(sys.argv[2]), float(sys.argv[3])
deadline = time.time() + seconds
while time.time() < deadline:
    try:
        for line in open(path, errors="replace"):
            if pattern.search(line):
                print(line.rstrip())
                sys.exit(0)
    except FileNotFoundError:
        pass
    time.sleep(5)
print("TIMEOUT")
sys.exit(1)
