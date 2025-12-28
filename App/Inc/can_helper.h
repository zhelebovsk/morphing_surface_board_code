#ifndef CAN_HELPER_H
#define CAN_HELPER_H

#include "stm32g4xx_hal.h"
#include "fdcan.h"

void send_can_hello(uint8_t dip_id);
void read_can_frame(void);

#endif // CAN_HELPER_H
