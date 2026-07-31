下面详细讲一下 **Nexys A7 板载麦克风的硬件连接、工作原理、PDM 数据含义、FPGA 如何采样和还原音频**。

---

# Nexys A7 板载麦克风原理详解

Nexys A7 板上带有一个数字 MEMS 麦克风。参考手册中写的是 Analog Devices ADMP421 类 PDM 麦克风，原理图中对应器件为：

```text
IC1: SPK0833LM4H
```

它本质上是一个 **数字 PDM 输出 MEMS 麦克风**。

这个麦克风不是输出模拟电压，也不是 I2S，而是输出一种叫做 **PDM，Pulse Density Modulation，脉冲密度调制** 的 1-bit 数字音频流。

---

## 1. 麦克风硬件连接

在 Nexys A7 原理图第 3 页中，麦克风模块为：

```text
IC1: SPK0833LM4H
```

它与 FPGA 的连接如下：

| 麦克风信号 | 功能 | FPGA 信号名 | FPGA 引脚 |
|---|---|---|---|
| CLK | 麦克风输入时钟 | M_CLK | J5 |
| DATA | PDM 数据输出 | M_DATA | H5 |
| L/R SEL | 左右声道选择/数据边沿选择 | M_LRSEL | F5 |
| VDD | 电源 | VCC3V3 | - |
| GND | 地 | GND | - |

Vivado XDC 约束一般写为：

```tcl
set_property -dict { PACKAGE_PIN J5 IOSTANDARD LVCMOS33 } [get_ports M_CLK]
set_property -dict { PACKAGE_PIN H5 IOSTANDARD LVCMOS33 } [get_ports M_DATA]
set_property -dict { PACKAGE_PIN F5 IOSTANDARD LVCMOS33 } [get_ports M_LRSEL]
```

---

## 2. 麦克风整体工作流程

板载麦克风的工作流程如下：

```text
空气声波
   ↓
MEMS 振膜机械振动
   ↓
电容变化
   ↓
内部模拟放大器
   ↓
Sigma-Delta 调制器
   ↓
1-bit PDM 数字流
   ↓
FPGA 对 PDM 采样
   ↓
低通滤波 / 抽取 / 计数平均
   ↓
PCM 音频采样值
```

也就是说，FPGA 接收到的不是普通的多位并行音频数据，而是一串高速的 0/1 比特流。

---

## 3. PDM 是什么？

PDM 全称是：

```text
Pulse Density Modulation
脉冲密度调制
```

它用 **1-bit 高速数字流中 1 的密度** 表示模拟信号幅度。

### 3.1 直观理解

假设在一小段时间窗口内统计 PDM 数据：

```text
00000000  → 很小的模拟值
01010101  → 中间值
11111111  → 很大的模拟值
```

更准确地说：

| PDM 流 | 含义 |
|---|---|
| 全 0 | 最大负幅度 |
| 0 和 1 各一半 | 接近 0 幅度 |
| 全 1 | 最大正幅度 |
| 1 越密集 | 声音瞬时幅度越高 |
| 0 越密集 | 声音瞬时幅度越低 |

例如：

```text
PDM: 1111111100000000
```

在这个窗口中 1 的数量是 8，0 的数量是 8，平均值是 0.5，对应接近中点。

再比如：

```text
PDM: 1111111111110000
```

1 的数量是 12，0 的数量是 4，平均值是 0.75，对应较大的正向幅度。

---

## 4. PDM 和 PWM 的区别

很多初学者容易把 PDM 和 PWM 混淆。

### 4.1 PWM

PWM 是脉冲宽度调制：

```text
周期固定，改变高电平宽度
```

例如：

```text
11110000 11110000 11110000
```

高电平宽度固定集中在每个周期前半段。

### 4.2 PDM

PDM 是脉冲密度调制：

```text
不关心每个周期内高电平宽度，而关心一段时间内 1 的数量
```

例如：

```text
10110111 01110111 10111101
```

1 越密集，表示模拟值越大。

### 4.3 对比

| 特性 | PWM | PDM |
|---|---|---|
| 调制对象 | 脉冲宽度 | 脉冲密度 |
| 数据位宽 | 通常 1 bit | 1 bit |
| 周期 | 明确固定周期 | 高速 bitstream |
| 音频麦克风常用 | 否 | 是 |
| FPGA 处理方式 | 低通滤波 | 低通滤波 + 抽取 |

---

## 5. 麦克风内部 Sigma-Delta 调制原理

PDM 麦克风内部通常使用 **Sigma-Delta 调制器**。

简化模型如下：

```text
        ┌──────────┐
声波 →  │ 模拟前端  │
        └────┬─────┘
             ↓
        ┌──────────┐
        │ 积分器    │
        └────┬─────┘
             ↓
        ┌──────────┐
        │ 比较器    │ → 1-bit 输出
        └────┬─────┘
             ↓
        ┌──────────┐
        │ 反馈 DAC  │
        └──────────┘
```

其思想是：

- 如果输入模拟值偏高，就输出更多的 `1`
- 如果输入模拟值偏低，就输出更多的 `0`
- 长时间平均后，PDM 流的平均值接近原始模拟信号

参考手册中给了一个简单例子：

假设模拟输入为 `0.4Vdd`，Sigma-Delta 调制器会产生类似：

```text
0, 1, 0, 1, 0, 0, 1, ...
```

在足够长时间内，输出中 `1` 的比例接近 `0.4`。

---

## 6. Nexys A7 麦克风时钟

麦克风需要 FPGA 提供时钟：

```text
M_CLK
```

参考手册说明：

```text
麦克风时钟范围：1 MHz ~ 3.3 MHz
典型值：2.4 MHz
```

所以 FPGA 需要从板载 100MHz 时钟分频产生一个大约 1~3.3MHz 的时钟。

例如：

| 系统时钟 | 分频方式 | 麦克风时钟 |
|---|---|---|
| 100 MHz | 除以 40 | 2.5 MHz |
| 100 MHz | MMCM 产生 | 2.4 MHz |
| 100 MHz | 除以 50 | 2.0 MHz |

严格来说，如果想得到准确的 2.4MHz，最好用 Vivado 的 Clocking Wizard / MMCM。

如果只是做基础实验，2MHz 或 2.5MHz 通常也可以使用，只要在器件允许范围内。

---

## 7. L/R SEL 信号的作用

麦克风有一个：

```text
M_LRSEL
```

该信号用于选择数据在哪个时钟边沿输出，也常用于左右声道复用。

参考手册中说明：

| M_LRSEL | 数据有效边沿 |
|---|---|
| 0 | 数据在时钟上升沿可用 |
| 1 | 数据在时钟下降沿可用 |

Nexys A7 只有一个麦克风，一般可以固定：

```verilog
assign M_LRSEL = 1'b0;
```

然后在 `M_CLK` 的上升沿采样 `M_DATA`。

或者固定为 1，在下降沿采样。

---

## 8. FPGA 如何从 PDM 得到音频数据？

FPGA 不能直接把 `M_DATA` 当成音频采样值使用，因为它只是 1-bit 高速流。

必须做：

```text
PDM → 低通滤波 → 降采样 → PCM
```

最简单的方法是 **计数平均法**。

---

## 9. 最简单的 PDM 解码方法：统计 1 的个数

假设麦克风时钟为：

```text
M_CLK = 2.4 MHz
```

如果我们每 100 个 PDM bit 统计一次 1 的数量，则输出采样率为：

```text
2.4 MHz / 100 = 24 kHz
```

每 100 个 bit 中，1 的数量范围是：

```text
0 ~ 100
```

这个计数值就可以近似看作音频采样值。

例如：

| 100 个 PDM bit 中 1 的个数 | 对应音频值 |
|---|---|
| 0 | 最小 |
| 25 | 偏负 |
| 50 | 静音附近 |
| 75 | 偏正 |
| 100 | 最大 |

如果要得到有符号值，可以做：

```text
signed_sample = ones_count - N/2
```

例如 N=128：

```text
signed_sample = ones_count - 64
```

这样：

| ones_count | signed_sample |
|---|---|
| 0 | -64 |
| 64 | 0 |
| 128 | +64 |

---

## 10. 为什么要低通滤波？

PDM 是高速 1-bit 调制流，里面有大量高频量化噪声。

Sigma-Delta 调制器会把噪声推到高频区域，这叫：

```text
Noise Shaping
噪声整形
```

人耳关注的是 20Hz~20kHz 左右的音频，而 PDM 高频噪声在 MHz 级附近。

所以 FPGA 需要做数字低通滤波，把高频噪声去掉，再降采样。

最简单的计数平均，其实就是一种低通滤波器：

```text
Moving Average Filter
移动平均滤波器
```

更高级的实现会使用：

- CIC 滤波器
- FIR 低通滤波器
- CIC + FIR 补偿滤波器
- 多级抽取滤波器

---

## 11. 计数窗口大小如何选择？

假设麦克风时钟为 2.4MHz。

### 11.1 若窗口为 64

```text
采样率 = 2.4MHz / 64 = 37.5kHz
位宽约 = log2(64) = 6 bit
```

优点：采样率较高
缺点：幅度分辨率较低

### 11.2 若窗口为 128

```text
采样率 = 2.4MHz / 128 = 18.75kHz
位宽约 = 7 bit
```

优点：分辨率更高
缺点：采样率较低

### 11.3 若窗口为 100

```text
采样率 = 2.4MHz / 100 = 24kHz
```

这是参考手册中提到的思路附近，用于简单音频实验很合适。

### 11.4 选择建议

| 应用 | 建议窗口 | 说明 |
|---|---|---|
| LED 音量显示 | 64 或 128 | 简单 |
| 录音播放实验 | 64~128 | 可接受 |
| 语音识别前端 | 64 或更复杂滤波 | 需要更好质量 |
| 高保真音频 | CIC + FIR | 不建议只用计数 |

---

## 12. 简单 PDM 采样 Verilog 示例

下面给一个最基础的示例：
用 100MHz 系统时钟产生约 2.5MHz 麦克风时钟，然后每 128 个 PDM bit 统计一次 1 的个数。

```verilog
module nexys_a7_pdm_mic_simple (
    input  wire        clk100,
    input  wire        rst,

    output reg         M_CLK,
    input  wire        M_DATA,
    output wire        M_LRSEL,

    output reg  [7:0]  audio_level,
    output reg         sample_valid
);

    // 固定选择上升沿输出/采样模式
    assign M_LRSEL = 1'b0;

    // 100MHz / 40 = 2.5MHz
    // M_CLK 半周期计数 20 个 clk100 周期
    reg [5:0] clk_div;

    always @(posedge clk100) begin
        if (rst) begin
            clk_div <= 0;
            M_CLK   <= 0;
        end else begin
            if (clk_div == 19) begin
                clk_div <= 0;
                M_CLK   <= ~M_CLK;
            end else begin
                clk_div <= clk_div + 1;
            end
        end
    end

    // 检测 M_CLK 上升沿
    reg M_CLK_d;

    always @(posedge clk100) begin
        M_CLK_d <= M_CLK;
    end

    wire mic_clk_rise = (M_CLK == 1'b1) && (M_CLK_d == 1'b0);

    // 每 128 个 PDM bit 统计一次 1 的数量
    reg [6:0] bit_count;
    reg [7:0] ones_count;

    always @(posedge clk100) begin
        if (rst) begin
            bit_count    <= 0;
            ones_count   <= 0;
            audio_level  <= 0;
            sample_valid <= 0;
        end else begin
            sample_valid <= 0;

            if (mic_clk_rise) begin
                ones_count <= ones_count + M_DATA;
                bit_count  <= bit_count + 1;

                if (bit_count == 7'd127) begin
                    audio_level  <= ones_count + M_DATA;
                    sample_valid <= 1;

                    bit_count  <= 0;
                    ones_count <= 0;
                end
            end
        end
    end

endmodule
```

这个模块输出：

```text
audio_level = 0~128
```

静音附近一般在 64 左右。

如果想得到有符号音频：

```verilog
wire signed [8:0] audio_signed = {1'b0, audio_level} - 9'sd64;
```

---

## 13. 用 LED 显示麦克风音量

上面的 `audio_level` 是波形瞬时值，不是音量。
如果要显示音量，可以取它相对中点的绝对值：

```verilog
wire signed [8:0] audio_signed = {1'b0, audio_level} - 9'sd64;

wire [7:0] amplitude =
    audio_signed[8] ? -audio_signed : audio_signed;
```

然后用幅度点亮 LED：

```verilog
always @(*) begin
    if (amplitude > 60)      led = 16'hFFFF;
    else if (amplitude > 56) led = 16'h7FFF;
    else if (amplitude > 52) led = 16'h3FFF;
    else if (amplitude > 48) led = 16'h1FFF;
    else if (amplitude > 44) led = 16'h0FFF;
    else if (amplitude > 40) led = 16'h07FF;
    else if (amplitude > 36) led = 16'h03FF;
    else if (amplitude > 32) led = 16'h01FF;
    else if (amplitude > 28) led = 16'h00FF;
    else if (amplitude > 24) led = 16'h007F;
    else if (amplitude > 20) led = 16'h003F;
    else if (amplitude > 16) led = 16'h001F;
    else if (amplitude > 12) led = 16'h000F;
    else if (amplitude > 8)  led = 16'h0007;
    else if (amplitude > 4)  led = 16'h0003;
    else                     led = 16'h0001;
end
```

---

## 14. 更规范的 PDM 到 PCM 架构

简单计数法适合演示，但音质一般。更标准的架构如下：

```text
PDM 输入
  ↓
同步采样
  ↓
CIC 抽取滤波器
  ↓
FIR 补偿低通滤波器
  ↓
PCM 音频数据
  ↓
存储 / 播放 / FFT / 识别
```

### 14.1 CIC 滤波器

CIC 即：

```text
Cascaded Integrator Comb Filter
级联积分梳状滤波器
```

它非常适合 FPGA，因为主要使用加法器和寄存器，不需要乘法器。

结构：

```text
积分器 → 积分器 → ... → 降采样 → 梳状器 → 梳状器 → ...
```

优点：

- 不需要乘法器
- 很适合高倍率抽取
- FPGA 资源消耗低

缺点：

- 通带有下垂
- 高音频质量时需要 FIR 补偿

### 14.2 FIR 低通滤波器

FIR 可以进一步改善音质：

- 去除高频噪声
- 限制音频带宽
- 补偿 CIC 通带下垂

Vivado 中可以使用：

```text
FIR Compiler IP
```

或者自己写定点 FIR。

---

## 15. 麦克风数据播放到音频输出

Nexys A7 还带有 PWM 音频输出：

```text
AUD_PWM → 低通滤波器 → 音频插孔
```

参考手册的内置自检中就实现了：

```text
按 BTNU 录制 5 秒麦克风音频
↓
存入 DDR2
↓
通过音频输出立即播放
```

完整音频链路可以是：

```text
PDM 麦克风
  ↓
FPGA PDM 解码
  ↓
PCM 数据
  ↓
DDR2 缓冲
  ↓
PWM/PDM 音频调制
  ↓
板载低通滤波器
  ↓
3.5mm 音频接口
```

---

## 16. 麦克风与音频输出的区别

板载麦克风：

```text
输入设备
PDM 数字输出
FPGA 提供 M_CLK
FPGA 读取 M_DATA
```

板载音频接口：

```text
输出设备
FPGA 输出 AUD_PWM
板载低通滤波转换为模拟音频
```

二者不要混淆。

| 模块 | 方向 | 信号类型 |
|---|---|---|
| 麦克风 | 输入到 FPGA | PDM 数字流 |
| 音频插孔 | FPGA 输出 | PWM/PDM 经模拟滤波 |
| VGA | FPGA 输出 | 并行 RGB + 同步 |
| UART | 双向 | 串口 |

---

## 17. 开发时的注意事项

### 17.1 M_CLK 不能太高或太低

参考范围：

```text
1MHz ~ 3.3MHz
```

太低可能导致采样质量下降，太高可能超出器件规范。

### 17.2 M_DATA 是异步输入吗？

严格来说，`M_DATA` 是由 `M_CLK` 驱动产生的。
如果 `M_CLK` 由 FPGA 产生，那么可以在 FPGA 内部用同一个时钟关系采样。
但若你在 `clk100` 域中检测 `M_CLK` 边沿采样，应该注意时序裕量。

更规范的方法是：

- 用 MMCM 产生 `mic_clk`
- 直接用 `mic_clk` 作为采样时钟
- 在 `posedge mic_clk` 采样 `M_DATA`
- 再跨时钟域到系统时钟

### 17.3 静音值不是 0

PDM 解码后，静音中心通常在：

```text
N/2
```

例如窗口 N=128 时静音约为 64。
做音量或波形时要减去中点。

### 17.4 简单计数法音质有限

如果只是点亮 LED、做声强检测、基础录音，可以用计数法。

如果要较好音质，建议：

```text
CIC + FIR + 合理采样率
```

### 17.5 不要把 M_DATA 当普通 1-bit 音频播放

直接输出 PDM 数据到 LED 或音频口通常没有意义。
必须先滤波或平均。

---

## 18. 一个推荐的实验步骤

如果你刚开始做 Nexys A7 麦克风实验，建议按这个顺序：

### 第一步：产生 M_CLK

用 100MHz 分频产生 2MHz~2.5MHz。

### 第二步：固定 M_LRSEL

```verilog
assign M_LRSEL = 1'b0;
```

### 第三步：采样 M_DATA

在 M_CLK 上升沿读取。

### 第四步：统计 1 的个数

每 64/128 个 bit 输出一个样本。

### 第五步：用 LED 显示幅度

计算：

```text
abs(sample - midpoint)
```

### 第六步：保存或播放

进阶可将 PCM 写入 DDR2，再通过 AUD_PWM 播放。

---

## 19. 总结

Nexys A7 的麦克风本质是一个 **数字 PDM MEMS 麦克风**。

核心原理可以概括为：

```text
声波 → MEMS 传感 → Sigma-Delta 调制 → 1-bit PDM 流
```

FPGA 需要做：

```text
产生 M_CLK
设置 M_LRSEL
采样 M_DATA
统计/滤波 PDM 比特流
抽取得到 PCM 音频样本
```

最简单实现：

```text
每 N 个 PDM bit 统计 1 的个数
sample = ones_count - N/2
```

高质量实现：

```text
PDM → CIC 抽取 → FIR 低通/补偿 → PCM
```

Nexys A7 板载麦克风非常适合做：

- 声音强度检测
- LED 音量条
- 简单录音播放
- FFT 频谱分析
- 语音前端处理
- 数字滤波器实验
- PDM/CIC/FIR 学习项目