candump can0,103:7FF
cansend can0 100#11111111

sudo apt install can-utils

sudo slcand -o -c -f -s8 /dev/ttyACM6 can0  
sudo ip link set can0 txqueuelen 1000
sudo ip link set can0 up type can bitrate 1000000


ip link show can0