#!/bin/sh
# Shallow fetch of webOS-ports/chromium151 at the commit pinned in upstream/source/config.env (C151_COMMIT) into
# /work/c151 (docker volume cr151work). GitHub cuts long packs now and then ("early EOF"), so it retries.
# usage (from browser/): docker run --rm --entrypoint sh -v cr151work:/work -v "$PWD/cr151:/cr151:ro" alpine/git /cr151/fetch.sh
set -u
C=$(sed -n 's/^C151_COMMIT=\([0-9a-f]*\).*/\1/p' /cr151/upstream/source/config.env)
R=/work/c151
[ -d "$R/.git" ] || { git init -q "$R" && git -C "$R" remote add origin https://github.com/webOS-ports/chromium151; }
git -C "$R" config http.lowSpeedLimit 1000
git -C "$R" config http.lowSpeedTime 120
n=0
until git -C "$R" fetch -q --depth 1 origin "$C"; do
	n=$((n + 1)); [ $n -ge 8 ] && { echo "fetch failed $n times"; exit 1; }
	echo "fetch failed ($n), retry in 30 s"; sleep 30
done
git -C "$R" checkout -q --detach FETCH_HEAD
[ "$(git -C "$R" rev-parse HEAD)" = "$C" ] || { echo "HEAD is not $C"; exit 1; }
echo "at $C, $(git -C "$R" ls-files | wc -l) files, $(du -sh "$R" | cut -f1)"
