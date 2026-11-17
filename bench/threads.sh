#!/bin/sh
# CPU time per thread of the browser's processes between two moments: run "threads.sh snap A" before
# and "threads.sh snap B" after, then "threads.sh diff A B" prints jiffies (1/100 s) per process/thread.
# Thread names come from /proc/<pid>/task/<tid>/comm (WebKit names its threads).
case "$1" in
  snap)
    F=/tmp/threads.$2
    : > $F
    for p in $(pidof WPEWebProcess WPENetworkProcess browser); do
      pn=$(cat /proc/$p/comm)
      for t in /proc/$p/task/*; do
        set -- $(cat $t/stat | sed 's/.*) //')
        echo "$pn $(cat $t/comm | tr ' ' _) $(( ${12} + ${13} ))" >> $F
      done
    done ;;
  diff)
    awk 'NR==FNR { a[$1" "$2] += $3; next } { b[$1" "$2] += $3 }
         END { for (k in b) { d = b[k] - a[k]; if (d > 5) printf "%6d %s\n", d, k } }' /tmp/threads.$2 /tmp/threads.$3 | sort -rn ;;
esac
