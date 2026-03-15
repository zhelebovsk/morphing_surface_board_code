#include "usb_debug.h"
#include "usbd_cdc_if.h"
#include "motor_helper.h"
#include "timer_helper.h"
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
        delay_ms(5000);
        return;
    }
    if (buf[0] == '>') {
        change_motor(true);
        usb_printf("Changed Chosen Motor to %i\r\n", getmot());
        return;
    }
    if (buf[0] == '<') {
        change_motor(false);
        usb_printf("Changed Chosen Motor to %i\r\n", getmot());
        return;
    }
    if (buf[0] == 'u') {
    	usb_printf("Increased Scale To %i\r\n", getscale());
    	change_scale(true);
        return;
    }
    if (buf[0] == 'd') {
        	usb_printf("Decreased Scale To %i\r\n", getscale());
        	change_scale(false);
        	return;
        }
    if (buf[0] == '+') {
    	change_zero(true);
    	usb_printf("Increased Zero of Motor %i to %i \r\n", getmot(), get_zero_val(getmot()));
    	return;
    }
    if (buf[0] == '-') {
    	change_zero(false);
    	usb_printf("Decreased Zero of Motor %i to %i \r\n", getmot(), get_zero_val(getmot()));
    	return;
    }
    if (buf[0] >= '0' && buf[0] <= '9'){
    	motors_location_set((void*)buf);
    	usb_printf("Motor set location debug command received\r\n");
    	return;
    }
    usb_printf("Received unexpected %lu bytes: %.*s\r\n", len, (int)len, buf);
    return;
}
