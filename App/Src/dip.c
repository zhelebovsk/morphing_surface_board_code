#include "dip.h"

uint8_t Read_DIP_ID(void)
{
    uint8_t dip_status[6] = {0};
    dip_status[0] = !HAL_GPIO_ReadPin(GPIOC, DIP_1_Pin);
    dip_status[1] = !HAL_GPIO_ReadPin(GPIOD, DIP_2_Pin);
    dip_status[2] = !HAL_GPIO_ReadPin(GPIOD, DIP_3_Pin);
    dip_status[3] = !HAL_GPIO_ReadPin(GPIOD, DIP_4_Pin);
    dip_status[4] = !HAL_GPIO_ReadPin(GPIOC, DIP_5_Pin);
    dip_status[5] = !HAL_GPIO_ReadPin(GPIOC, DIP_6_Pin);

    uint8_t dip_id = (dip_status[5] << 5) | (dip_status[4] << 4) |
                     (dip_status[3] << 3) | (dip_status[2] << 2) |
                     (dip_status[1] << 1) |  dip_status[0];


    return dip_id;
}