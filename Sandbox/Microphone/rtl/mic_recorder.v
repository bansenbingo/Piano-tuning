module mic_recorder (
    input  wire        CLK100MHZ,
    input  wire        CPU_RESETN,
    input  wire        SW_0,
    input  wire        SW_1,
    input  wire        M_DATA,
    output wire        M_CLK,
    output wire        M_LRSEL,
    output reg         AUD_PWM,
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

    localparam BUF_DEPTH = 8192;
    localparam ADDR_W    = 13;

    wire                buf_we;
    wire [ADDR_W-1:0]   buf_addr;
    wire [7:0]          buf_din;
    wire [7:0]          buf_dout;

    reg  [ADDR_W:0]     record_count;
    reg  [ADDR_W:0]     play_count;
    wire                buf_full;
    wire                buf_empty;

    assign buf_full  = (record_count == BUF_DEPTH);
    assign buf_empty = (record_count == 0) || (play_count == record_count);

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

    always @(posedge CLK100MHZ or posedge rst) begin
        if (rst) begin
            record_count <= 0;
        end else if (state == RECORD) begin
            if (sample_valid && !buf_full)
                record_count <= record_count + 1;
        end else if (state == IDLE && SW_0 && !buf_full) begin
            record_count <= 0;
        end
    end

    always @(posedge CLK100MHZ or posedge rst) begin
        if (rst) begin
            play_count <= 0;
        end else if (state == PLAYBACK) begin
            if (sample_tick && !buf_empty)
                play_count <= play_count + 1;
        end else if (state == IDLE) begin
            play_count <= 0;
        end
    end

    localparam SAMPLE_PERIOD = 5120;
    reg [12:0] sample_timer;
    wire       sample_tick;

    always @(posedge CLK100MHZ or posedge rst) begin
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

    always @(posedge CLK100MHZ or posedge rst) begin
        if (rst)
            state <= IDLE;
        else
            state <= next_state;
    end

    always @(*) begin
        next_state = state;
        case (state)
            IDLE: begin
                if (SW_0 && !buf_full)
                    next_state = RECORD;
                else if (SW_1 && !buf_empty)
                    next_state = PLAYBACK;
            end
            RECORD: begin
                if (!SW_0 || buf_full)
                    next_state = IDLE;
            end
            PLAYBACK: begin
                if (!SW_1 || buf_empty)
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
        case (state)
            IDLE: begin
                if (record_count > 0)
                    LED = 16'h0001;
                else
                    LED = 16'h0000;
            end
            RECORD: begin
                LED = vu_leds;
            end
            PLAYBACK: begin
                LED = {1'b1, vu_leds[14:0]};
            end
            default: LED = 16'h0000;
        endcase
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

    always @(posedge CLK100MHZ or posedge rst) begin
        if (rst)
            AUD_PWM <= 1'b0;
        else
            AUD_PWM <= (pwm_cnt < pwm_duty);
    end

    assign AUD_SD = (state == PLAYBACK);

endmodule
