# Nexys A7 录音音频传回电脑

本文说明如何在 Nexys A7 上将板载麦克风录制的音频数据通过 USB 传回电脑，并在电脑端保存为 WAV 文件。

## 1. 结论与适用范围

Nexys A7 可以通过板载 FT2232HQ 的 USB-UART 通道将 FPGA 中的音频数据传回电脑。电脑会将该接口识别为虚拟串口，FPGA 只需要实现 UART 发送器，不需要实现完整的 USB 协议。

当前 `Sandbox/Microphone/MicrophoneA7` 工程已经实现：

```text
板载 PDM 麦克风
    ↓
PDM 解码与抽取
    ↓
8 bit PCM 近似采样
    ↓
片上音频缓存
    ↓
AUD_PWM 音频播放
```

当前工程**尚未实现 UART 传输**。因此，仅生成并下载当前工程的 bitstream，不能自动把录音发送到电脑。需要在现有设计中增加 UART TX 引脚、UART 发送模块、发送控制状态机和电脑端接收程序。

本文推荐的方案是录音结束后再批量发送，而不是边录音边发送。这样可以避免录音写缓存和串口发送同时访问同一个单端口 RAM，也更容易保证数据完整。

## 2. 板卡接口

### 2.1 USB-UART 信号

Nexys A7 的 J6 是共用的 USB-JTAG/UART 接口，板上 FT2232HQ 将 FPGA 的 UART 信号转换为电脑可识别的虚拟串口。

| 功能 | FPGA 引脚 | FPGA 方向 | 说明 |
|---|---|---|---|
| UART TX | `D4` | 输出 | FPGA 发送到电脑（网络名 `UART_RXD_OUT`） |
| UART RX | `C4` | 输入 | 电脑发送到 FPGA，可选（网络名 `UART_TXD_IN`） |
| UART CTS | `D3` | 输入 | 硬件流控，可选 |
| UART RTS | `E5` | 输出 | 硬件流控，可选 |

本方案只使用 `UART TX`。不使用硬件流控时，电脑端和 FPGA 端都应关闭 RTS/CTS 流控。

参考资料中的网络名为 `UART_TXD_IN`（C4）和 `UART_RXD_OUT`（D4）。参考手册（第 6 节）明确说明：含方向含义的信号名是从 DTE（即电脑）视角命名的。因此 `UART_TXD_IN` 是电脑的 TXD 进入 FPGA（FPGA 输入，C4），`UART_RXD_OUT` 是 FPGA 输出给电脑 RXD 的线（FPGA 输出，D4）。**FPGA 发送到电脑必须约束到 `D4`**；约束到 C4 会驱动 FT2232 的输出线，电脑收不到任何数据。

### 2.2 与音频接口的区别

板载 3.5 mm 音频接口不能直接将数字录音文件传给电脑。它的路径是：

```text
PCM → AUD_PWM → 板载低通滤波器 → 3.5 mm 音频接口
```

这是模拟音频播放路径。要把音频保存为文件，应使用 USB-UART；不要把 `AUD_PWM` 当作数据传输接口。

## 3. 当前录音数据格式

当前工程的关键参数如下：

| 项目 | 当前值 |
|---|---:|
| 系统时钟 | 100 MHz |
| 麦克风 PDM 时钟 | 2.5 MHz |
| PDM 抽取窗口 | 128 bit |
| PCM 采样率 | 约 19,531.25 Hz |
| PCM 数据宽度 | 8 bit，无符号 |
| 缓存深度 | 65,536 个样本 |
| 最大录音长度 | 约 3.36 s |

PDM 解码器每收集 128 个 PDM bit，统计其中为 1 的数量，生成一个 `0~128` 的无符号样本。静音中心约为 `64`。该样本被直接写入 8 bit 音频缓存，因此传输到电脑的数据不是原始 PDM 流，而是已经抽取后的 PCM 近似数据。

工程中的采样率由 2.5 MHz 除以 128 得到：

```text
2,500,000 / 128 = 19,531.25 samples/s
```

由于 UART 发送的是一个字节一个 PCM 样本，接收端必须使用与 FPGA 实际采样率相同的 WAV 参数。当前采样率不是常见的 16 kHz 或 48 kHz，不能在电脑端直接假定为 44.1 kHz。

## 4. 推荐的 FPGA 数据路径

推荐增加如下数据路径：

```text
录音完成
    ↓
锁存 record_count
    ↓
从 audio_buffer 依次读取 PCM 样本
    ↓
UART TX 发送音频数据帧
    ↓
FT2232HQ USB-UART
    ↓
电脑虚拟串口
```

发送时应让录音状态机和发送状态机互斥：

```text
IDLE → RECORD → IDLE → SEND → IDLE
```

不要在 `RECORD` 状态下直接从当前单端口缓存读取并发送。当前 `audio_buffer` 是单端口同步 RAM，录音和回放不并发，见 `Sandbox/Microphone/MicrophoneA7/MicrophoneA7.srcs/sources_1/imports/rtl/audio_buffer.v`。最小改动方案是录音停止后锁存有效样本数量，再进入发送状态。

### 4.1 建议新增的顶层端口

```verilog
input  wire UART_RXD_OUT,  // 可选：电脑发送控制命令到 FPGA
output wire UART_TXD_IN    // FPGA 发送音频到电脑
```

如果发送由固定开关控制，也可以暂时只添加 `UART_TXD_IN`，使用未占用的按钮或开关启动发送。更完整的设计可以使用 UART RX 接收电脑命令，例如：

```text
电脑发送 'S' → FPGA 开始发送
电脑发送 'P' → FPGA 查询状态
```

### 4.2 UART 配置

建议初始使用以下配置：

| 参数 | 推荐值 |
|---|---|
| 波特率 | `460800` |
| 数据位 | 8 |
| 校验位 | 无 |
| 停止位 | 1 |
| 流控 | 无 |

使用 100 MHz 系统时钟时，UART 位周期为：

```text
100,000,000 / 460,800 ≈ 217 个系统时钟周期
```

实际 RTL 中应使用整数分频，并通过仿真检查 TX 波形。也可以选择 `230400` baud 以降低时序要求，但 `460800` 有更大的实时传输余量。

### 4.3 传输带宽计算

每个 8 bit PCM 样本使用 UART 8N1 发送时，实际占用 10 个串行 bit：

```text
音频数据率 = 19,531.25 samples/s × 10
           ≈ 195,312.5 bit/s
```

因此：

- `115200 baud` 不足以实时发送当前音频；
- `230400 baud` 理论上可以实时发送，但余量较小；
- `460800 baud` 适合当前 8 bit、约 19.5 kHz 音频；
- 如果只在录音结束后发送，发送速度可以低于实时要求，但总传输时间会增加。

一段最大长度录音包含 65,536 个字节。仅计算音频数据时，在 `460800 baud` 下发送时间约为：

```text
65,536 × 10 / 460,800 ≈ 1.42 s
```

## 5. 建议的数据帧格式

不要只发送裸 PCM 字节。音频数据中可能出现任意值，电脑端无法可靠判断传输开始、结束或长度。建议使用固定帧头、长度字段和校验字段。

一个简单的数据帧如下，所有多字节整数使用小端序：

| 字段 | 长度 | 内容 |
|---|---:|---|
| Magic | 4 字节 | ASCII `P` `C` `M` `1` |
| Sample rate | 4 字节 | 采样率，建议写入 `19531` |
| Sample width | 1 字节 | `8` |
| Channels | 1 字节 | `1` |
| Sample count | 4 字节 | 有效 PCM 样本数量 |
| Payload | N 字节 | 8 bit 无符号 PCM 样本 |
| Checksum | 2 字节 | Payload 的 CRC-16 |

对应的数据结构可以理解为：

```text
"PCM1" + sample_rate + sample_width + channels
      + sample_count + pcm_data + crc16
```

### 5.1 采样率字段

当前硬件采样率为 `19,531.25 Hz`，但整数 WAV header 通常使用整数采样率字段。建议 FPGA 和电脑端统一写入 `19531`，并在文档或帧协议中说明真实时钟由 `2.5 MHz / 128` 得到。

如果后续将麦克风时钟改为 2.4576 MHz，则 128 倍抽取后可以得到标准的 19.2 kHz；如果改为 2.048 MHz，则可以得到标准的 16 kHz。这样更适合语音处理和 WAV 播放，但属于另一个硬件参数设计。

### 5.2 无符号 PCM 转换

当前缓存样本是无符号格式，静音值约为 64。标准 8 bit PCM WAV 也通常使用无符号样本，并以 128 为静音中心。因此，电脑端保存 WAV 前可以将 FPGA 样本平移：

```text
wav_sample = clamp(fpga_sample + 64, 0, 255)
```

如果不做平移，声音波形会偏离标准 8 bit PCM 的中心，可能产生明显直流偏置。实际偏移量应根据 PDM 解码和录音效果调整，初始值使用 64。

另一种方式是保存为 16 bit signed PCM：

```text
signed_sample = (fpga_sample - 64) × 512
```

但这只是把 7 bit 左右的有效幅度扩展到 16 bit，并不会增加实际分辨率。初次验证建议保存为 8 bit 单声道 WAV。

## 6. 电脑端接收流程

### 6.1 安装和确认串口

1. 使用 J6 将 Nexys A7 连接到电脑。
2. 给开发板供电并下载包含 UART 功能的 bitstream。
3. 安装 FTDI Virtual COM Port 驱动（如果操作系统没有自动安装）。
4. 在系统设备列表中确认出现 FTDI 虚拟串口。
5. 记录串口设备名，例如 Windows 的 `COM5` 或 macOS 的 `/dev/cu.usbserial-*`。

J6 同时承担 JTAG 和 UART 功能。Vivado 可以使用同一根 USB 线下载 bitstream，串口程序则使用 FTDI 暴露的虚拟串口通道。

### 6.2 使用 Python 接收并生成 WAV

电脑端可以使用 `pyserial` 接收数据。下面的示例读取 `PCM1` 数据帧，并将 8 bit 无符号 PCM 保存为单声道 WAV。

```python
import struct
import sys
import time
import wave

import serial


PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-XXXX"
BAUDRATE = 460800


def read_exact(port, size):
    data = bytearray()
    while len(data) < size:
        chunk = port.read(size - len(data))
        if not chunk:
            raise TimeoutError("serial receive timeout")
        data.extend(chunk)
    return bytes(data)


with serial.Serial(PORT, BAUDRATE, timeout=2) as port:
    deadline = time.monotonic() + 10
    header = bytearray()
    while time.monotonic() < deadline:
        header += port.read(1)
        if header.endswith(b"PCM1"):
            break
        if len(header) > 4:
            del header[:-4]
    else:
        raise TimeoutError("PCM1 frame header not found")

    sample_rate = struct.unpack("<I", read_exact(port, 4))[0]
    sample_width = read_exact(port, 1)[0]
    channels = read_exact(port, 1)[0]
    sample_count = struct.unpack("<I", read_exact(port, 4))[0]
    samples = read_exact(port, sample_count)
    received_crc = struct.unpack("<H", read_exact(port, 2))[0]

if sample_width != 8 or channels != 1:
    raise ValueError("example only supports 8 bit mono audio")

with wave.open("recording.wav", "wb") as wav:
    wav.setnchannels(channels)
    wav.setsampwidth(sample_width // 8)
    wav.setframerate(sample_rate)
    wav.writeframes(samples)

print(f"saved recording.wav: {sample_count} samples at {sample_rate} Hz")
print(f"received CRC16: 0x{received_crc:04x}")
```

安装依赖并运行：

```bash
python3 -m pip install pyserial
python3 receive_audio.py /dev/cu.usbserial-XXXX
```

Windows 示例：

```bash
python receive_audio.py COM5
```

上面的示例假设 FPGA 已经按照本文件定义发送帧。CRC 只打印出来用于调试；正式使用时应在电脑端重新计算 CRC-16 并与 `received_crc` 比较。

## 7. FPGA 发送控制建议

推荐使用以下时序：

1. 将 `SW[0]` 置为 1，开始录音。
2. 将 `SW[0]` 置为 0，停止录音并保持缓存内容。
3. 通过另一个开关、按钮或 UART 命令启动发送。
4. FPGA 发送 `PCM1` 帧头、采样参数、样本数量、PCM 数据和 CRC。
5. 发送完成后回到空闲状态。
6. 电脑端检测到完整帧后写出 `recording.wav`。

发送期间建议：

- 禁止重新开始录音，避免覆盖发送中的 RAM；
- 保持 `record_count` 不变；
- 使用独立的发送地址计数器；
- 正确处理同步 RAM 的一拍读延迟；
- 发送状态通过 LED 指示；
- 发送完成后再允许播放或新一轮录音。

当前设计中，`record_count` 表示有效样本数，`audio_buffer` 的地址和读数据都是同步逻辑。发送状态机不能在发出读地址的同一拍就假设 `buf_dout` 已经是该地址的数据，需要增加一个读请求/数据有效阶段。

## 8. Vivado 中需要修改的内容

### 8.1 RTL 文件

至少需要新增：

- `uart_tx.v`：8N1 UART 发送器；
- 发送控制状态机：负责帧头、字段、缓存读取、CRC 和结束状态；
- `mic_recorder.v` 的 UART 端口和状态连接。

发送器的基本状态可以是：

```text
UART_IDLE
    ↓
UART_START_BIT
    ↓
UART_DATA_BITS
    ↓
UART_STOP_BIT
    ↓
UART_IDLE
```

上层发送控制状态机则负责：

```text
SEND_HEADER → SEND_METADATA → READ_BUFFER
            → SEND_SAMPLE → SEND_CRC → SEND_DONE
```

### 8.2 XDC 约束

在当前 `mic_recorder.xdc` 中增加：

```tcl
## USB-UART
set_property -dict { PACKAGE_PIN C4 IOSTANDARD LVCMOS33 } [get_ports { UART_TXD_IN }]
set_property -dict { PACKAGE_PIN D4 IOSTANDARD LVCMOS33 } [get_ports { UART_RXD_OUT }]
```

如果暂时不使用电脑发送命令，可以不添加 RX 端口和约束，只保留 TX。端口命名可以改成更清晰的 `UART_TX`，但必须确保端口与 XDC 的含义一致。

### 8.3 不建议使用 ILA 作为文件传输接口

Vivado ILA 适合观察少量内部信号和调试时序，不适合连续传输数万字节录音并在电脑上保存为音频文件。JTAG 也主要用于配置和调试。正式音频传输应使用 USB-UART；如果需要更高带宽，再考虑以太网或 microSD。

## 9. 可靠性检查

### 9.1 先发送固定测试数据

在接入真实麦克风数据前，建议让 FPGA 发送以下固定序列：

```text
00 01 02 03 ... FE FF
```

电脑端检查：

- 字节顺序是否正确；
- 是否丢字节；
- 帧长度是否正确；
- CRC 是否匹配；
- 串口波特率和 8N1 配置是否一致。

### 9.2 再发送 RAM 数据

确认固定数据无误后，先把 RAM 初始化为递增序列，再测试 RAM 读取和发送。最后才接入麦克风录音数据。这样可以区分 UART、RAM 读时序和 PDM 解码问题。

### 9.3 音频结果检查

生成 WAV 后，可以用音频播放器或 Python 检查：

- 文件是否能打开；
- 播放时长是否约为 `sample_count / 19531` 秒；
- 波形是否以正确的静音中心为基准；
- 是否存在明显的连续噪声、削波或直流偏置。

例如，65,536 个样本的预期时长约为：

```text
65,536 / 19,531.25 ≈ 3.36 s
```

## 10. 限制与可选改进

当前 8 bit 计数平均法适合基础录音、波形观察和传输验证，但不是高保真音频采集方案。参考资料建议较高音质时使用 `CIC + FIR` 抽取滤波器。

如果后续需求扩大，可以考虑：

- 使用 DDR2 保存更长录音；
- 使用 CIC/FIR 获得更好的频响和噪声性能；
- 将采样率调整为标准的 16 kHz、19.2 kHz 或 48 kHz；
- 通过 USB-UART 发送 16 bit PCM；
- 使用以太网进行实时音频传输；
- 使用 microSD 先保存文件，再由电脑读取。

以太网理论上提供更高带宽，但需要实现 RMII、MAC、数据包协议和电脑端网络接收程序。对于当前约 3.36 秒、8 bit、单声道录音，USB-UART 是实现成本最低且足够使用的方案。

## 11. 总结

完整实现需要以下四部分：

```text
1. FPGA 增加 UART TX 发送器
2. FPGA 从 audio_buffer 读取并封装 PCM 数据
3. XDC 将 UART TX 约束到 C4
4. 电脑端串口程序接收并保存 WAV
```

推荐先使用 `460800 baud, 8N1, 无流控`，以 `PCM1` 帧格式传输当前 8 bit PCM 数据。当前工程中的录音和板载音频播放功能可以保留，UART 发送作为录音完成后的新增工作模式。
