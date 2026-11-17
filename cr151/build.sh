#!/bin/bash
# build.sh: our build driver in place of upstream container/build.sh (which is built around Modal snapshots and
# time-boxed chunks). Same sysroot (compat, glibc 2.24), builtins, patches and args.gn (+ args.delta.gn).
# usage (inside incontainer.sh): build.sh gen | build [ninja targets, default chrome] | collect
. /opt/cn/container/lib.sh
need_sysroot
need_builtins
cd "$SRC"
mkdir -p "$OUT"
cmp -s "$CN/args.gn" "$OUT/args.gn" || cp "$CN/args.gn" "$OUT/args.gn"
case "${1:-build}" in
gen)
	buildtools/linux64/gn gen "$OUT" 2>&1 | tee -a "$LOG"
	[ "${PIPESTATUS[0]}" -eq 0 ] || die "gn gen failed"
	buildtools/linux64/gn args "$OUT" --list --short --overrides-only > "$OUT/args-effective.txt" 2>&1 || true
	grep -q -- "-mfloat-abi=softfp" "$OUT/obj/base/base.ninja" || die "target cflags lack -mfloat-abi=softfp (patch 0012?)"
	grep -o -- '-mtune=[a-z0-9-]*\|-march=[a-z0-9.+-]*\|-mfpu=[a-z0-9-]*' "$OUT/obj/base/base.ninja" | sort | uniq -c | tee -a "$LOG"
	;;
build)
	shift || true
	T=${*:-chrome}
	J=${BUILD_JOBS:-$(nproc)}
	log "ninja -j $J $T"
	ninja -C "$OUT" -j "$J" -k 0 $T 2>&1 | tee "$W/ninja-last.txt" |
		awk '/^\[[0-9]+\/[0-9]+\]/{n++; if (n % 500 == 0) {print; fflush()}} /^FAILED|error:/{print; fflush()}'
	rc=${PIPESTATUS[0]}
	grep -E '^FAILED|error:' "$W/ninja-last.txt" | head -40 > "$W/ninja-errors.txt" || true
	log "ninja exit $rc"
	exit $rc
	;;
collect)
	bash "$CN/container/collect.sh"
	;;
esac
