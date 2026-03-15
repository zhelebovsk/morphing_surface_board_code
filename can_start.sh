if [ -z "$1" ]; then
    echo "Usage: $0 ACM_number"
    echo "Example: $0 6   -> /dev/ttyACM6"
    exit 1
fi

ACM=$1
DEV="/dev/ttyACM$ACM"

echo "Starting SLCAN on $DEV"
sudo ip link set can0 down 2>/dev/null
sudo pkill slcand 2>/dev/null
sudo slcand -o -c -f -s8 $DEV can0
sudo ip link set can0 txqueuelen 1000
sudo ip link set can0 up type can bitrate 1000000

echo "CAN interface can0 is up"