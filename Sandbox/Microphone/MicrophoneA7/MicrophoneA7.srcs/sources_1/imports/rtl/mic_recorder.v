module mic_recorder #(
    parameter integer SWITCH_DEBOUNCE_CYCLES = 1000000
) (
    input  wire        CLK100MHZ,
    input  wire        CPU_RESETN,
    input  wire        SW_0,
    input  wire        SW_15,
    input  wire        M_DATA,
    output wire        M_CLK,
    output wire        M_LRSEL,
    output wire        AUD_PWM,
    output wire        AUD_SD,
    output reg  [15:0] LED
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

    localparam IDLE     = 2'd0;
    localparam RECORD   = 2'd1;
    localparam PLAYBACK = 2'd2;

    reg [1:0] state;
    reg [1:0] next_state;

    // 64 KiB holds about 3.36 s at the 19.531 kHz PCM sample rate.
    localparam BUF_DEPTH = 65536;
    localparam ADDR_W    = $clog2(BUF_DEPTH);

    localparam DEBOUNCE_W = $clog2(SWITCH_DEBOUNCE_CYCLES + 1);

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

    wire record_start;
    wire play_start;
    assign record_start = sw_0_debounced && !sw_0_debounced_d;
    assign play_start   = sw_15_debounced && !sw_15_debounced_d;

    wire                buf_we;
    wire [ADDR_W-1:0]   buf_addr;
    wire [7:0]          buf_din;
    wire [7:0]          buf_dout;

    reg  [ADDR_W:0]     record_count;
    reg  [ADDR_W:0]     play_count;
    wire                buf_full;
    wire                recorded_data_available;

    assign buf_full  = (record_count == BUF_DEPTH);
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
                                        : play_count[ADDR_W-1:0];
    assign buf_we   = (state == RECORD) && sample_valid && !buf_full;
    assign buf_din  = pcm_sample;

    always @(posedge CLK100MHZ) begin
        if (rst) begin
            record_count <= 0;
        end else if ((state == IDLE) && record_start) begin
            // A new SW[0] assertion always starts a fresh recording, including
            // after the preceding recording filled the buffer.
            record_count <= 0;
        end else if (state == RECORD) begin
            if (sample_valid && !buf_full)
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
            // play_count addresses the sample held at the PWM input.  Advance
            // only after its entire sample period has elapsed.
            if (sample_tick && (play_count != record_count))
                play_count <= play_count + 1;
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
            end
            RECORD: begin
                if (!sw_0_debounced || buf_full)
                    next_state = IDLE;
            end
            PLAYBACK: begin
                // End playback on the tick after the final sample was output,
                // not when that final sample first reaches the PWM input.
                if (!sw_15_debounced ||
                    (sample_tick && (play_count == record_count - 1'b1)))
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
        LED[0]  = (state == RECORD);             // Recording active.
        LED[15] = (state == PLAYBACK);           // Playback active.

        if (state == IDLE) begin
            LED[1] = recorded_data_available;    // A recording is ready.
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

    // Nexys A7 pulls AUD_PWM up on the analog board.  Release the pin for a
    // logical high and only drive it low, as required by the audio interface.
    assign AUD_PWM = ((state == PLAYBACK) && (pwm_cnt < pwm_duty)) ? 1'bz : 1'b0;

    assign AUD_SD = (state == PLAYBACK);

endmodule
