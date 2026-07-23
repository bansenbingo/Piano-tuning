# Nexys A7 PDM 麦克风录音与回放 RTL 实现说明

本文档说明当前 `MicrophoneA7` 工程中实际使用的 RTL，而非通用示例。内容依据以下文件及 `Reference` 中的 Nexys A7 硬件资料整理。

```text
Sandbox/Microphone/MicrophoneA7/
├── MicrophoneA7.srcs/sources_1/imports/rtl/
│   ├── mic_recorder.v       # 顶层、录放控制、PWM 和 LED
│   ├── pdm_decoder.v        # PDM 时钟与抽取解码
│   └── audio_buffer.v       # 片上同步音频缓存
└── MicrophoneA7.srcs/constrs_1/imports/xdc/
    └── mic_recorder.xdc     # 当前工程的引脚和时钟约束
```

板级连接、电气要求和 PDM 原理可参考 `Reference/A7.md`、`Reference/mic.md`、`Reference/A7.xdc`、Nexys A7 参考手册及原理图。本文以当前 Verilog 的行为为准；参数、接口或状态机修改后，应同步更新本文档。

## 1. 设计目标与数据流

设计使用 Nexys A7 板载数字 MEMS PDM 麦克风进行短时单声道录音，将解码后的样本保存在 FPGA 片上存储器中，并通过板载 PWM 音频接口一次性回放。

```text
                         +-----------------------------+
                         |         mic_recorder        |
                         |                             |
CLK100MHZ -------------->| 100 MHz 系统时钟域          |
CPU_RESETN ------------->| 复位、开关同步和状态控制    |
SW_0 ------------------->| 录音请求                    |
SW_15 ------------------>+ 播放请求                    |
                         +--------------+--------------+
                                        |
                                        v
                         +-----------------------------+
                         |         pdm_decoder         |
                         | 2.5 MHz M_CLK               |
M_DATA ----------------->| 两级同步、128 bit 计数抽取 |
M_CLK <------------------|                             |
M_LRSEL <----------------| 固定为 0                    |
                         +--------------+--------------+
                                        |
                          pcm_sample[7:0], sample_valid
                                        |
                                        v
                         +-----------------------------+
                         |        audio_buffer         |
                         | 65,536 x 8 bit 同步存储器   |
                         +--------------+--------------+
                                        |
                                        v
                         +-----------------------------+
                         | PWM、开漏式 AUD_PWM、LED    |
                         +----------+------------------+
                                    |          |
                              AUD_PWM       AUD_SD
```

PDM 解码器在系统退出复位后持续工作，不依赖录音或播放状态。录音状态只决定是否把有效 PCM 样本写入缓存；播放状态只决定是否读取缓存并使能音频输出。

## 2. 顶层接口与板级约束

顶层模块为 `mic_recorder`。当前工程中顶层端口名称与 `mic_recorder.xdc` 完全一致，不能直接改为 `SW[0]`、`SW[15]` 等其他名称而不同时修改 XDC。

| RTL 端口 | 方向 | Nexys A7 引脚 | I/O 标准 | 用途 |
|---|---|---:|---|---|
| `CLK100MHZ` | 输入 | E3 | LVCMOS33 | 100 MHz 板载时钟 |
| `CPU_RESETN` | 输入 | C12 | LVCMOS33 | 低有效 CPU 复位按钮 |
| `SW_0` | 输入 | J15 | LVCMOS33 | 录音请求开关，对应 `SW[0]` |
| `SW_15` | 输入 | V10 | LVCMOS33 | 播放请求开关，对应 `SW[15]` |
| `M_CLK` | 输出 | J5 | LVCMOS33 | PDM 麦克风时钟 |
| `M_DATA` | 输入 | H5 | LVCMOS33 | PDM 数据流 |
| `M_LRSEL` | 输出 | F5 | LVCMOS33 | 麦克风数据边沿选择 |
| `AUD_PWM` | 输出 | A11 | LVCMOS33 | PWM 音频信号 |
| `AUD_SD` | 输出 | D12 | LVCMOS33 | 音频通道使能 |
| `LED[15:0]` | 输出 | 见下表 | LVCMOS33 | 状态与音量显示 |

`mic_recorder.xdc` 对 `CLK100MHZ` 施加了 10 ns 时钟约束：

```tcl
create_clock -add -name sys_clk_pin -period 10.00 -waveform {0 5} \
    [get_ports { CLK100MHZ }]
```

当前 LED 引脚映射如下。

| LED 位 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| FPGA 引脚 | H17 | K15 | J13 | N14 | R18 | V17 | U17 | U16 |

| LED 位 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| FPGA 引脚 | V16 | T15 | U14 | T16 | V15 | V14 | V12 | V11 |

XDC 还将 `AUD_PWM` 设置为 `SLEW SLOW`。该输出的电气行为由 RTL 明确实现为释放高电平、只主动拉低，不能改为普通推挽高电平输出。

## 3. 关键参数与派生时序

| 项目 | RTL 参数或表达式 | 数值 | 说明 |
|---|---|---:|---|
| 系统时钟 | `CLK100MHZ` | 100 MHz | 全部顺序逻辑使用此时钟 |
| PDM 时钟半周期 | `MCLK_DIV = 20` | 200 ns | 每 20 个系统时钟翻转一次 `M_CLK` |
| PDM 时钟 | `100 MHz / (2 x 20)` | 2.5 MHz | 位于参考资料给出的约 1 到 3.3 MHz 范围内 |
| PDM 统计窗口 | `WINDOW = 128` | 128 bit | 每个窗口产生一个 PCM 样本 |
| PCM 采样率 | `2.5 MHz / 128` | 19,531.25 Hz | 约 19.531 kHz |
| 播放样本周期 | `SAMPLE_PERIOD = 5120` | 51.2 us | `5120 / 100 MHz` |
| 播放采样率 | `100 MHz / 5120` | 19,531.25 Hz | 与录音采样率严格一致 |
| 缓存深度 | `BUF_DEPTH = 65536` | 65,536 样本 | 地址宽度为 16 bit |
| 缓存容量 | `65536 x 8 bit` | 524,288 bit / 64 KiB | 保存原始无符号 PCM 计数值 |
| 最长录音时间 | `65536 / 19531.25` | 约 3.36 s | 精确值约 3.355 s |
| PWM 位宽 | `pwm_cnt[7:0]` | 8 bit | 256 个计数状态 |
| PWM 载波 | `100 MHz / 256` | 390.625 kHz | 远高于 PCM 采样率 |
| 默认去抖时间 | `SWITCH_DEBOUNCE_CYCLES = 1000000` | 10 ms | 不含前级同步带来的极少量延迟 |

PCM 码值不是以零为静音中心的有符号数。PDM 窗口内的 `1` 个数直接作为样本，因此理论范围为 `0` 到 `128`，静音附近的理论中心值为 `64`。

## 4. 复位与开关请求

### 4.1 复位

`CPU_RESETN` 是低有效输入，顶层将其反相为内部复位：

```verilog
assign rst = ~CPU_RESETN;
```

复位时，主状态机进入 `IDLE`，录音计数和播放计数清零，PDM 时钟输出为低，PDM 样本初始化为 `8'd64`，开关同步/去抖状态清零。`pwm_cnt` 使用异步复位；其余主要时序逻辑在下一个 `CLK100MHZ` 上升沿响应复位。

音频 RAM 没有逐地址清零。复位后 `record_count = 0`，因此任何旧 RAM 内容都不被视为有效录音数据。

### 4.2 开关同步、去抖和边沿触发

`SW_0` 与 `SW_15` 都先经过两级触发器同步到 100 MHz 时钟域，再经过独立计数器去抖。输入与当前稳定状态不同且连续保持 `SWITCH_DEBOUNCE_CYCLES` 个时钟周期后，去抖状态才更新。

```text
物理开关 -> 两级同步 -> 10 ms 稳定性确认 -> 去抖状态 -> 上升沿脉冲
```

顶层并不把开关电平本身作为启动命令，而是检测去抖后信号的上升沿：

```verilog
record_start = sw_0_debounced  && !sw_0_debounced_d;
play_start   = sw_15_debounced && !sw_15_debounced_d;
```

因此，录音和播放均是一次触发行为：

- `SW_0` 从关到开后，约 10 ms 后产生一次 `record_start`，每次该事件都从地址 0 开始新录音并丢弃此前逻辑录音长度。
- 录音开始后，保持 `SW_0` 为开可持续录音；将其拨回关后，约 10 ms 后停止录音。
- `SW_15` 从关到开后，约 10 ms 后产生一次 `play_start`。回放结束后，即使 `SW_15` 仍保持为开，也不会自动重播。
- 要重新回放或重新触发录音，必须先将相应开关拨回关并完成去抖，再重新拨到开。
- 非空闲状态下收到的另一类启动脉冲不会排队保存。若在 `IDLE` 中两个脉冲同一周期出现，状态机因代码顺序优先进入 `RECORD`。

## 5. `mic_recorder` 状态机与缓存控制

### 5.1 状态机

状态机定义三个状态：

```text
IDLE      空闲，等待新的边沿触发命令
RECORD    写入 PDM 解码后的 PCM 样本
PLAYBACK  按原采样率读取样本并进行 PWM 输出
```

状态转换如下。

```text
IDLE -- record_start ------------------------> RECORD
RECORD -- !sw_0_debounced or buf_full -------> IDLE

IDLE -- play_start && recorded_data_available -> PLAYBACK
PLAYBACK -- !sw_15_debounced ----------------> IDLE
PLAYBACK -- final sample's sample_tick ------> IDLE
```

更准确的转移条件为：

| 当前状态 | 条件 | 下一状态 | 行为 |
|---|---|---|---|
| `IDLE` | `record_start` | `RECORD` | 清零 `record_count`，开始一段新录音 |
| `IDLE` | `play_start && record_count != 0` | `PLAYBACK` | 清零 `play_count`，从第 0 个样本播放 |
| `RECORD` | `!sw_0_debounced` 或缓存满 | `IDLE` | 保留当前录音长度，停止写入 |
| `PLAYBACK` | `!sw_15_debounced` | `IDLE` | 提前停止回放 |
| `PLAYBACK` | 最后一个样本的 `sample_tick` | `IDLE` | 最后一个样本完整保持一个播放周期后结束 |

`record_count` 和 `play_count` 的位宽均为 17 bit。低 16 bit 连接缓存地址，高位使计数器能够精确表示 `65536`，即缓存已满的状态。

### 5.2 录音写入

仅在 `RECORD` 状态、PDM 解码器产生有效样本且缓存未满时写 RAM：

```verilog
buf_we = (state == RECORD) && sample_valid && !buf_full;
```

每次写入后 `record_count` 加一。最后一个有效地址为 `16'hFFFF`；该地址写入完成后，`record_count` 变为 `65536`，`buf_full` 生效，状态机返回 `IDLE`。

一次新的 `record_start` 无条件把 `record_count` 清零，不会因为前一次录音已经写满而锁死。RAM 无需物理擦除：新的逻辑长度只由新的 `record_count` 决定，播放不会访问该长度以后的旧数据。

### 5.3 回放读出与结束时刻

回放定时器仅在 `PLAYBACK` 状态运行。其计满 `5119` 时产生一个 `sample_tick`，并将 `play_count` 加一：

```verilog
if (sample_tick && (play_count != record_count))
    play_count <= play_count + 1;
```

缓存读地址在录音状态使用 `record_count[15:0]`，其他状态使用 `play_count[15:0]`。因此回放从地址 0 开始，每个样本保持 5,120 个 100 MHz 时钟周期。

对最后一个样本，状态机判断的是：

```verilog
sample_tick && (play_count == record_count - 1'b1)
```

这使最终样本先完整输出一个样本周期，再在该周期结束的 tick 返回 `IDLE`；不会在最后一个样本刚到达 PWM 输入时提前截断。

## 6. `pdm_decoder`：时钟、采样和抽取

### 6.1 PDM 时钟与数据边沿

`pdm_decoder` 从 100 MHz 系统时钟生成 `M_CLK`。`mclk_cnt` 从 0 计数到 19 后翻转一次 `m_clk`，得到 50% 占空比的 2.5 MHz 方波。

```text
M_CLK 周期 = 2 x 20 x 10 ns = 400 ns
M_CLK 频率 = 2.5 MHz
```

模块把 `M_LRSEL` 固定为低：

```verilog
assign m_lrsel = 1'b0;
```

根据 `Reference/A7.md` 与 `Reference/mic.md`，该选择对应麦克风在 `M_CLK` 上升沿输出有效数据。RTL 没有在上升沿后的第一个系统时钟立即取样，而是在时钟高电平期间创建延迟采样使能：

```verilog
M_DATA_SAMPLE_DELAY = 8;
m_data_sample = m_clk && (mclk_cnt == M_DATA_SAMPLE_DELAY - 1);
```

由于 100 MHz 周期为 10 ns，计数器在时钟翻转后从 0 开始。该组合条件在 `M_CLK` 上升沿后约 70 ns 变为有效，并在下一个系统时钟沿被解码逻辑采样，即约为 `M_CLK` 上升沿后 80 ns，仍位于高电平区间并为麦克风数据的建立和传播留出余量。

### 6.2 `M_DATA` 同步

`M_DATA` 先通过两个 100 MHz 触发器：

```verilog
m_data_sync <= {m_data_sync[0], m_data};
```

随后解码逻辑在 `m_data_sample` 有效时使用 `m_data_sync[1]`。这降低了外部输入亚稳态传播到计数逻辑的风险，并结合延迟采样点避开了 `M_CLK` 边沿附近的数据变化。

该实现属于简单的单时钟域采样方案：`M_CLK` 是由 100 MHz 逻辑生成并输出给麦克风的时钟，而解码、缓存和状态机仍全部运行在 100 MHz 域内。它不是以 `M_CLK` 为独立时钟域、再通过 CDC 传输 PCM 的架构。

### 6.3 128 bit 积分-清零抽取

PDM 的瞬时数据为 1 bit，`1` 的密度表示音频瞬时幅度。解码器在每个采样使能到来时累加 `1` 的数目：

```verilog
ones_cnt <= ones_cnt + {7'b0, m_data_sync[1]};
bit_cnt  <= bit_cnt + 1;
```

当收集到第 128 个 PDM bit 时，模块输出包含当前 bit 的总数：

```verilog
pcm_sample   <= ones_cnt + {7'b0, m_data_sync[1]};
sample_valid <= 1'b1;
bit_cnt      <= 0;
ones_cnt     <= 0;
```

`sample_valid` 只维持一个 `CLK100MHZ` 周期。输出定义为：

```text
pcm_sample = 128 个连续 PDM bit 中 1 的个数
```

| PDM 窗口中 `1` 的数目 | `pcm_sample` | 相对中心值 `pcm_sample - 64` |
|---:|---:|---:|
| 0 | 0 | -64 |
| 64 | 64 | 0 |
| 128 | 128 (`8'h80`) | +64 |

这里的 128 bit 窗口是连续但不重叠的积分-清零窗口，也可视为矩形窗平均后抽取 128 倍；它不是保留历史样本的滑动平均滤波器。该方法资源很少，适合基础录音、回放和音量显示。

## 7. `audio_buffer`：片上音频缓存

`audio_buffer` 的默认参数可配置为任意深度和位宽；顶层将其实例化为：

```verilog
.DEPTH(65536),
.WIDTH(8)
```

存储器的行为为同步写、同步读：

```verilog
always @(posedge clk) begin
    if (we)
        mem[addr] <= din;
    dout <= mem[addr];
end
```

该模块只有一个地址端口。顶层通过状态复用地址：

| 工作状态 | `buf_addr` | 操作 |
|---|---|---|
| `RECORD` | `record_count[15:0]` | `sample_valid` 时写入 `pcm_sample` |
| `IDLE` 或 `PLAYBACK` | `play_count[15:0]` | 同步读取 `dout` |

在当前使用方式中，录音阶段不需要回放数据，回放阶段不写 RAM，因此单端口结构满足需求。该标准同步 RAM 写法通常可由 Vivado 推断为片上存储资源，具体映射结果仍以综合报告为准。

## 8. PWM 音频输出

### 8.1 占空比生成

`pwm_cnt` 是一个始终运行的 8 bit 计数器。回放期间的 PCM 样本来自 `buf_dout`；非回放期间使用静音中心值 64：

```verilog
pwm_sample = (state == PLAYBACK) ? buf_dout : 8'd64;
pwm_duty   = pwm_sample + 8'd64;
```

因此，理论 PCM 范围 `0` 到 `128` 映射为 PWM 占空比 25% 到 75%，以 50% 为静音中心。

| PCM 样本 | `pwm_duty` | 释放高电平的占空比 |
|---:|---:|---:|
| 0 | 64 | 25% |
| 64 | 128 | 50% |
| 128 | 192 | 75% |

PWM 比较条件为 `pwm_cnt < pwm_duty`，所以高阻释放区的长度等于 `pwm_duty`。8 bit 计数器每 256 个系统时钟循环一次，PWM 载波频率为约 390.625 kHz。

### 8.2 开漏式输出和放大器控制

Nexys A7 的 `AUD_PWM` 连接板载模拟上拉和重构低通滤波电路。根据 `Reference/A7.md`，该引脚必须以开漏方式使用：逻辑高时释放引脚，逻辑低时主动拉低。当前 RTL 已按此要求实现：

```verilog
assign AUD_PWM = ((state == PLAYBACK) && (pwm_cnt < pwm_duty)) ? 1'bz : 1'b0;
```

含义如下：

- 仅在 `PLAYBACK` 状态且计数器低于占空比阈值时，`AUD_PWM` 输出高阻态；板载模拟上拉把该节点建立为高电平。
- 其他时间，FPGA 只主动输出低电平。
- RTL 从不主动驱动 `AUD_PWM` 为逻辑高，避免将输出改成不符合板卡要求的推挽驱动。
- `AUD_SD` 仅在 `PLAYBACK` 状态为高，用于使能板载音频通道；空闲和录音时为低。

板载模拟低通滤波器将 PWM 波形转换为耳机或有源音箱可用的模拟音频。外接设备应连接到板载音频输出接口，不应直接把 `AUD_PWM` 当作普通数字音频信号使用。

## 9. LED 状态与音量条

顶层选择用于显示的样本：录音和空闲时显示当前 PDM 解码值，回放时显示缓存读出值。

```verilog
display_sample = (state == PLAYBACK) ? buf_dout : pcm_sample;
amplitude      = abs(display_sample - 64);
```

状态和音量条复用 16 个 LED，实际映射如下。

| 状态 | `LED[0]` | `LED[14:1]` | `LED[15]` |
|---|---|---|---|
| `IDLE` | 0 | `LED[1]` 为 1 表示存在录音；其余为 0 | 0 |
| `RECORD` | 1，录音中 | 当前麦克风样本的音量条 | 0 |
| `PLAYBACK` | 0 | 当前回放样本的音量条 | 1，回放中 |

活动状态下，`LED[14:1]` 使用 `vu_leds[13:0]`，阈值为：

```text
LED[1]  : amplitude > 0
LED[2]  : amplitude > 4
LED[3]  : amplitude > 8
...
LED[14] : amplitude > 52
```

代码还计算了阈值 56 和 60 的 `vu_leds[14]`、`vu_leds[15]`，但顶层未把它们接到 LED，因为 `LED[15]` 保留为播放状态，`LED[0]` 保留为录音状态。因而当前可见的 VU 条只有 14 级。

## 10. 实际操作流程

1. 下载当前工程的 bitstream，释放 `CPU_RESETN`，并使 `SW_0`、`SW_15` 都处于关的位置。
2. 将 `SW_0` 拨到开。约 10 ms 去抖后，`LED[0]` 点亮，设计开始从地址 0 录音。
3. 对板载麦克风说话或发声。`LED[14:1]` 显示以 64 为中心计算的瞬时幅度。
4. 将 `SW_0` 拨回关。约 10 ms 后录音停止；只要至少写入了一个 PCM 样本，空闲时 `LED[1]` 点亮。
5. 将 `SW_15` 拨到开。约 10 ms 后，`LED[15]` 点亮，音频通道使能，并从第 0 个样本开始一次性播放。
6. 播放会在最后一个已录样本结束后自动停止。若要提前停止，将 `SW_15` 拨回关；去抖完成后停止。
7. 若要再次播放，先将 `SW_15` 拨回关并等待其稳定，再重新拨到开。若要重新录音，对 `SW_0` 执行同样的关到开操作。

录音持续超过约 3.36 s 时，缓存写满并自动停止。下一次有效的 `SW_0` 上升沿仍能开始一段新录音。

## 11. 设计边界与改进方向

- PDM 解码使用单级 128 bit 积分-清零抽取。它的低通效果有限，适合功能演示和基础语音/音量实验，不等价于高保真 CIC 加 FIR 抽取链。
- PCM 采样率为约 19.531 kHz，奈奎斯特频率约为 9.766 kHz。若要更好地保留高频音频成分并抑制抽取混叠，应重新设计抽取率和滤波器。
- 样本直接存储为无符号 PDM 计数值，没有 DC 偏置校准、自动增益控制、压缩或更高精度 PCM 格式。静音中心值 64 是理论值，实际硬件可能存在偏移。
- `M_DATA` 已经经过两级同步并在 `M_CLK` 高电平中段采样，但这仍是简单的 100 MHz 域实现。对更高音质或更严格时序要求，可使用更完整的源同步采样、CIC 和 FIR 架构。
- 64 KiB 片上缓存只能保存约 3.36 s 音频。长时间录音需要使用 DDR2、microSD 或外部存储控制器。
- 控制请求是边沿触发且不排队。运行期间触发另一开关不会在当前操作结束后自动执行；需要在空闲状态下重新产生对应上升沿。
- `AUD_PWM` 的高阻输出依赖 Nexys A7 板载模拟上拉与低通电路。不得为了“看到高电平”而改成推挽驱动高电平。

## 12. 验证要点

每次修改 RTL、XDC 或参数后，应至少检查以下行为：

1. `M_CLK` 为约 2.5 MHz，`M_LRSEL` 恒为低，且 `M_DATA` 的有效采样频率为约 2.5 MHz。
2. `sample_valid` 每 128 个 PDM bit 产生一次，周期为 5,120 个 100 MHz 时钟周期。
3. 录音时 `record_count` 仅随 `sample_valid` 增加；停止录音后其值保持不变。
4. `SW_0` 的一次有效上升沿始终从 `record_count = 0` 开始，即使上一次缓存已经写满。
5. 播放时 `play_count` 每 5,120 个系统时钟增加一次，最后一个样本完整输出后自动停止。
6. 非播放状态下 `AUD_SD = 0`，`AUD_PWM` 被拉低；播放状态下 `AUD_PWM` 只在逻辑高区间释放为高阻，不主动驱动高电平。
7. `LED[0]` 只表示录音状态，`LED[15]` 只表示播放状态，空闲且有有效录音时 `LED[1]` 点亮。
8. 顶层端口与 `mic_recorder.xdc` 的端口名、引脚和 I/O 标准完全一致。

本项目的 Vivado 相关改动应由用户在板上下载 bitstream 后验证实际麦克风录音和音频回放效果；静态 RTL 推导不能替代板级音频验证。
