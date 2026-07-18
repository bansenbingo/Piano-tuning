`timescale 1ns / 1ps

module tb_mic_recorder;

    reg         CLK100MHZ;
    reg         CPU_RESETN;
    reg         SW_0;
    reg         SW_1;
    wire        M_CLK;
    wire        M_LRSEL;
    wire        M_DATA;
    wire        AUD_PWM;
    wire        AUD_SD;
    wire [15:0] LED;

    mic_recorder u_dut (
        .CLK100MHZ (CLK100MHZ),
        .CPU_RESETN(CPU_RESETN),
        .SW_0      (SW_0),
        .SW_1      (SW_1),
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
        SW_1        = 1'b0;
        sine_phase  = 0.0;
        sd_integrator = 0;
        pdm_bit     = 1'b0;

        #200;
        CPU_RESETN = 1'b1;
        #500;

        repeat(600000) @(posedge CLK100MHZ);

        SW_0 = 1'b1;
        repeat(12000000) @(posedge CLK100MHZ);

        SW_0 = 1'b0;
        #50000;

        SW_1 = 1'b1;
        repeat(60000000) @(posedge CLK100MHZ);

        SW_1 = 1'b0;
        #100000;

        SW_0 = 1'b1;
        repeat(8000000) @(posedge CLK100MHZ);

        SW_0 = 1'b0;
        #100000;

        SW_1 = 1'b1;
        repeat(60000000) @(posedge CLK100MHZ);

        SW_1 = 1'b0;
        #50000;

        $finish;
    end

endmodule
