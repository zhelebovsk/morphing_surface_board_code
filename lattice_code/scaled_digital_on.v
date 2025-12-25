module digital_forwarding #(
    parameter N = 16  // number of channels
)(
    output wire [N-1:0] PWM_out,
    output wire [N-1:0] DIR_out,
    input  wire [N-1:0] PWM,
    input  wire [N-1:0] DIR,
	input  wire [15:0] POT_IN,
    output wire [3:0]  POT_OUT
);

    genvar i;
    generate
        for (i = 0; i < N; i = i + 1) begin : forward_logic
            assign PWM_out[i] = (DIR[i] == 1'b0) ? ~PWM[i] : 1'b1;
            assign DIR_out[i] = (DIR[i] == 1'b0) ? 1'b1 : ~PWM[i];
        end
    endgenerate
	assign POT_OUT[0] = &POT_IN[3:0];      // OR of inputs 0–3
    assign POT_OUT[1] = &POT_IN[7:4];      // OR of inputs 4–7
    assign POT_OUT[2] = &POT_IN[11:8];     // OR of inputs 8–11
    assign POT_OUT[3] = &POT_IN[15:12];    // OR of inputs 12–15

endmodule