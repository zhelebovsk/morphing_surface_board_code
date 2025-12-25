# Power supply lines:

1. 12V_in (tp2) (x1 connector) -> 12V (tp15)

12V_in is connected to the board, and all power is derived from here

12V_in goes through the polarity and overvoltage protection unit (LM74502D, HYG025N06LS1C2). Limited overvoltage with a pair of resistors to 19.2V

2. 12V -> 3v3 (tp18, hl4) and 5v (tp17, hl3)
The installed resistors seem to be much higher than it should be like 6v and 4v5 corresponding. (LMR51430XDDCR step-down)

3. 5v -> 5v_ISO (no tp, but HL1)

B0505S-1WR3 separate the power for the communication (RS485 and CAN)

4. 12v -> 6v (motor supply) (tp16, hl2)

SIC431, the voltage can be adjusted with couple of mosfets run by stm32 2n7002



---
# Communication
1. RJ45 port:

1.1 CAN 
ISO1042BDWV connected only to 3v3, gnd and 2 stm32 pins corresponding for the communication

1.2 RS485
ISO3088DWR same as CAN bus + RS485 control

both communication protocols have the 120ohm terminals, and testpoints at the mcu side. the line output can be checked only on the rj45 side (use the rj45 adapter for communication)

2. usb (x2 connector)
USBLC6-2SC6 high-speed protection unit connects only 2 wires from the board with the usb type-c. 

3. simple usart 3 pins (x3) to the chip rx, tx, gnd
4. 
---

# Programmers
1. JTAG goes to lattice (x7)
2. SWD  goes to stm32g474 (x4)

---

# MCU
stm32g474 takes 3v3 power supply,
16mhz crystal
ref3030 for adc reference (3v)

## mcu pin groups
1. potentiometers (16) connected to adc1 and adc2 [the reasonable limit of the potentiometers are 3v0 and 0v3]
2. dir (16)
3. pwm (16)
4. usart
5. usb
6. can
7. rs485
8. i2c (eeprom memory AT24C32M/TR 32 kbit)
9. dac (limiting potentiometers)
10. spi 

---
# other
1. motor limitation tp27, tp28. alarm pins are send to the lattice, the ports need to be send to the stm32 