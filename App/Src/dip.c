#include "dip.h"

uint8_t Read_DIP_ID(void)
{
    uint8_t dip_id = 0;
    dip_id |= (!HAL_GPIO_ReadPin(DIP_1_GPIO_Port, DIP_1_Pin)) << 0;
    dip_id |= (!HAL_GPIO_ReadPin(DIP_2_GPIO_Port, DIP_2_Pin)) << 1;
    dip_id |= (!HAL_GPIO_ReadPin(DIP_3_GPIO_Port, DIP_3_Pin)) << 2;
    dip_id |= (!HAL_GPIO_ReadPin(DIP_4_GPIO_Port, DIP_4_Pin)) << 3;
    dip_id |= (!HAL_GPIO_ReadPin(DIP_5_GPIO_Port, DIP_5_Pin)) << 4;
    dip_id |= (!HAL_GPIO_ReadPin(DIP_6_GPIO_Port, DIP_6_Pin)) << 5;
    return dip_id;
}