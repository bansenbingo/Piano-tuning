// Nexys A7 PDM 麦克风录音、回放与 UART 数据传输顶层。
// 录音数据在 PC 端接收操作参见本文件末尾注释。
//
// 功能：
//   1. SW[0] 上拨开始录音，下拨停止录音；最长录制约 10 秒后自动停止。
//   2. SW[15] 上拨启动回放，下拨停止回放或播完自动停止。
//   3. 按动 BTNC（中央按钮）将全部已录音数据通过 UART 发送到计算机。
//
// 数据路径：
//   M_DATA -> pdm_decoder -> audio_buffer -> PWM/AUD_PWM（回放）
//                                          -> uart_tx -> UART_TXD（传输）
//
// 所有时序逻辑位于 100 MHz 系统时钟域。
module mic_recorder #(
    parameter integer SWITCH_DEBOUNCE_CYCLES = 1000000,
    parameter integer BTN_DEBOUNCE_CYCLES    = 1000000
) (
    input  wire        CLK100MHZ,
    input  wire        CPU_RESETN,
    input  wire        SW_0,
    input  wire        SW_15,
    input  wire        BTNC,
    input  wire        M_DATA,
    output wire        M_CLK,
    output wire        M_LRSEL,
    output wire        AUD_PWM,
    output wire        AUD_SD,
    output reg  [15:0] LED,
    output wire        UART_TXD
);

    wire rst;
    assign rst = ~CPU_RESETN;

    wire [7:0] pcm_sample;
    wire       sample_valid;

    pdm_decoder u_pdm_decoder (
        .clk          (CLK100MHZ),
        .rst          (rst),
        .m_data       (M_DATA),
        .m_clk        (M_CLK),
        .m_lrsel      (M_LRSEL),
        .pcm_sample   (pcm_sample),
        .sample_valid (sample_valid)
    );

    localparam IDLE     = 3'd0;
    localparam RECORD   = 3'd1;
    localparam PLAYBACK = 3'd2;
    localparam SEND     = 3'd3;

    reg [2:0] state;
    reg [2:0] next_state;

    // 19,531.25 Hz 采样率下约 10 秒 = 195,313 个样本。
    // 音频缓存容量 262,144 x 8 bit（2^18），确保 10 秒录音有足够空间。
    localparam BUF_DEPTH   = 262144;
    localparam MAX_SAMPLES = 195313;
    localparam ADDR_W      = $clog2(BUF_DEPTH);

    localparam DEBOUNCE_W = $clog2(SWITCH_DEBOUNCE_CYCLES + 1);
    localparam BTN_DEBOUNCE_W = $clog2(BTN_DEBOUNCE_CYCLES + 1);

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

    // BTNC 去抖相关信号
    reg btnc_meta;
    reg btnc_sync;
    reg btnc_debounced;
    reg btnc_debounced_d;
    reg [BTN_DEBOUNCE_W-1:0] btnc_debounce_count;

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

    // BTNC 同步与去抖
    always @(posedge CLK100MHZ) begin
        if (rst) begin
            btnc_meta   <= 1'b0;
            btnc_sync   <= 1'b0;
        end else begin
            btnc_meta   <= BTNC;
            btnc_sync   <= btnc_meta;
        end
    end

    always @(posedge CLK100MHZ) begin
        if (rst) begin
            btnc_debounced       <= 1'b0;
            btnc_debounced_d     <= 1'b0;
            btnc_debounce_count  <= 0;
        end else begin
            btnc_debounced_d <= btnc_debounced;

            if (btnc_sync == btnc_debounced) begin
                btnc_debounce_count <= 0;
            end else if (btnc_debounce_count == BTN_DEBOUNCE_CYCLES - 1) begin
                btnc_debounced      <= btnc_sync;
                btnc_debounce_count <= 0;
            end else begin
                btnc_debounce_count <= btnc_debounce_count + 1'b1;
            end
        end
    end

    wire record_start;
    wire play_start;
    wire send_start;
    assign record_start = sw_0_debounced && !sw_0_debounced_d;
    assign play_start   = sw_15_debounced && !sw_15_debounced_d;
    assign send_start   = btnc_debounced && !btnc_debounced_d;

    wire                buf_we;
    wire [ADDR_W-1:0]   buf_addr;
    wire [7:0]          buf_din;
    wire [7:0]          buf_dout;

    reg  [ADDR_W:0]     record_count;
    reg  [ADDR_W:0]     play_count;
    wire                buf_full;
    wire                max_samples_reached;
    wire                recorded_data_available;

    assign buf_full  = (record_count == BUF_DEPTH);
    assign max_samples_reached = (record_count == MAX_SAMPLES);
    assign recorded_data_available = (record_count != 0);

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

    assign buf_addr = (state == RECORD) ? record_count[ADDR_W-1:0]
                   : (state == SEND)   ? send_count[ADDR_W-1:0]
                                       : play_count[ADDR_W-1:0];
    assign buf_we   = (state == RECORD) && sample_valid && !buf_full && !max_samples_reached;
    assign buf_din  = pcm_sample;

    always @(posedge CLK100MHZ) begin
        if (rst) begin
            record_count <= 0;
        end else if ((state == IDLE) && record_start) begin
            record_count <= 0;
        end else if (state == RECORD) begin
            if (sample_valid && !buf_full && !max_samples_reached)
                record_count <= record_count + 1;
        end
    end

    localparam SAMPLE_PERIOD = 5120;
    reg [12:0] sample_timer;
    wire       sample_tick;

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

    // ---------- UART 发送子模块与 SEND 控制 ----------

    wire       uart_busy;
    reg        uart_send;
    reg [7:0]  send_byte_data;

    uart_tx #(
        .CLK_FREQ(100_000_000),
        .BAUD(921_600)
    ) u_uart_tx (
        .clk  (CLK100MHZ),
        .rst  (rst),
        .data (send_byte_data),
        .send (uart_send),
        .busy (uart_busy),
        .tx   (UART_TXD)
    );

    reg [ADDR_W:0] send_count;
    reg            send_issued;
    reg            send_done;
    reg            send_startup;

    always @(posedge CLK100MHZ) begin
        if (rst) begin
            send_count  <= 0;
            send_issued <= 0;
            uart_send   <= 0;
            send_done   <= 0;
            send_startup <= 0;
        end else if ((state == IDLE) && send_start && recorded_data_available) begin
            send_count  <= 0;
            send_issued <= 0;
            uart_send   <= 0;
            send_done   <= 0;
            send_startup <= 1;
        end else if (state == SEND) begin
            uart_send <= 0;

            if (send_startup) begin
                send_startup <= 0;
            end else if (!send_issued) begin
                if (!uart_busy) begin
                    uart_send      <= 1;
                    send_issued    <= 1;
                    send_byte_data <= buf_dout;
                end
            end else begin
                if (!uart_busy) begin
                    if (send_count == record_count - 1'b1) begin
                        send_done <= 1;
                    end else begin
                        // 地址推进后需等待一拍，让 audio_buffer 的寄存读输出更新
                        send_count   <= send_count + 1;
                        send_issued  <= 0;
                        send_startup <= 1;
                    end
                end
            end
        end else begin
            send_count  <= 0;
            send_issued <= 0;
            uart_send   <= 0;
            send_done   <= 0;
            send_startup <= 0;
        end
    end

    always @(posedge CLK100MHZ) begin
        if (rst)
            state <= IDLE;
        else
            state <= next_state;
    end

    always @(*) begin
        next_state = state;
        case (state)
            IDLE: begin
                if (record_start)
                    next_state = RECORD;
                else if (play_start && recorded_data_available)
                    next_state = PLAYBACK;
                else if (send_start && recorded_data_available)
                    next_state = SEND;
            end
            RECORD: begin
                if (!sw_0_debounced || buf_full || max_samples_reached)
                    next_state = IDLE;
            end
            PLAYBACK: begin
                if (!sw_15_debounced ||
                    (sample_tick && (play_count == record_count - 1'b1)))
                    next_state = IDLE;
            end
            SEND: begin
                if (send_done)
                    next_state = IDLE;
            end
            default: next_state = IDLE;
        endcase
    end

    wire signed [8:0] signed_sample;
    wire [7:0] amplitude;
    wire [15:0] vu_leds;

    wire [7:0] display_sample;
    assign display_sample = (state == PLAYBACK) ? buf_dout : pcm_sample;

    assign signed_sample = {1'b0, display_sample} - 9'd64;

    assign amplitude = signed_sample[8]
        ? (~signed_sample[7:0] + 1'b1)
        : signed_sample[7:0];

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

    always @(*) begin
        LED = 16'h0000;
        LED[0]  = (state == RECORD);
        LED[15] = (state == PLAYBACK);
        LED[14] = (state == SEND);

        if (state == IDLE) begin
            LED[1] = recorded_data_available;
        end else if (state == SEND) begin
        end else begin
            LED[14:1] = vu_leds[13:0];
        end
    end

    reg [7:0] pwm_cnt;
    always @(posedge CLK100MHZ or posedge rst) begin
        if (rst)
            pwm_cnt <= 0;
        else
            pwm_cnt <= pwm_cnt + 1;
    end

    wire [7:0] pwm_sample;
    assign pwm_sample = (state == PLAYBACK) ? buf_dout : 8'd64;

    wire [7:0] pwm_duty;
    assign pwm_duty = pwm_sample + 8'd64;

    assign AUD_PWM = ((state == PLAYBACK) && (pwm_cnt < pwm_duty)) ? 1'bz : 1'b0;

    assign AUD_SD = (state == PLAYBACK);

endmodule


// PC 端接收录音数据操作指南
// =========================
//
// 硬件连接：
//   将 Nexys A7 的 PROG USB 口（J6）通过 USB 线连接计算机。
//   Windows 通常自动安装 FTDI VCP 驱动，设备管理器中出现 COM 端口。
//
// 串口参数：
//   波特率 921,600 bps / 8 数据位 / 1 停止位 / 无校验 / 无流控
//
// 数据格式：
//   A7 发送的每个字节是 8 bit 无符号 PCM 样本（PDM 计数器值 0-128，静音≈64）。
//   采样率 19,531.25 Hz（100 MHz / 5120），单声道。
//   总共发送 record_count 个字节（≤ 195,313，约 10 秒）。
//
// Python 接收脚本（将 raw 数据保存并转为 WAV）：
//
//   import serial
//   import wave
//   import struct
//
//   PORT = "COM3"          # 根据设备管理器修改
//   BAUD = 921600
//   OUT_RAW  = r"Z:\Piano-tuning\Sandbox\Microphone\recording.raw"
//   OUT_WAV  = r"Z:\Piano-tuning\Sandbox\Microphone\recording.wav"
//   SAMPLE_RATE = 19531
//
//   ser = serial.Serial(PORT, BAUD, timeout=3)
//   print("等待 FPGA 传输...")
//
//   raw_data = bytearray()
//   while True:
//       chunk = ser.read(4096)
//       if not chunk:
//           break
//       raw_data.extend(chunk)
//
//   ser.close()
//   print(f"收到 {len(raw_data)} 字节")
//
//   with open(OUT_RAW, "wb") as f:
//       f.write(raw_data)
//   print(f"原始数据已保存至 {OUT_RAW}")
//
//   with wave.open(OUT_WAV, "wb") as wav:
//       wav.setnchannels(1)
//       wav.setsampwidth(1)
//       wav.setframerate(SAMPLE_RATE)
//       for sample in raw_data:
//           wav.writeframesraw(struct.pack("B", sample))
//   print(f"WAV 文件已保存至 {OUT_WAV}")
//
// 也可用任意串口终端工具（PuTTY、Tera Term 等）捕获原始字节流后手动处理。
