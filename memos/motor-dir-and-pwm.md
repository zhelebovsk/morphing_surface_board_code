# Direction

every main loop cycle the direction is set

!Are you sure you set the correct pins? how to check it?

# PWM
PWM signal is subject to be set and checked, though the fpga is not configured yet

tim 1, 3, 4, 8

prescaler is 6-1 and 256-1 is the period
auto-preload (not to change the values on the middle of running, but only in the beginning of the period)

pwm1    PE9     1-1
pwm2    PE11    1-2
pwm3    PE13    1-3
pwm4    PE14    1-4
pwm5    PC6     8-1
pwm6    PC7     8-2
pwm7    PC8     8-3
pwm8    PC9     8-4
pwm9    PD12    4-1
pwm10   PD13    4-2
pwm11   PD14    4-3
pwm12   PD15    4-4
pwm13   PE2     3-1
pwm14   PE3     3-2
pwm15   PE4     3-3
pwm16   PE5     3-4
