#!/bin/sh
# Runs on the TV for the length of a benchmark: a Left Shift press every 60 s on /dev/input/event1 ("LGE RCU"), which
# resets tvpower's idle timer, so the screensaver does not cover and pause the browser. The compositor does not read
# event1, so the browser never sees the key. Checked 2026-11-18: Shift on event1 takes the TV from "Screen Saver" to
# "Active". A tvpower registerScreenSaverRequest client answering "no" from a root shell does not work (tvpower still
# starts the saver), and event10 ("LGE Network Input") exists only while a network remote is connected.
# Start it detached from the telnet session, which kills its children on exit (ps shows only "sh"; use pgrep -f):
#   setsid sh keepawake.sh < /dev/null > /dev/null 2>&1 &      Stop it: pkill -f keepawake.sh
while :; do
	/media/developer/temp/evkeys /dev/input/event1 50 42
	sleep 60
done
