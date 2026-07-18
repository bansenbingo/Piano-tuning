module pdm_decoder (
    input  wire        clk,
    input  wire        rst,
    input  wire        m_data,
    output reg         m_clk,
    output wire        m_lrsel,
    output reg  [7:0]  pcm_sample,
    output reg         sample_valid
);

    assign m_lrsel = 1'b0;

    localparam MCLK_DIV = 20;
    localparam WINDOW   = 128;

    reg [5:0] mclk_cnt;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            mclk_cnt <= 0;
            m_clk    <= 1'b0;
        end else begin
            if (mclk_cnt == MCLK_DIV - 1) begin
                mclk_cnt <= 0;
                m_clk    <= ~m_clk;
            end else begin
                mclk_cnt <= mclk_cnt + 1;
            end
        end
    end

    reg m_clk_d;
    wire m_clk_rise;

    always @(posedge clk) begin
        m_clk_d <= m_clk;
    end
    assign m_clk_rise = m_clk && !m_clk_d;

    reg [6:0] bit_cnt;
    reg [7:0] ones_cnt;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            bit_cnt      <= 0;
            ones_cnt     <= 0;
            pcm_sample   <= 8'd64;
            sample_valid <= 1'b0;
        end else begin
            sample_valid <= 1'b0;

            if (m_clk_rise) begin
                ones_cnt <= ones_cnt + {7'b0, m_data};
                bit_cnt  <= bit_cnt + 1;

                if (bit_cnt == WINDOW - 1) begin
                    pcm_sample   <= ones_cnt + {7'b0, m_data};
                    sample_valid <= 1'b1;
                    bit_cnt      <= 0;
                    ones_cnt     <= 0;
                end
            end
        end
    end

endmodule
