#include "can_helper.h"

void send_can_hello(uint8_t dip_id)
{
    FDCAN_TxHeaderTypeDef tx_header;
    uint8_t tx_data[5] = {'H','e','l','l','o'};

    tx_header.Identifier = 0x100 + dip_id;       // Your board ID in CAN space
    tx_header.IdType = FDCAN_STANDARD_ID;
    tx_header.TxFrameType = FDCAN_DATA_FRAME;
    tx_header.DataLength = FDCAN_DLC_BYTES_5;
    tx_header.ErrorStateIndicator = FDCAN_ESI_ACTIVE;
    tx_header.BitRateSwitch = FDCAN_BRS_OFF;
    tx_header.FDFormat = FDCAN_CLASSIC_CAN;
    tx_header.TxEventFifoControl = FDCAN_NO_TX_EVENTS;
    tx_header.MessageMarker = 0;

    HAL_FDCAN_AddMessageToTxFifoQ(&hfdcan1, &tx_header, tx_data);
}