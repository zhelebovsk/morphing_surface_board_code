module digital_forwarding (
    output wire PWM_out,
    output wire DIR_out,
	input wire PWM,
	input wire DIR
);

assign PWM_out = (DIR == 1'b0) ? ~PWM : 1'b1;
assign DIR_out = (DIR == 1'b0) ? 1'b1 : ~PWM;

endmodule