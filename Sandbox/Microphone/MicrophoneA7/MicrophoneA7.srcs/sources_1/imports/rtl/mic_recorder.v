// Nexys A7 板载 PDM 麦克风录音与一次性回放顶层。
//
// 数据路径：M_DATA -> pdm_decoder -> audio_buffer -> PWM/AUD_PWM。
// 控制方式：SW_0 的去抖上升沿开始新录音；SW_15 的去抖上升沿开始
// 回放已录数据。所有时序逻辑均位于 100 MHz 系统时钟域。
module mic_recorder #(
    // 开关输入需连续稳定的系统时钟周期数；默认 1,000,000 周期即 10 ms。
    parameter integer SWITCH_DEBOUNCE_CYCLES = 1000000
) (
    input  wire        CLK100MHZ,  // Nexys A7 板载 100 MHz 时钟。
    input  wire        CPU_RESETN, // 低有效复位按钮输入。
    input  wire        SW_0,       // SW[0]：录音请求开关。
    input  wire        SW_15,      // SW[15]：播放请求开关。
    input  wire        M_DATA,     // 板载 MEMS 麦克风输出的 1 bit PDM 数据。
    output wire        M_CLK,      // FPGA 输出给麦克风的 2.5 MHz PDM 时钟。
    output wire        M_LRSEL,    // 麦克风数据边沿选择，固定为低。
    output wire        AUD_PWM,    // 开漏式 PWM 音频输出。
    output wire        AUD_SD,     // 板载音频通道使能，高电平表示播放中。
    output reg  [15:0] LED         // 录音/播放状态和瞬时音量显示。
);

    // 内部统一使用高有效复位，便于子模块和时序逻辑判断。
    wire rst;
    assign rst = ~CPU_RESETN;

    // PDM 解码后的无符号样本：理论范围为 0 到 128，静音中心约为 64。
    wire [7:0] pcm_sample;
    // 每收集 128 个 PDM bit 时有效一个 CLK100MHZ 周期的样本写入脉冲。
    wire       sample_valid;

    // 持续生成麦克风时钟并完成 PDM 的积分-清零抽取；
    // 解码器不受录音/播放状态限制，以保证随时可显示当前音量。
    pdm_decoder u_pdm_decoder (
        .clk          (CLK100MHZ),
        .rst          (rst),
        .m_data       (M_DATA),
        .m_clk        (M_CLK),
        .m_lrsel      (M_LRSEL),
        .pcm_sample   (pcm_sample),
        .sample_valid (sample_valid)
    );

    // 三态录放控制状态编码。
    localparam IDLE     = 2'd0; // 空闲：等待一次新的录音或播放请求。
    localparam RECORD   = 2'd1; // 录音：把有效 PCM 样本写入片上缓存。
    localparam PLAYBACK = 2'd2; // 回放：按原采样率读取缓存并驱动 PWM。

    // state 为当前状态寄存器，next_state 为组合逻辑计算的下一状态。
    reg [1:0] state;
    reg [1:0] next_state;

    // 64 KiB 缓存可在 19.531 kHz 采样率下保存约 3.36 s 的 8 bit 音频。
    localparam BUF_DEPTH = 65536;
    // 缓存地址宽度为 16 bit；计数器额外保留 1 bit 用于表示“已满”。
    localparam ADDR_W    = $clog2(BUF_DEPTH);

    // 去抖计数器位宽，需能计到 SWITCH_DEBOUNCE_CYCLES - 1。
    localparam DEBOUNCE_W = $clog2(SWITCH_DEBOUNCE_CYCLES + 1);

    // 两级同步器和去抖状态：
    // meta/sync 将异步机械开关输入同步到 100 MHz 域；
    // debounced 保存稳定后的电平；debounced_d 用于检测其上升沿；
    // debounce_count 统计输入与稳定状态不同的连续周期数。
    reg sw_0_meta;
    reg sw_0_sync;
    reg sw_0_debounced;
    reg sw_0_debounced_d;
    reg [DEBOUNCE_W-1:0] sw_0_debounce_count;
    reg sw_15_meta;
    reg sw_15_sync;
    reg sw_15_debounced;
    reg sw_15_debounced_d;
    reg [DEBOUNCE_W-1:0] sw_15_debounce_count;

    // 将两个物理开关分别经过两级触发器同步，降低亚稳态传播风险。
    always @(posedge CLK100MHZ) begin
        if (rst) begin
            sw_0_meta   <= 1'b0;
            sw_0_sync   <= 1'b0;
            sw_15_meta   <= 1'b0;
            sw_15_sync   <= 1'b0;
        end else begin
            sw_0_meta   <= SW_0;
            sw_0_sync   <= sw_0_meta;
            sw_15_meta   <= SW_15;
            sw_15_sync   <= sw_15_meta;
        end
    end

    // 两路独立去抖：只有输入连续稳定足够长时间，才接受新的开关电平。
    // 同时延迟一拍去抖结果，为后续产生一次性的上升沿启动脉冲。
    always @(posedge CLK100MHZ) begin
        if (rst) begin
            sw_0_debounced       <= 1'b0;
            sw_0_debounced_d     <= 1'b0;
            sw_0_debounce_count  <= 0;
            sw_15_debounced      <= 1'b0;
            sw_15_debounced_d    <= 1'b0;
            sw_15_debounce_count <= 0;
        end else begin
            sw_0_debounced_d  <= sw_0_debounced;
            sw_15_debounced_d <= sw_15_debounced;

            if (sw_0_sync == sw_0_debounced) begin
                sw_0_debounce_count <= 0;
            end else if (sw_0_debounce_count == SWITCH_DEBOUNCE_CYCLES - 1) begin
                sw_0_debounced      <= sw_0_sync;
                sw_0_debounce_count <= 0;
            end else begin
                sw_0_debounce_count <= sw_0_debounce_count + 1'b1;
            end

            if (sw_15_sync == sw_15_debounced) begin
                sw_15_debounce_count <= 0;
            end else if (sw_15_debounce_count == SWITCH_DEBOUNCE_CYCLES - 1) begin
                sw_15_debounced      <= sw_15_sync;
                sw_15_debounce_count <= 0;
            end else begin
                sw_15_debounce_count <= sw_15_debounce_count + 1'b1;
            end
        end
    end

    // 去抖后开关的上升沿。它们是单周期脉冲，而非持续的开关电平。
    wire record_start;
    wire play_start;
    assign record_start = sw_0_debounced && !sw_0_debounced_d;
    assign play_start   = sw_15_debounced && !sw_15_debounced_d;

    // audio_buffer 的单端口接口：写入录音样本或读取回放样本。
    wire                buf_we;   // 写使能，仅录音且 PCM 样本有效时置位。
    wire [ADDR_W-1:0]   buf_addr; // 当前读/写地址，由状态选择录音或播放计数。
    wire [7:0]          buf_din;  // 写入 RAM 的当前 PCM 样本。
    wire [7:0]          buf_dout; // RAM 同步读出的、用于回放的 PCM 样本。

    // 已写入和已播放的样本数量。额外的最高位允许数值精确到 BUF_DEPTH。
    reg  [ADDR_W:0]     record_count;
    reg  [ADDR_W:0]     play_count;
    // 缓存状态标志：满时禁止继续写入；非零时允许启动播放。
    wire                buf_full;
    wire                recorded_data_available;

    assign buf_full  = (record_count == BUF_DEPTH);
    assign recorded_data_available = (record_count != 0);

    // 单端口同步 RAM：录音状态使用 record_count 写入，其他状态使用
    // play_count 读取。录音与回放不会并发进行，因此无需双端口 RAM。
    audio_buffer #(
        .DEPTH(BUF_DEPTH),
        .WIDTH(8)
    ) u_audio_buffer (
        .clk  (CLK100MHZ),
        .we   (buf_we),
        .addr (buf_addr),
        .din  (buf_din),
        .dout (buf_dout)
    );

    // 复用 RAM 地址端口；录音时取下一个写地址，非录音时取当前播放地址。
    assign buf_addr = (state == RECORD) ? record_count[ADDR_W-1:0]
                                        : play_count[ADDR_W-1:0];
    // sample_valid 以 PCM 采样率出现，避免把 2.5 MHz 的每个 PDM bit 写入 RAM。
    assign buf_we   = (state == RECORD) && sample_valid && !buf_full;
    assign buf_din  = pcm_sample;

    // 记录有效样本总数。新的 SW[0] 上升沿总会重新从地址 0 录音，
    // 无需物理清零 RAM；新的 record_count 定义了本次录音的有效长度。
    always @(posedge CLK100MHZ) begin
        if (rst) begin
            record_count <= 0;
        end else if ((state == IDLE) && record_start) begin
            // 即使上一段录音填满了缓存，也允许本次录音覆盖旧数据。
            record_count <= 0;
        end else if (state == RECORD) begin
            if (sample_valid && !buf_full)
                record_count <= record_count + 1;
        end
    end

    // 回放样本保持周期：5120 / 100 MHz = 51.2 us，对应 19.53125 kHz。
    localparam SAMPLE_PERIOD = 5120;
    // sample_timer 仅在回放中递增；计满时产生一次样本切换节拍。
    reg [12:0] sample_timer;
    wire       sample_tick;

    // 生成播放采样节拍。离开 PLAYBACK 时清零，使下次回放从完整周期开始。
    always @(posedge CLK100MHZ) begin
        if (rst) begin
            sample_timer <= 0;
        end else begin
            if (state == PLAYBACK) begin
                if (sample_timer == SAMPLE_PERIOD - 1)
                    sample_timer <= 0;
                else
                    sample_timer <= sample_timer + 1;
            end else begin
                sample_timer <= 0;
            end
        end
    end
    assign sample_tick = (sample_timer == SAMPLE_PERIOD - 1);

    // 播放计数器指定当前保持在 PWM 输入端的缓存样本。只在一个完整
    // 样本周期结束后前进，保证每个录音样本被输出 SAMPLE_PERIOD 个时钟周期。
    always @(posedge CLK100MHZ) begin
        if (rst) begin
            play_count <= 0;
        end else if ((state == IDLE) && play_start && recorded_data_available) begin
            play_count <= 0;
        end else if (state == PLAYBACK) begin
            if (sample_tick && (play_count != record_count))
                play_count <= play_count + 1;
        end
    end

    // 当前状态寄存器：在每个系统时钟沿装载组合逻辑给出的下一状态。
    always @(posedge CLK100MHZ) begin
        if (rst)
            state <= IDLE;
        else
            state <= next_state;
    end

    // 状态机组合逻辑。录音优先于播放；播放最后一个样本的整个周期后
    // 才退出，避免最后一个 PCM 样本刚进入 PWM 时就被截断。
    always @(*) begin
        next_state = state;
        case (state)
            IDLE: begin
                if (record_start)
                    next_state = RECORD;
                else if (play_start && recorded_data_available)
                    next_state = PLAYBACK;
            end
            RECORD: begin
                if (!sw_0_debounced || buf_full)
                    next_state = IDLE;
            end
            PLAYBACK: begin
                if (!sw_15_debounced ||
                    (sample_tick && (play_count == record_count - 1'b1)))
                    next_state = IDLE;
            end
            default: next_state = IDLE;
        endcase
    end

    // LED 音量计算：把无符号 PDM 计数值转为以 64 为零点的有符号量，
    // 再取绝对值得到与声音极性无关的瞬时幅度。
    wire signed [8:0] signed_sample;
    wire [7:0] amplitude;
    wire [15:0] vu_leds;

    // 录音/空闲时显示实时麦克风值，回放时显示当前缓存样本。
    wire [7:0] display_sample;
    assign display_sample = (state == PLAYBACK) ? buf_dout : pcm_sample;

    assign signed_sample = {1'b0, display_sample} - 9'd64;

    // 二进制补码绝对值：signed_sample[8] 为 1 时表示负幅度。
    assign amplitude = signed_sample[8]
        ? (~signed_sample[7:0] + 1'b1)
        : signed_sample[7:0];

    // 16 级幅度阈值。顶层实际使用 vu_leds[13:0]，因为 LED[0] 和
    // LED[15] 分别保留给录音和播放状态指示。
    assign vu_leds[0]  = (amplitude >  0);
    assign vu_leds[1]  = (amplitude >  4);
    assign vu_leds[2]  = (amplitude >  8);
    assign vu_leds[3]  = (amplitude > 12);
    assign vu_leds[4]  = (amplitude > 16);
    assign vu_leds[5]  = (amplitude > 20);
    assign vu_leds[6]  = (amplitude > 24);
    assign vu_leds[7]  = (amplitude > 28);
    assign vu_leds[8]  = (amplitude > 32);
    assign vu_leds[9]  = (amplitude > 36);
    assign vu_leds[10] = (amplitude > 40);
    assign vu_leds[11] = (amplitude > 44);
    assign vu_leds[12] = (amplitude > 48);
    assign vu_leds[13] = (amplitude > 52);
    assign vu_leds[14] = (amplitude > 56);
    assign vu_leds[15] = (amplitude > 60);

    // LED 复用显示：LED[0] 指示录音，LED[15] 指示播放；空闲且存在
    // 有效录音时 LED[1] 点亮。活动状态下 LED[14:1] 显示音量条。
    always @(*) begin
        LED = 16'h0000;
        LED[0]  = (state == RECORD);             // 当前处于录音状态。
        LED[15] = (state == PLAYBACK);           // 当前处于回放状态。

        if (state == IDLE) begin
            LED[1] = recorded_data_available;    // 已有录音可供播放。
        end else begin
            LED[14:1] = vu_leds[13:0];
        end
    end

    // 8 bit 自由运行 PWM 载波计数器，频率为 100 MHz / 256 = 390.625 kHz。
    reg [7:0] pwm_cnt;
    always @(posedge CLK100MHZ or posedge rst) begin
        if (rst)
            pwm_cnt <= 0;
        else
            pwm_cnt <= pwm_cnt + 1;
    end

    // 回放时使用缓存样本；其他状态使用静音中心值，尽管此时 AUD_SD 已关闭。
    wire [7:0] pwm_sample;
    assign pwm_sample = (state == PLAYBACK) ? buf_dout : 8'd64;

    // 将 0 到 128 的 PDM 计数值偏移到 64 到 192，使静音值 64 对应 50% 占空比。
    wire [7:0] pwm_duty;
    assign pwm_duty = pwm_sample + 8'd64;

    // Nexys A7 模拟音频电路对 AUD_PWM 提供上拉，因此必须按开漏方式驱动：
    // 回放 PWM 的“高”区间释放为高阻态，其他时间只主动拉低；不能推挽输出高电平。
    assign AUD_PWM = ((state == PLAYBACK) && (pwm_cnt < pwm_duty)) ? 1'bz : 1'b0;

    // 仅在实际回放时使能板载音频通道，避免录音或空闲时输出声音。
    assign AUD_SD = (state == PLAYBACK);

endmodule
