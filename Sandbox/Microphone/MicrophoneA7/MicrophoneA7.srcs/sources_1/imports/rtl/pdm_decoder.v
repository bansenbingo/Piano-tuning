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

    localparam MCLK_DIV           = 20;
    localparam M_DATA_SAMPLE_DELAY = 8;
    localparam WINDOW             = 128;

    reg [5:0] mclk_cnt;

    always @(posedge clk) begin
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

    reg [1:0] m_data_sync;

    always @(posedge clk) begin
        if (rst)
            m_data_sync <= 2'b00;
        else
            m_data_sync <= {m_data_sync[0], m_data};
    end

    // M_DATA is launched by the microphone after M_CLK rises.  Sample it well
    // inside M_CLK's high phase, rather than one 100 MHz cycle after the edge.
    wire m_data_sample;
    assign m_data_sample = m_clk && (mclk_cnt == M_DATA_SAMPLE_DELAY - 1);

    reg [6:0] bit_cnt;
    reg [7:0] ones_cnt;

    always @(posedge clk) begin
        if (rst) begin
            bit_cnt      <= 0;
            ones_cnt     <= 0;
            pcm_sample   <= 8'd64;
            sample_valid <= 1'b0;
        end else begin
            sample_valid <= 1'b0;

            if (m_data_sample) begin
                ones_cnt <= ones_cnt + {7'b0, m_data_sync[1]};
                bit_cnt  <= bit_cnt + 1;

                if (bit_cnt == WINDOW - 1) begin
                    pcm_sample   <= ones_cnt + {7'b0, m_data_sync[1]};
                    sample_valid <= 1'b1;
                    bit_cnt      <= 0;
                    ones_cnt     <= 0;
                end
            end
        end
    end

endmodule
