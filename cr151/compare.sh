#!/bin/sh
# compare.sh: cheap comparison of our chrome (/work/dist/browser) with their release chrome (/work/theirs/browser).
# A rebuild with different flags (-O2/-Os, LTO opt level, armv8.2) cannot match byte for byte, so this compares what
# survives a flag change: needed libraries, dynamic symbols, strings with URLs, the set of .pak/resource files,
# Chromium version strings, and section sizes. Output: /work/compare/*.txt and a summary on stdout.
R=llvm-readelf-23; N=llvm-nm-23
A=/work/dist/browser/chrome; T=/work/theirs/browser/chrome; O=/work/compare
mkdir -p "$O"
$R -d "$A" | grep NEEDED | sed 's/.*\[//; s/\]//' | sort > "$O/needed.ours"
$R -d "$T" | grep NEEDED | sed 's/.*\[//; s/\]//' | sort > "$O/needed.theirs"
$N -D --defined-only "$A" | awk '{print $NF}' | sort -u > "$O/dynsym-def.ours"
$N -D --defined-only "$T" | awk '{print $NF}' | sort -u > "$O/dynsym-def.theirs"
$N -D --undefined-only "$A" | awk '{print $NF}' | sort -u > "$O/dynsym-undef.ours"
$N -D --undefined-only "$T" | awk '{print $NF}' | sort -u > "$O/dynsym-undef.theirs"
strings -n 8 "$A" | grep -oE 'https?://[A-Za-z0-9.-]+' | sort -u > "$O/hosts.ours"
strings -n 8 "$T" | grep -oE 'https?://[A-Za-z0-9.-]+' | sort -u > "$O/hosts.theirs"
strings -n 6 "$A" | grep -E '^Chrome/[0-9.]+$|^151\.0\.[0-9]+\.[0-9]+$' | sort -u > "$O/version.ours"
strings -n 6 "$T" | grep -E '^Chrome/[0-9.]+$|^151\.0\.[0-9]+\.[0-9]+$' | sort -u > "$O/version.theirs"
(cd /work/dist/browser && find . -type f | sort) > "$O/files.ours"
(cd /work/theirs/browser && find . -type f | sort) > "$O/files.theirs"
$R -S -W "$A" | python3 -c 'import sys; [print(p[1], int(p[5], 16)) for p in (l.split() for l in sys.stdin) if len(p) > 5 and p[1].startswith(".")]' | sort > "$O/sections.ours"
$R -S -W "$T" | python3 -c 'import sys; [print(p[1], int(p[5], 16)) for p in (l.split() for l in sys.stdin) if len(p) > 5 and p[1].startswith(".")]' | sort > "$O/sections.theirs"
cmpset() {   # name: lines only in ours / only in theirs
	echo "$1: ours $(wc -l < "$O/$1.ours"), theirs $(wc -l < "$O/$1.theirs"), only ours $(comm -23 "$O/$1.ours" "$O/$1.theirs" | wc -l), only theirs $(comm -13 "$O/$1.ours" "$O/$1.theirs" | wc -l)"
}
for s in needed dynsym-def dynsym-undef hosts version files; do cmpset "$s"; done
echo "hosts only in theirs:"; comm -13 "$O/hosts.ours" "$O/hosts.theirs" | head -20
echo "hosts only in ours:"; comm -23 "$O/hosts.ours" "$O/hosts.theirs" | head -20
echo "needed only in theirs:"; comm -13 "$O/needed.ours" "$O/needed.theirs"
echo "dynsym-undef only in theirs:"; comm -13 "$O/dynsym-undef.ours" "$O/dynsym-undef.theirs" | head -20
echo "files only in theirs:"; comm -13 "$O/files.ours" "$O/files.theirs"
echo "sections (ours / theirs):"; join "$O/sections.ours" "$O/sections.theirs" | awk '$2 > 100000 || $3 > 100000'
echo "versions:"; cat "$O/version.ours"; echo --; cat "$O/version.theirs"
