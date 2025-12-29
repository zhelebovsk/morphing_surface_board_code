#include "usb_debug.h"
#include "usbd_cdc_if.h"
#include "motor_helper.h"
#include <string.h>
#include <stdio.h>

#define USB_PRINTF_BUF_SIZE 256

void usb_printf(const char *format, ...) {
    char buffer[USB_PRINTF_BUF_SIZE];
    va_list args;
    va_start(args, format);
    int len = vsnprintf(buffer, USB_PRINTF_BUF_SIZE, format, args);
    va_end(args);
    
    if (len > 0 && len < USB_PRINTF_BUF_SIZE) {
        CDC_Transmit_FS((uint8_t*)buffer, len);
    }
}

void usb_handle_command() {
    uint8_t *buf = USB_GetRxBuffer();
    uint32_t len = USB_GetRxLength();
    if (len == 0) {
        return;
    }
    if (buf[0] == 'k') {
        usb_printf("Kill command received\r\n");
        for (int i = 0; i < 16; i++) {
            set_motor(i, 0);
        }
        return;
    }
    if (buf[0] == 'h') {
        usb_printf("Help command received\r\n");
        return;
    }
    if (buf[0] == 's') {
        usb_printf("Setter command received\r\n");
        return;
    }
    if (buf[0] == 'g') {
        usb_printf("Getter command received\r\n");
        return;
    }
    usb_printf("Received unexpected %lu bytes: %.*s\r\n", len, (int)len, buf);
    return;
}