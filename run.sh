# make clean
SEP="\033[1;34m------------------------------------------------------------\033[0m"
cd "$(dirname "$0")/firmware" &&
make && 
echo -e "$SEP" && 
openocd -f interface/stlink.cfg -f target/stm32g4x.cfg -c "program build/STM32_code.bin verify reset exit 0x08000000"