#!/bin/bash
# patch.sh: put every file that the patch series touches back to git's content, then run upstream apply-patches.py
# (their patches + ours from browser/cr151/patches). Upstream expects a fresh snapshot each time; this makes a re-run
# on the same tree safe. Files created by a patch are removed first.
. /opt/cn/container/lib.sh
for p in /opt/cn/patches/*.patch; do
	git -C "$REPO" apply --numstat "$p" 2>/dev/null | cut -f3
	grep -E '^\+\+\+ b/' "$p" | sed 's|^+++ b/||; s|\t.*||'
done | sort -u > "$W/patched-paths.txt"
while read -r f; do
	[ -n "$f" ] || continue
	if git -C "$REPO" ls-files --error-unmatch -- "$f" > /dev/null 2>&1; then
		git -C "$REPO" checkout -q -- "$f"
	else
		rm -f "$REPO/$f"
	fi
done < "$W/patched-paths.txt"
log "reset $(wc -l < "$W/patched-paths.txt") patched paths"
rc=0
REPO=$REPO W=$W SNAP=$SNAP python3 "$CN/container/apply-patches.py" > "$W/apply.txt" 2>&1 || rc=$?
cat "$W/apply.txt" >> "$LOG"
grep -v '^applied' "$W/apply.txt" || true
[ $rc -eq 0 ] || die "patches did not apply"
log "applied $(ls /opt/cn/patches/*.patch | wc -l) patches"
