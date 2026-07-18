`timescale 1ns / 1ps

module tb_mic_recorder;

    reg         CLK100MHZ;
    reg         CPU_RESETN;
    reg         SW_0;
    reg         SW_15;
    wire        M_CLK;
    wire        M_LRSEL;
    wire        M_DATA;
    wire        AUD_PWM;
    wire        AUD_SD;
    wire [15:0] LED;

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

    always #5 CLK100MHZ = ~CLK100MHZ;

    real       sine_phase;
    real       sine_val;
    integer    sd_integrator;
    reg        pdm_bit;

    always @(posedge M_CLK) begin
        sine_phase = sine_phase + 2.0 * 3.1415926535 * 500.0 / 2500000.0;
        if (sine_phase > 2.0 * 3.1415926535)
            sine_phase = sine_phase - 2.0 * 3.1415926535;
        sine_val = 64.0 + 32.0 * $sin(sine_phase);

        sd_integrator = sd_integrator + $rtoi(sine_val) - (pdm_bit ? 128 : 0);
        pdm_bit = (sd_integrator > 0) ? 1'b1 : 1'b0;
    end

    assign M_DATA = pdm_bit;

    initial begin
        $dumpfile("tb_mic_recorder.vcd");
        $dumpvars(0, tb_mic_recorder);

        CLK100MHZ   = 1'b0;
        CPU_RESETN  = 1'b0;
        SW_0        = 1'b0;
        SW_15       = 1'b0;
        sine_phase  = 0.0;
        sd_integrator = 0;
        pdm_bit     = 1'b0;

        repeat(2) @(posedge CLK100MHZ);
        CPU_RESETN = 1'b1;

        SW_0 = 1'b1;
        // One PDM sample is produced every 5,120 system-clock cycles.  Record
        // long enough to cross multiple decimation windows.
        repeat(100000) @(posedge CLK100MHZ);

        SW_0 = 1'b0;
        repeat(10) @(posedge CLK100MHZ);

        if (u_dut.record_count == 0)
            $fatal(1, "No PCM samples were recorded");
        if (LED[0] !== 1'b0 || LED[1] !== 1'b1)
            $fatal(1, "Idle LEDs do not indicate a recording is ready");

        SW_15 = 1'b1;
        wait (AUD_SD === 1'b1);
        if (LED[15] !== 1'b1)
            $fatal(1, "Playback status LED did not turn on");

        // The recorded samples play at the same 19.531 kHz rate.
        repeat(100000) @(posedge CLK100MHZ);
        if (u_dut.play_count != u_dut.record_count)
            $fatal(1, "Playback did not consume every recorded sample");
        if (AUD_SD !== 1'b0)
            $fatal(1, "Playback did not stop at the end of the recording");

        // Playback is one-shot while SW[15] stays on.  Release it before a
        // subsequent playback request.
        SW_15 = 1'b0;
        repeat(10) @(posedge CLK100MHZ);

        $finish;
    end

endmodule
