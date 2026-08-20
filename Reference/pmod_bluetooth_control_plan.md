# Nexys A7 Pmod 蓝牙远程控制方案

## 1. 方案概述

本方案使用 Nexys A7 的 Pmod 接口连接 BLE UART 蓝牙模块，让手机通过蓝牙控制 FPGA 中的录音和播放逻辑。

```text
手机
  │ BLE
  ▼
BLE 蓝牙模块
  │ 3.3 V UART
  ▼
Nexys A7 Pmod JA
  │
  ▼
FPGA UART 接收模块
  │
  ▼
录音/播放控制逻辑
```

蓝牙模块负责 BLE 无线链路和 GATT 数据传输，FPGA 只负责 UART 通信、命令解析以及控制现有录音/播放状态机。因此 FPGA 不需要实现复杂的蓝牙协议栈。

本方案面向控制命令，不建议通过 BLE 传输录音音频。音频传输应优先使用 Ethernet、USB 或其他高速接口。

## 2. 推荐硬件

建议选择带 3.3 V 供电和 3.3 V UART 电平的 BLE UART 模块，优先考虑以下类型：

- 基于 `CC2541` 的 HM-10 类 BLE 4.0 模块；
- 基于 `nRF52832` 或 `nRF52840` 的 BLE UART 模块；
- 支持 BLE GATT 自定义 Service/Characteristic 的其他透明传输模块。

如果希望快速验证，可以选择带稳压和电平转换电路的 HM-10 BLE UART 开发板，但需要确认具体模块确实支持 BLE，而不是只支持 Bluetooth Classic。不同厂家的 HM-10 兼容模块可能使用不同 AT 指令和 GATT UUID，应以实际模块数据手册为准。

### 2.1 HM-10 与 HC-05 的选择

| 项目 | HM-10 | HC-05 |
|---|---|---|
| 协议 | BLE 4.0 | Bluetooth Classic |
| 手机兼容性 | Android 和 iOS 通常都可以 | iOS 通常不支持 SPP 串口 |
| FPGA 接口 | UART | UART |
| 手机控制 | BLE GATT 应用 | 蓝牙串口应用 |
| 推荐用途 | Android/iOS 远程控制 | Android 或传统蓝牙设备 |

如果需要兼容 iPhone，应选择 BLE 模块，不要选择只支持 HC-05 类 SPP 的模块。

## 3. 蓝牙模块规格要求

采购模块时至少应满足以下要求：

| 参数 | 要求 |
|---|---|
| 无线协议 | BLE 4.0 或更高版本 |
| 工作频段 | 2.4 GHz ISM |
| 蓝牙角色 | 支持 Peripheral 模式 |
| 手机兼容性 | Android 和 iOS |
| 数据服务 | 支持 BLE GATT 自定义 Service/Characteristic |
| 传输方式 | BLE 数据与 UART 双向透明传输 |
| UART 电平 | 3.3 V CMOS |
| UART 波特率 | 至少支持 9600、19200、115200 baud |
| 推荐初始波特率 | 9600 baud |
| 数据格式 | 8 数据位、无校验、1 停止位，即 `8N1` |
| 供电电压 | 3.3 V，能够直接连接 Pmod 3.3 V |
| 工作电流 | 正常工作建议小于 50 mA |
| 峰值电流 | 建议小于 150 mA |
| UART 输入耐压 | 不得超过 3.3 V |
| 配置方式 | 支持 AT 指令或等效配置方式 |
| 连接状态 | 建议提供状态 LED 或 `STATE` 引脚 |
| 空旷通信距离 | 建议至少 5 到 10 m |
| 天线 | 板载 PCB 天线或外置天线 |
| 上电行为 | 上电后自动进入可连接状态 |

必须重点确认以下事项：

- 模块 UART 必须是 3.3 V 电平；
- 模块必须提供 BLE GATT 串口服务；
- 模块供电峰值电流必须满足；
- 不得把 5 V UART 信号直接接入 FPGA；
- 模块的 Service UUID、RX Characteristic UUID 和 TX Characteristic UUID 必须有明确资料。

## 4. Pmod JA 接线

建议使用 Pmod `JA`，连接关系如下：

| Pmod 引脚 | FPGA 端口 | 蓝牙模块连接 | 说明 |
|---|---|---|---|
| JA1 | `ble_rx` | `TXD` | 模块发送到 FPGA |
| JA2 | `ble_tx` | `RXD` | FPGA 发送到模块 |
| JA3 | `ble_state` | `STATE`，可选 | 连接状态输入 |
| JA4 | `ble_reset` | `EN/RESET`，可选 | 模块复位控制 |
| JA5 | GND | GND | 电源地 |
| JA6 | 3.3 V | VCC | 模块供电 |
| JA7 | 备用 | CTS，可选 | 硬件流控，初版不使用 |
| JA8 | 备用 | RTS，可选 | 硬件流控，初版不使用 |
| JA9 | 备用 | 保留 | 暂不连接 |
| JA10 | 备用 | 保留 | 暂不连接 |
| JA11 | GND | GND | 电源地 |
| JA12 | 3.3 V | VCC | 电源 |

最小连接只需要四根线：

```text
JA1  <--- 蓝牙模块 TXD
JA2  ---> 蓝牙模块 RXD
JA5  ----  GND
JA6  ----  3.3 V
```

UART 必须交叉连接：

```text
模块 TXD -> FPGA RX
FPGA TX   -> 模块 RXD
```

根据 `Reference/A7.xdc`，Pmod JA 的 FPGA 管脚为：

| Pmod 信号 | FPGA 管脚 |
|---|---|
| `JA1` | `C17` |
| `JA2` | `D18` |
| `JA3` | `E18` |
| `JA4` | `G17` |
| `JA7` | `D17` |
| `JA8` | `E17` |
| `JA9` | `F18` |
| `JA10` | `G18` |

当前参考约束中的 Pmod 信号是注释状态。实际工程使用时，需要取消相关注释，并在顶层模块定义对应端口。所有信号使用 `LVCMOS33`。

## 5. FPGA 逻辑结构

FPGA 端建议分为以下模块：

```text
uart_rx
  │
  ▼
命令缓冲与解析器
  │
  ├── 录音控制
  ├── 播放控制
  └── 状态查询
  │
  ▼
uart_tx
  │
  ▼
BLE 模块 -> 手机
```

### 5.1 UART 参数

第一版建议使用：

```text
Baud rate: 9600
Data bits: 8
Parity: None
Stop bits: 1
Flow control: None
```

9600 baud 已足够传输录音控制命令，并且分频误差要求较低。功能稳定后可以提高到 115200 baud。UART 接收建议使用 8 倍或 16 倍过采样。

当前工程使用 100 MHz 系统时钟。UART 分频器应根据实际系统时钟和目标波特率计算，避免直接假定一个固定计数值。

### 5.2 命令协议

第一版采用 ASCII 命令，以换行符结束：

```text
START_RECORD\n
STOP_RECORD\n
START_PLAYBACK\n
STATUS\n
```

FPGA 返回确认信息：

```text
OK RECORDING\n
OK STOPPED\n
OK PLAYING\n
STATUS IDLE\n
```

建议命令解析器具备以下行为：

- 接收字符直到 `LF` 或 `CRLF`；
- 对未知命令返回 `ERROR UNKNOWN_COMMAND`；
- 只有在当前状态允许时才执行录音或播放命令；
- 每条有效命令都返回明确确认信息；
- 上电后默认处于安全的 `IDLE` 状态。

如果后续需要更高可靠性，可以改用带校验和的二进制帧：

```text
0xAA 0x55 CMD LENGTH PAYLOAD CHECKSUM
```

## 6. 手机端工作流程

手机端需要支持 BLE GATT 特征读写的工具或应用，例如 BLE 调试工具、nRF Connect，或自行开发的 Android/iOS 应用。

推荐工作流程：

1. 手机扫描并连接 BLE 模块；
2. 手机向模块的 RX Characteristic 写入控制命令；
3. 模块通过 UART `TXD` 将命令发送到 FPGA；
4. FPGA 执行命令并通过 UART `TX` 返回结果；
5. 模块通过 TX Characteristic Notification 将结果通知手机。

实际使用的 UUID 由蓝牙模块固件决定，必须根据模块资料配置。

## 7. 供电、布线和调试注意事项

- Pmod 的 I/O 使用 3.3 V 逻辑，不能直接接收 5 V UART。
- 裸蓝牙模块通常只能使用 3.3 V；带开发板的模块是否支持 5 V 供电必须查看其资料，不能仅凭模块名称判断。
- BLE 模块平均电流较低，但发射时存在瞬时电流，模块应具有合适的去耦电容。
- 如果出现掉线、复位或通信乱码，应优先检查供电、电平、波特率和 TX/RX 是否交叉。
- 蓝牙天线应远离 FPGA、金属外壳、排线和其他大面积金属。
- 初期调试应保留板载 USB-UART，用于输出 FPGA 状态和对比测试。
- 不要使用 Pmod 同一组引脚驱动多个输出设备，避免总线冲突。

## 8. 推荐的实际落地配置

```text
蓝牙模块：3.3 V BLE UART 模块
推荐类型：HM-10 类或 nRF52832/nRF52840 模块
Pmod：JA
波特率：9600
数据格式：8N1
硬件流控：关闭
控制协议：ASCII 命令 + 换行
手机端：BLE GATT 调试 App
FPGA 端：UART RX/TX + 命令解析状态机
```

建议按以下顺序实施：

1. 先用 USB-UART 验证 FPGA UART 和命令解析；
2. 再连接 BLE 模块，确认模块可以独立发送和接收 UART 数据；
3. 使用手机 BLE 工具发送 `STATUS`，确认 FPGA 返回状态；
4. 接入 `START_RECORD`、`STOP_RECORD` 和 `START_PLAYBACK`；
5. 最后再考虑自定义手机应用和二进制协议。

## 9. 依据资料

- `Reference/A7.xdc:85` 到 `Reference/A7.xdc:124`：Pmod JA、JB、JC、JD 的 FPGA 管脚约束；
- `Reference/nexys-a7_rm.pdf` 第 10 节：Pmod 接口和电源说明；
- `Reference/nexys-a7_rm.pdf` 第 6 节：板载 USB-UART，可用于初期调试；
- `Reference/nexys-a7-d3-sch.pdf`：Pmod、FPGA 和板级电源连接关系；
- `Reference/microphone_rtl_implementation.md`：当前麦克风工程的录音和播放功能范围。
