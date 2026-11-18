#!/usr/bin/env bash
if [ -z "$1" ]; then
    echo "Usage: $0 ACM_number"
    echo "Example: $0 6   -> /dev/ttyACM6"
    exit 1
fi

ACM=$1
DEV="/dev/ttyACM$ACM"

if [ ! -e "$DEV" ]; then
    echo "ERROR: $DEV not found. Is the adapter plugged in? (check: ls /dev/ttyACM*)" >&2
    exit 1
fi

echo "Starting SLCAN on $DEV"
sudo ip link set can0 down 2>/dev/null
sudo pkill slcand 2>/dev/null
sudo slcand -o -c -f -s8 "$DEV" can0 || { echo "ERROR: slcand failed on $DEV" >&2; exit 1; }
sudo ip link set can0 txqueuelen 1000
# one-shot isn't supported by this hardware's firmware (EOPNOTSUPP on the
# Kvaser Leaf v3 -- see can_start_kvaser.sh); left out here for the same
# reason.
#
# restart-ms 100 auto-recovers the local controller if bus-off trips, instead
# of leaving can0 dead until a manual down/up. It is recovery, not prevention.
# An absent *addressee* is harmless, since any healthy board ACKs every frame;
# bus-off needs real bit errors. See can_start_kvaser.sh for the explanation.
sudo ip link set can0 up type can bitrate 1000000 restart-ms 100 || {
    echo "ERROR: failed to bring up can0 (see the ip error above)" >&2; exit 1; }

echo "CAN interface can0 is up"