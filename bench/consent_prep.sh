#!/bin/sh
# Builds the autoconsent add-ons consent_run.py compares (cr151/autoconsent.sh says what each variant changes), as
# tars for the TV.
# usage: consent_prep.sh <autoconsent-X.Y.Z.tgz> <sha256> <out dir>     writes <out dir>/<variant>.tar
set -eu
TGZ=$1 SHA=$2 OUT=$3
BUILD=$(cd "$(dirname "$0")/../cr151" && pwd)/autoconsent.sh
# test keeps its old tar name, autoconsent.tar (consent_run.py variant "ac")
for v in test lean lean-noh lean-frames; do
	name=$v
	[ "$v" = test ] && name=autoconsent
	sh "$BUILD" "$TGZ" "$SHA" "$v" "$OUT/$name"
	tar -cf "$OUT/$name.tar" -C "$OUT/$name" .
	echo "$OUT/$name.tar $(wc -c < "$OUT/$name.tar") bytes"
done
