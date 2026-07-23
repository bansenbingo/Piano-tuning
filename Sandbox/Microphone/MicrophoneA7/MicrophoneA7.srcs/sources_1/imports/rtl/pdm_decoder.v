// 将 Nexys A7 板载 MEMS 麦克风的 1 bit PDM 数据转换为低速 PCM 近似样本。
// 本模块从 100 MHz 系统时钟生成 2.5 MHz 的 M_CLK，并统计每 128 个 PDM bit
// 中“1”的数量。该统计值的理论范围为 0 到 128，静音中心约为 64。
module pdm_decoder (
    input  wire        clk,          // 100 MHz 系统时钟。
    input  wire        rst,          // 高有效同步复位。
    input  wire        m_data,       // 麦克风输出的 1 bit PDM 数据。
    output reg         m_clk,        // 输出给麦克风的 PDM 时钟。
    output wire        m_lrsel,      // 数据边沿选择：低电平对应上升沿有效。
    output reg  [7:0]  pcm_sample,   // 最近一个 128 bit 窗口的“1”计数。
    output reg         sample_valid  // pcm_sample 更新时的单周期有效脉冲。
);

    // 选择麦克风在 M_CLK 上升沿发送数据的模式。
    assign m_lrsel = 1'b0;

    // M_CLK 每 MCLK_DIV 个系统时钟翻转一次：100 MHz / (20 x 2) = 2.5 MHz。
    localparam MCLK_DIV            = 20;
    // M_CLK 上升沿后延迟的系统时钟周期数，在高电平中段采样稳定的 M_DATA。
    localparam M_DATA_SAMPLE_DELAY = 8;
    // 一个 PCM 输出样本累计的 PDM bit 数；同时决定抽取比和样本值满量程。
    localparam WINDOW              = 128;

    // M_CLK 半周期计数器，数到 MCLK_DIV - 1 后清零并翻转 m_clk。
    reg [5:0] mclk_cnt;

    // 产生占空比约为 50% 的麦克风工作时钟；复位时固定输出低电平。
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

    // M_DATA 由麦克风相对 M_CLK 产生，使用两级同步器减少其进入 100 MHz
    // 逻辑时发生亚稳态并向后级传播的风险。
    reg [1:0] m_data_sync;

    // 两级同步。m_data_sync[1] 是用于 PDM 统计的稳定数据版本。
    always @(posedge clk) begin
        if (rst)
            m_data_sync <= 2'b00;
        else
            m_data_sync <= {m_data_sync[0], m_data};
    end

    // 麦克风在 M_CLK 上升沿之后输出 M_DATA。因此不在紧邻边沿处采样，而是在
    // M_CLK 高电平中段产生一次采样使能，为数据传播和建立时间保留余量。
    wire m_data_sample;
    assign m_data_sample = m_clk && (mclk_cnt == M_DATA_SAMPLE_DELAY - 1);

    // bit_cnt 记录当前 128 bit 窗口内已采集的数据位数。
    // ones_cnt 累加窗口内的“1”数量，使用 8 bit 以表示最大值 128。
    reg [6:0] bit_cnt;
    reg [7:0] ones_cnt;

    // 对 PDM 数据执行积分-清零抽取：每个 m_data_sample 采一个 PDM bit；
    // 第 128 个 bit 到达时输出包含当前 bit 的总和，并清零计数器开始新窗口。
    // sample_valid 默认清零，因而只在窗口结束的一个系统时钟周期内有效。
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
