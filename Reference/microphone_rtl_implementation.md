# Nexys A7 麦克风录音 RTL 实现说明

本文档总结 `Sandbox/Microphone/rtl` 中三个 Verilog 源文件的实现逻辑：

```text
Sandbox/Microphone/rtl/
├── mic_recorder.v
├── pdm_decoder.v
└── audio_buffer.v
```

设计目标是使用 Nexys A7 板载 PDM 麦克风完成声音采样，将解码后的音频样本暂存到 FPGA 内部存储器，并通过板载 PWM 音频接口进行播放。

## 1. 系统总体结构

系统以 Nexys A7 的 `CLK100MHZ` 作为唯一系统时钟，频率为 100 MHz。整体数据流如下：

```text
板载 PDM 麦克风
       │
       ├── M_CLK：FPGA 输出约 2.5 MHz 麦克风时钟
       ├── M_LRSEL：固定为 0
       └── M_DATA：麦克风输出的 1 bit PDM 数据
                   │
                   ▼
             pdm_decoder
                   │
                   ├── pcm_sample：8 bit PCM 近似采样值
                   └── sample_valid：PCM 样本有效脉冲
                   │
                   ▼
             audio_buffer
                   │
             8192 × 8 bit 存储器
                   │
                   ▼
             PWM 音频播放
                   │
             AUD_PWM / AUD_SD
```

顶层模块 `mic_recorder` 负责控制录音、停止和播放，并负责把各个子模块连接起来。

## 2. 顶层模块 `mic_recorder`

### 2.1 接口功能

| 信号 | 方向 | 功能 |
|---|---|---|
| `CLK100MHZ` | 输入 | Nexys A7 100 MHz 系统时钟 |
| `CPU_RESETN` | 输入 | 低电平有效的复位信号 |
| `SW_0` | 输入 | 录音控制开关，1 表示录音 |
| `SW_1` | 输入 | 播放控制开关，1 表示播放 |
| `M_DATA` | 输入 | 麦克风 PDM 数据 |
| `M_CLK` | 输出 | 提供给麦克风的时钟 |
| `M_LRSEL` | 输出 | 麦克风左右声道/数据边沿选择，固定为 0 |
| `AUD_PWM` | 输出 | PWM 音频数据 |
| `AUD_SD` | 输出 | 音频放大器使能信号 |
| `LED[15:0]` | 输出 | 录音状态、播放状态和音量显示 |

复位逻辑为：

```verilog
rst = ~CPU_RESETN;
```

因此，按下 CPU reset 按钮时，内部模块进入复位状态。

### 2.2 状态机

顶层状态机包含三个状态：

```text
IDLE    ：空闲
RECORD  ：录音
PLAYBACK：播放
```

状态转移关系如下：

```text
                 SW_0 = 1 且缓存未满
              ┌──────────────────────┐
              │                      ▼
          ┌───────┐              ┌────────┐
          │ IDLE  │              │ RECORD │
          └───────┘              └────────┘
              ▲  │                    │
              │  │ SW_1 = 1           │ SW_0 = 0
              │  │ 且有录音数据       │ 或缓存已满
              │  ▼                    ▼
          ┌──────────┐ ◄───────────────┘
          │ PLAYBACK │
          └──────────┘
              │
              └── SW_1 = 0 或播放完成 ──► IDLE
```

状态行为：

- `IDLE`：等待录音或播放命令。若 `SW_0=1` 且缓存未满，进入 `RECORD`；若 `SW_1=1` 且存在录音数据，进入 `PLAYBACK`。
- `RECORD`：每当 PDM 解码器产生 `sample_valid`，就把当前 PCM 样本写入缓存。`SW_0=0` 或缓存已满时停止录音。
- `PLAYBACK`：按照约 19.5 kHz 的播放采样率依次读取缓存数据。当 `SW_1=0` 或所有样本播放完毕时返回 `IDLE`。

### 2.3 录音计数器和播放计数器

顶层使用两个 14 bit 计数器：

```verilog
record_count
play_count
```

其中：

- `record_count` 表示已经写入的样本数量，同时其低 13 bit 作为 BRAM 写地址。
- `play_count` 表示已经播放的样本数量，同时其低 13 bit 作为 BRAM 读地址。
- 缓存深度为 8192 个 8 bit 样本。
- `record_count == 8192` 时认为缓存已满。
- `play_count == record_count` 时认为播放完成。

录音期间的写使能为：

```verilog
buf_we = (state == RECORD) && sample_valid && !buf_full;
```

这保证只有在录音状态、PCM 样本有效且缓存未满时才写入存储器。

### 2.4 播放采样定时器

PDM 解码器每 128 个麦克风时钟产生一个 PCM 样本。麦克风时钟约为 2.5 MHz，因此音频采样率约为：

```text
2.5 MHz / 128 ≈ 19.531 kHz
```

顶层播放定时器使用 100 MHz 系统时钟，并设置：

```verilog
SAMPLE_PERIOD = 5120;
```

因此播放采样脉冲周期约为：

```text
5120 / 100 MHz = 51.2 us
```

对应采样率约为：

```text
1 / 51.2 us ≈ 19.531 kHz
```

播放计数器只在 `sample_tick` 有效且缓存未播放完成时递增。

### 2.5 LED 音量显示

解码后的 PCM 值范围约为 `0~128`，静音中心约为 `64`。顶层先计算相对中心值：

```text
signed_sample = display_sample - 64
```

然后计算绝对幅度：

```text
amplitude = abs(display_sample - 64)
```

16 个 LED 按幅度阈值逐级点亮：

```text
LED[0]  ：amplitude > 0
LED[1]  ：amplitude > 4
LED[2]  ：amplitude > 8
...
LED[15] ：amplitude > 60
```

显示规则：

- `IDLE`：若缓存中有数据，点亮 `LED[0]`；否则全部熄灭。
- `RECORD`：16 个 LED 显示当前麦克风音量条。
- `PLAYBACK`：`LED[15]` 作为播放状态指示，同时低 15 位显示当前播放数据的音量。

### 2.6 PWM 音频输出

PWM 计数器为 8 bit，直接使用 100 MHz 系统时钟递增：

```text
PWM 频率 = 100 MHz / 256 ≈ 390.625 kHz
```

播放样本来自 BRAM。为了使 PWM 占空比围绕 50% 对称，代码将样本加上 64：

```verilog
pwm_duty = pwm_sample + 8'd64;
```

典型对应关系：

| PCM 样本 | PWM 占空比近似值 |
|---:|---:|
| 0 | 25% |
| 64 | 50% |
| 128 | 75% |

`AUD_SD` 仅在 `PLAYBACK` 状态为高，用于使能板载音频放大器：

```verilog
AUD_SD = (state == PLAYBACK);
```

当前实现使用 FPGA 普通推挽方式输出 `AUD_PWM`，而不是严格的开漏三态驱动。这种方式适合基础实验和功能验证；如果要完全按照硬件音频接口要求实现，应进一步确认并实现相应的三态/开漏输出方式。

## 3. PDM 解码器 `pdm_decoder`

### 3.1 麦克风时钟产生

系统时钟为 100 MHz，`MCLK_DIV=20`。每计数 20 个系统时钟，翻转一次 `M_CLK`：

```text
M_CLK = 100 MHz / (20 × 2) = 2.5 MHz
```

2.5 MHz 位于 Nexys A7 板载 PDM 麦克风约 1~3.3 MHz 的允许范围内。

### 3.2 数据边沿选择

```verilog
assign m_lrsel = 1'b0;
```

根据板卡麦克风说明，`M_LRSEL=0` 时在麦克风时钟上升沿读取 `M_DATA`。

### 3.3 上升沿检测

`M_CLK` 是由 FPGA 内部产生的寄存器信号。解码器在 100 MHz 系统时钟域中保存上一拍的 `M_CLK`，通过比较当前值和上一拍的值检测上升沿：

```verilog
m_clk_rise = m_clk && !m_clk_d;
```

检测到上升沿后，读取一个 PDM 数据位。

### 3.4 128 bit 计数平均

PDM 是 1 bit 高速数据流，音频幅度由一段时间内 `1` 的密度表示。模块每 128 个 PDM bit 统计一次 `1` 的数量：

```text
ones_count = 128 个 PDM bit 中 1 的个数
pcm_sample = ones_count
```

输出范围为：

```text
0~128
```

静音时通常约为 64。每完成一个窗口，输出一个时钟周期的 `sample_valid` 脉冲。

### 3.5 PDM 解码伪代码

```text
初始化：
    M_CLK 分频计数器 = 0
    M_CLK = 0
    bit_count = 0
    ones_count = 0
    pcm_sample = 64
    sample_valid = 0

每个 100 MHz 系统时钟上升沿：
    如果复位：
        清零 M_CLK 分频计数器
        清零 M_CLK
        清零 bit_count 和 ones_count
        pcm_sample = 64
        sample_valid = 0
    否则：
        如果 M_CLK 分频计数器达到 19：
            清零分频计数器
            翻转 M_CLK
        否则：
            分频计数器加 1

        保存上一拍 M_CLK
        如果检测到 M_CLK 上升沿：
            ones_count = ones_count + M_DATA
            bit_count = bit_count + 1

            如果 bit_count 达到 127：
                pcm_sample = ones_count + 当前 M_DATA
                sample_valid = 1
                bit_count = 0
                ones_count = 0
            否则：
                sample_valid = 0
```

## 4. 音频缓存 `audio_buffer`

### 4.1 存储结构

缓存模块参数如下：

```verilog
DEPTH = 8192
WIDTH = 8
```

因此逻辑存储容量为：

```text
8192 × 8 bit = 65536 bit = 8 KiB
```

8192 个地址需要 13 bit 地址：

```text
ADDR_W = clog2(8192) = 13
```

### 4.2 写入和读取

缓存采用同步写入、同步读出结构：

```verilog
always @(posedge clk) begin
    if (we)
        mem[addr] <= din;
    dout <= mem[addr];
end
```

这种写法便于 Vivado 将存储器推断为 FPGA Block RAM 或其他片上存储资源。

模块没有独立的读写地址端口，而是由顶层通过 `addr` 选择当前地址：

- `RECORD` 状态使用 `record_count[12:0]` 作为写地址。
- 非 `RECORD` 状态使用 `play_count[12:0]` 作为读地址。
- 写使能 `we` 只在录音状态有效。

### 4.3 缓存模块伪代码

```text
初始化存储器输出 dout

每个系统时钟上升沿：
    如果写使能 we 有效：
        mem[addr] = din

    dout = mem[addr]
```

## 5. 系统工作流程伪代码

```text
复位：
    state = IDLE
    record_count = 0
    play_count = 0
    PWM 计数器清零

持续运行 PDM 解码器：
    生成 M_CLK
    采集 M_DATA
    每 128 bit 产生一个 pcm_sample

如果 state == IDLE：
    play_count = 0

    如果 SW_0 == 1 且缓存未满：
        record_count = 0
        state = RECORD

    否则如果 SW_1 == 1 且缓存中有数据：
        state = PLAYBACK

如果 state == RECORD：
    如果 SW_0 == 0 或缓存已满：
        state = IDLE
    否则如果 sample_valid == 1：
        将 pcm_sample 写入 audio_buffer
        record_count = record_count + 1

如果 state == PLAYBACK：
    如果 SW_1 == 0 或 play_count == record_count：
        state = IDLE
    否则如果 sample_tick == 1：
        从 audio_buffer 读取当前样本
        play_count = play_count + 1

在所有状态下：
    根据当前 display_sample 计算音量幅度
    更新 LED 音量条

在 PLAYBACK 状态下：
    将 BRAM 样本转换为 PWM 占空比
    AUD_SD = 1

在其他状态下：
    AUD_SD = 0
    PWM 使用静音中心值
```

## 6. 关键参数汇总

| 参数 | 数值 | 说明 |
|---|---:|---|
| 系统时钟 | 100 MHz | `CLK100MHZ` |
| 麦克风时钟 | 2.5 MHz | `100 MHz / 40` |
| PDM 统计窗口 | 128 bit | 每 128 个 PDM bit 产生一个 PCM 样本 |
| PCM 采样率 | 约 19.531 kHz | `2.5 MHz / 128` |
| 缓存深度 | 8192 样本 | 约 0.42 秒音频 |
| PCM 位宽 | 8 bit | 样本范围约为 `0~128` |
| PWM 位宽 | 8 bit | 256 级占空比 |
| PWM 频率 | 约 390.625 kHz | `100 MHz / 256` |
| 静音中心 | 64 | PDM 计数平均值的理论中点 |

录音时长约为：

```text
8192 / 19531 ≈ 0.42 秒
```

## 7. 上板验证流程

1. 下载 bitstream 并完成复位。
2. 将 `SW_1` 置为 0，确保系统不处于播放状态。
3. 将 `SW_0` 置为 1，进入录音状态。
4. 对着板载麦克风说话或拍手，观察 LED 音量条变化。
5. 将 `SW_0` 置为 0，停止录音。若缓存中有数据，空闲状态下 `LED[0]` 点亮。
6. 将 `SW_1` 置为 1，开始播放，`LED[15]` 表示播放状态。
7. 将耳机或有源音箱连接到 Nexys A7 音频输出接口，检查是否能听到录音内容。
8. 将 `SW_1` 置为 0，可提前停止播放。

## 8. 当前实现的限制和注意事项

- PDM 解码采用简单的 128 bit 计数平均法，实质上是一个简单移动平均滤波器，适合音量检测、基础录音和功能演示，但音质不如 CIC 加 FIR 的多级抽取滤波器。
- PDM 数据的静音中心不是 0，而是约 64。LED 音量计算已经减去该中心值。
- `M_DATA` 在顶层被直接送入系统时钟域中的边沿检测逻辑。由于 `M_CLK` 由 FPGA 产生，基础实验中通常可以工作；更严格的设计可以使用专用时钟资源和独立的 `M_CLK` 时钟域。
- 当前 PWM 输出使用普通推挽逻辑。若需要严格满足板载音频接口的开漏要求，应进一步改为三态/开漏输出结构。
- 缓存使用 FPGA 内部存储器，只保存约 0.42 秒音频，不能替代 DDR2 或 microSD 长时间录音。
- 当前实现中，如果 `record_count` 达到缓存容量，`buf_full` 会保持有效；由于重新开始录音的计数清零条件包含 `!buf_full`，缓存完全写满后不能直接重新录音，需要增加专门的缓存清空或重新录音控制逻辑。
- `M_CLK`、PDM 解码、BRAM 读写和 PWM 都由顶层的 100 MHz 时钟同步控制，设计没有使用门控时钟。
