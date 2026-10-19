#!/usr/bin/env bash
# Bring up can0 via Kvaser Leaf v3 (uses kvaser_usb kernel module — no slcand needed).
# Run once after plugging in the Kvaser. The device appears as can0 automatically.

sudo modprobe kvaser_usb 2>/dev/null

sudo ip link set can0 down 2>/dev/null
sudo ip link set can0 txqueuelen 1000

# --- What actually causes bus-off here (read before changing these flags) ---
#
# CAN acknowledgement is NOT addressed: every healthy node drives the ACK slot
# dominant for every frame it receives correctly, whatever ID is in the header.
# So pinging a board that isn't wired up is harmless as long as at least one
# other board is alive to answer -- cantest/test_comms.py relies on exactly
# this (one real board ACKs the frames addressed to the other 29).
#
# If NO node can ACK (nothing powered, bus unplugged), the controller retries
# forever and sits at ERROR-PASSIVE -- it does not go bus-off, because ACK
# errors stop counting once error-passive (confirmed on the bench 2026-10-19).
# Bus-off needs real bit errors: bitrate mismatch, wiring/termination faults,
# or a node corrupting frames (e.g. a board resetting mid-traffic).
#
# So repeated bus-off is a physical-layer fault to find, not a tuning problem.
#
# one-shot mode (try each frame once, no hardware retransmit) would blunt it,
# but this Kvaser Leaf v3's firmware doesn't report the capability -- "ip link
# set ... one-shot on" fails with EOPNOTSUPP, and because ip applies all
# attributes in one atomic netlink call, that failure took the whole command
# down with it and left can0 DOWN. Left out deliberately; don't re-add blind.
#
# restart-ms 100 is recovery, not prevention: on bus-off the driver resets the
# controller after 100 ms instead of leaving can0 dead until a manual down/up.
# It restarts the local controller only -- the interface stays up, open sockets
# survive, and the other boards see nothing but an idle bus and keep holding
# their last commanded position. Cost is ~100 ms, i.e. ~10 dropped frames at
# the 100 Hz command rate.
sudo ip link set can0 up type can bitrate 1000000 restart-ms 100

echo "CAN interface can0 is up (Kvaser)"
