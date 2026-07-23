// 仿真时间单位1ns，精度1ps
`timescale 1ns / 1ps

// 麦克风录音回放设计测试平台
module tb_mic_recorder;

    // 系统时钟和复位信号
    reg         CLK100MHZ;
    reg         CPU_RESETN;
    // 控制开关：SW_0启动录音，SW_15启动回放
    reg         SW_0;
    reg         SW_15;
    // 麦克风接口信号
    wire        M_CLK;
    wire        M_LRSEL;
    wire        M_DATA;
    // 音频输出信号
    wire        AUD_PWM;
    wire        AUD_SD;
    // 状态指示LED
    wire [15:0] LED;

    // 实例化被测设计，使用较短的消抖周期以加速仿真
    mic_recorder #(
        .SWITCH_DEBOUNCE_CYCLES(4)
    ) u_dut (
        .CLK100MHZ (CLK100MHZ),
        .CPU_RESETN(CPU_RESETN),
        .SW_0      (SW_0),
        .SW_15     (SW_15),
        .M_DATA    (M_DATA),
        .M_CLK     (M_CLK),
        .M_LRSEL   (M_LRSEL),
        .AUD_PWM   (AUD_PWM),
        .AUD_SD    (AUD_SD),
        .LED       (LED)
    );

    // 生成100MHz系统时钟，周期10ns
    always #5 CLK100MHZ = ~CLK100MHZ;

    // PDM麦克风信号模拟：500Hz正弦波
    real       sine_phase;
    real       sine_val;
    integer    sd_integrator;
    reg        pdm_bit;

    // 每个麦克风时钟上升沿更新PDM输出
    always @(posedge M_CLK) begin
        // 500Hz正弦波相位推进，采样率2.5MHz
        sine_phase = sine_phase + 2.0 * 3.1415926535 * 500.0 / 2500000.0;
        if (sine_phase > 2.0 * 3.1415926535)
            sine_phase = sine_phase - 2.0 * 3.1415926535;
        // 正弦波：中心值64，振幅32
        sine_val = 64.0 + 32.0 * $sin(sine_phase);

        // 一阶Sigma-Delta调制
        sd_integrator = sd_integrator + $rtoi(sine_val) - (pdm_bit ? 128 : 0);
        pdm_bit = (sd_integrator > 0) ? 1'b1 : 1'b0;
    end

    // 将PDM位流连接到被测设计的麦克风数据输入
    assign M_DATA = pdm_bit;

    // 测试流程：复位、录音、回放验证
    initial begin
        // 生成波形文件用于调试
        $dumpfile("tb_mic_recorder.vcd");
        $dumpvars(0, tb_mic_recorder);

        // 初始化所有信号
        CLK100MHZ   = 1'b0;
        CPU_RESETN  = 1'b0;
        SW_0        = 1'b0;
        SW_15       = 1'b0;
        sine_phase  = 0.0;
        sd_integrator = 0;
        pdm_bit     = 1'b0;

        // 释放复位
        repeat(2) @(posedge CLK100MHZ);
        CPU_RESETN = 1'b1;

        // 启动录音，持续足够长时间以产生多个PCM样本
        SW_0 = 1'b1;
        repeat(100000) @(posedge CLK100MHZ);

        // 停止录音
        SW_0 = 1'b0;
        repeat(10) @(posedge CLK100MHZ);

        // 验证录音产生了PCM样本
        if (u_dut.record_count == 0)
            $fatal(1, "No PCM samples were recorded");
        // 验证空闲状态LED指示录音就绪
        if (LED[0] !== 1'b0 || LED[1] !== 1'b1)
            $fatal(1, "Idle LEDs do not indicate a recording is ready");

        // 启动回放，等待音频放大器使能
        SW_15 = 1'b1;
        wait (AUD_SD === 1'b1);
        // 验证回放状态LED点亮
        if (LED[15] !== 1'b1)
            $fatal(1, "Playback status LED did not turn on");

        // 等待回放完成
        repeat(100000) @(posedge CLK100MHZ);
        // 验证回放消耗了所有录音样本
        if (u_dut.play_count != u_dut.record_count)
            $fatal(1, "Playback did not consume every recorded sample");
        // 验证回放结束后放大器关闭
        if (AUD_SD !== 1'b0)
            $fatal(1, "Playback did not stop at the end of the recording");

        // 释放回放开关，准备后续操作
        SW_15 = 1'b0;
        repeat(10) @(posedge CLK100MHZ);

        // 仿真结束
        $finish;
    end

endmodule