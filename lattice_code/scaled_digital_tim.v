module digital_forwarding #(
    parameter N = 16  // number of channels
)(
    input  wire clk_ext,              // External 40 MHz square 
    input  wire [N-1:0] PWM,
    input  wire [N-1:0] DIR,
    output reg  [N-1:0] PWM_out,
    output reg  [N-1:0] DIR_out       
);
	
	integer i;
    always @(posedge clk_ext) begin
        for (i = 0; i < N; i = i + 1) begin
            if (DIR[i] == 1'b0) begin
                PWM_out[i] <= ~PWM[i];
                DIR_out[i] <= 1'b1;
            end else begin
                PWM_out[i] <= 1'b1;
                DIR_out[i] <= ~PWM[i];
            end
        end
    end

endmodule

module pot_combiner (
    input  wire        clk_ext,
    input  wire [15:0] POT_IN,
    output reg  [3:0]  POT_OUT
);

    always @(posedge clk_ext) begin
        POT_OUT[0] <= |POT_IN[3:0];      // OR of inputs 0–3
        POT_OUT[1] <= |POT_IN[7:4];      // OR of inputs 4–7
        POT_OUT[2] <= |POT_IN[11:8];     // OR of inputs 8–11
        POT_OUT[3] <= |POT_IN[15:12];    // OR of inputs 12–15
    end

endmodule
