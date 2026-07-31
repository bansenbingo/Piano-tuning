module uart_tx #(
    parameter CLK_FREQ = 100_000_000,
    parameter BAUD     = 921_600
) (
    input  wire       clk,
    input  wire       rst,
    input  wire [7:0] data,
    input  wire       send,
    output reg        busy,
    output reg        tx
);

    localparam DIV   = CLK_FREQ / BAUD;
    localparam DIV_W = $clog2(DIV) + 1;

    localparam S_IDLE  = 3'd0;
    localparam S_START = 3'd1;
    localparam S_DATA  = 3'd2;
    localparam S_STOP  = 3'd3;

    reg [2:0]       state;
    reg [DIV_W-1:0] div_cnt;
    reg [2:0]       bit_idx;
    reg [7:0]       shift_reg;

    always @(posedge clk) begin
        if (rst) begin
            state     <= S_IDLE;
            div_cnt   <= 0;
            bit_idx   <= 0;
            shift_reg <= 0;
            busy      <= 0;
            tx        <= 1'b1;
        end else begin
            case (state)
                S_IDLE: begin
                    busy <= 0;
                    tx   <= 1'b1;
                    if (send) begin
                        shift_reg <= data;
                        state     <= S_START;
                        div_cnt   <= 0;
                        busy      <= 1;
                    end
                end

                S_START: begin
                    tx <= 1'b0;
                    if (div_cnt == DIV - 1) begin
                        div_cnt <= 0;
                        bit_idx <= 0;
                        state   <= S_DATA;
                    end else begin
                        div_cnt <= div_cnt + 1;
                    end
                end

                S_DATA: begin
                    tx <= shift_reg[bit_idx];
                    if (div_cnt == DIV - 1) begin
                        div_cnt <= 0;
                        if (bit_idx == 7) begin
                            state <= S_STOP;
                        end else begin
                            bit_idx <= bit_idx + 1;
                        end
                    end else begin
                        div_cnt <= div_cnt + 1;
                    end
                end

                S_STOP: begin
                    tx <= 1'b1;
                    if (div_cnt == DIV - 1) begin
                        state <= S_IDLE;
                        busy  <= 0;
                    end else begin
                        div_cnt <= div_cnt + 1;
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
