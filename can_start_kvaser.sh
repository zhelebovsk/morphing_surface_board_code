#!/usr/bin/env bash
# Bring up can0 via Kvaser Leaf v3 (uses kvaser_usb kernel module — no slcand needed).
# Run once after plugging in the Kvaser. The device appears as can0 automatically.

sudo modprobe kvaser_usb 2>/dev/null

sudo ip link set can0 down 2>/dev/null
sudo ip link set can0 txqueuelen 1000
sudo ip link set can0 up type can bitrate 1000000

echo "CAN interface can0 is up (Kvaser)"
