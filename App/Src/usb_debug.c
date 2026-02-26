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
    if (buf[0] == 'z') {
    	usb_printf("Zero command received, zeros are %i|%i|%i|%i|%i|%i|%i|%i|%i|%i|%i|%i|%i|%i|%i|%i\r\n", get_zero_val(0), get_zero_val(1), get_zero_val(2),
    			get_zero_val(3), get_zero_val(4), get_zero_val(5), get_zero_val(6), get_zero_val(7), get_zero_val(8), get_zero_val(9), get_zero_val(10),
				get_zero_val(11), get_zero_val(12), get_zero_val(13), get_zero_val(14), get_zero_val(15));
    	zero_motors();
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
    	motor_location_set((void*)buf);
    	usb_printf("Motor set location debug command received\r\n");
    	return;
    }
    usb_printf("Received unexpected %lu bytes: %.*s\r\n", len, (int)len, buf);
    return;
}
