#!/bin/sh
# threads.sh for content_shell: CPU jiffies per thread between two snapshots, labelled with the
# Chromium process type (browser/renderer/gpu-process/utility), plus any webOS media daemon
# (umediaserver, pipelines, decoders) so a hardware decode path shows up too.
# usage: threads_cr120.sh snap A; ...; threads_cr120.sh snap B; threads_cr120.sh diff A B
case "$1" in
  snap)
    F=/tmp/cr120threads.$2
    : > $F
    for c in /proc/[0-9]*/comm; do
      p=${c#/proc/}; p=${p%/comm}
      n=$(cat $c 2>/dev/null)
      case "$n" in
        content_shell)
          ty=$(tr '\000' '\n' < /proc/$p/cmdline | sed -n 's/^--type=//p' | head -n 1)
          pn=${ty:-browser} ;;
        cr120run) pn=launcher ;;  # owns NDL in the app build (launcher/cr120run.c)
        *media*|*pipeline*|*vdec*|*VDEC*|*decoder*|*omx*|*gst*) pn=sys:$n ;;
        *) continue ;;
      esac
      for t in /proc/$p/task/*; do
        set -- $(sed 's/.*) //' $t/stat 2>/dev/null)
        [ -n "${13}" ] && echo "$pn $(tr ' ' _ < $t/comm) $(( ${12} + ${13} ))" >> $F
      done
    done ;;
  diff)
    awk 'NR==FNR { a[$1" "$2] += $3; next } { b[$1" "$2] += $3 }
         END { for (k in b) { d = b[k] - a[k]; if (d > 5) printf "%6d %s\n", d, k } }' /tmp/cr120threads.$2 /tmp/cr120threads.$3 | sort -rn ;;
esac
