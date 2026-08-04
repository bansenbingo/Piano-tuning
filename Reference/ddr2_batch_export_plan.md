# 实现计划：Nexys A7 多次录音 → DDR2 存储 → 统一批量导出至电脑

> 状态：已确认方案（Windows + Vivado 环境，DDR2 存储，录完后一次性统一上传）
> 日期：2026-08-03
> 关联：`Sandbox/Microphone/UploadWav/rtl/`、`Sandbox/Microphone/UploadWav/UploadSound/`、`transport.md`、`A7.md`、`mic.md`

---

## 1. 背景与可行性

`Sandbox/Microphone/UploadWav/` 已具备完整的音频采集与 UART 传输链路，且 `UploadSound` Vivado 工程已成功综合实现（时序满足、0 error），bitstream 已生成：

```text
录音(SW0) → audio_buffer(256 KiB) → SEND 状态机 → uart_tx(921,600, 8N1)
        → FT2232HQ(D4) → J6 USB → PC 虚拟串口 → receive_wav.py → .raw/.wav
```

现有链路的唯一瓶颈：

- `audio_buffer` 仅为片上 256 KiB 单端口 RAM，只能存一段约 10 秒的录音；
- 无多段（take）管理，无法"多次录音、板上保存、统一上传"。

**结论：可实现。** 方案为用板上 **128 MiB DDR2 SDRAM** 替换 `audio_buffer`，增加分段表管理多段录音，按一次 BTNC 将所有录音以单帧批量上传。

---

## 2. 总体架构

```text
M_DATA → pdm_decoder(100 MHz) ──┐
                                ├→ 写打包(8样本/64bit) → 异步FIFO → MIG写FSM
SW0 录音控制 ──→ take_table(起始地址+样本数)                    │
                                ├────────────────────────→ DDR2(128 MiB)
SW15 回放 ────→ 读请求FSM ←──── 异步FIFO(回传数据) ←─ MIG读FSM
                                │
BTNC 批量上传 ─→ 帧封装(表头+各段长度+数据+CRC16) → uart_tx → UART_TXD(D4)
                                │
PC: receive_wav.py → 解析帧 → 每段保存 recording_001.wav ...
```

要点：

- 音频逻辑保持 100 MHz；DDR2 MIG 用户接口为其自身时钟域（4:1 比率时约 81.25 MHz）；跨时钟域用异步 FIFO。
- 因为 RECORD / PLAYBACK / SEND 三种状态互斥，DDR2 任一时刻只有一个客户端访问，无复杂仲裁。

---

## 3. Vivado 工程准备（Windows，Z:\Piano-tuning）

1. 打开 `Sandbox/Microphone/UploadWav/UploadSound/UploadSound.xpr`（工程路径为 Z: 盘，需位于 `Z:\Piano-tuning`）。
2. 新建 **MIG 7 Series** IP（`mig_7series_0`）。推荐直接采用 Digilent 官方 Nexys4DDR（与 Nexys A7-100T 相同）Music Looper 演示工程中**已在板上验证可工作**的配置（`mig_b.prj`，可在 MIG GUI 中直接导入），参数如下：

   | 项目 | 值（Digilent 官方实测） | 备注 |
   |---|---|---|
   | 内存类型 | DDR2 SDRAM | |
   | 内存型号 | MT47H64M16HR-25E（-25E 速度等级） | |
   | 数据位宽 | 16 | |
   | 内存时钟周期 | **3333 ps（≈300 MHz → 600 MT/s）** | 本地 `A7.md` §7.3 建议 3077 ps（650 MT/s）亦可，Digilent 实测值更保守可靠 |
   | Burst Length / Type | 8 / Sequential | |
   | CAS Latency / AL / Write Recovery | 5 / 0 / 5 | |
   | ODT (RTT) | 50 Ω | |
   | 输出驱动 / DQS# | Full strength / Enable | |
   | 输入时钟 | **200 MHz（`clk_wiz` 从板上 100 MHz 生成，接 MIG `sys_clk_i`）** | MIG 内部 MMCM 据此产生 300 MHz 内存时钟与 PHY 时钟 |
   | System / Reference Clock | No Buffer / Use System Clock | |
   | PHY 比率 | **4:1** | DDR2 的 4:1 用户接口为 **128-bit 数据 @ 75 MHz**（不是 64-bit） |
   | 用户接口 | NATIVE（`app_*` 信号） | 也可选 AXI4 |
   | VCCAUX_IO | 1.8 V | |
   | 内部 Vref / 复位极性 | 启用 / ACTIVE LOW | |
   | 地址结构 | Row 13 / Col 10 / Bank 3（app 地址 27 bit） | 128 MiB 字节寻址 |
   | 关键时序参数 | twtr=7.5, trrd=10, trefi=7.8, tfaw=45, trtp=7.5, trfc=127.5, trp=12.5, tras=40, trcd=15（ns） | MIG 自动计算 |
   | 器件 | xc7a100tcsg324-1 | |

3. **DDR 引脚约束由 MIG 自动生成**，切勿在 `upload_wav.xdc` 中手动约束 DDR 引脚。
   （注意：本地 `A7.md` §3.16 中 `DDR_LDQS_P/N`、`DDR_UDQS_P/N` 的引脚记录有误——mig.prj 实测为 DQS_P[0]=U9、DQS_N[0]=V9、DQS_P[1]=U2、DQS_N[1]=V2；因约束由 MIG 自动生成，不影响实现，仅作勘误。）
4. 将 MIG 输出约束文件与示例 wrapper 加入工程，运行综合/实现验证时序。

---

## 4. 新增 / 修改 RTL（`UploadWav/rtl/`）

### 4.1 `ddr_store.v`（新增）

MIG native UI 封装：

- **写路径**：100 MHz 域的 8-bit 采样字节 → 按 8 字节打包为 64-bit → 异步 FIFO → MIG 写 FSM（`app_en`/`app_wdf_*`）连续写入递增地址。
- **读路径**：读请求 FSM 预读 → 数据回传 FIFO → 100 MHz 域按字节输出。
- 因状态互斥，写/读由 RECORD / PLAYBACK / SEND 状态选择，内部用简单多路选择即可。

### 4.2 `take_table.v`（新增）

- 记录每段 take 的起始 DDR2 地址与样本数（小型 BRAM 或寄存器堆，≥128 段）；
- 保存当前段数 `num_takes`、下一写入地址指针；
- 每段样本数用 32-bit 计数，单段理论上限远超 DDR2 容量，不设固定段长限制。

### 4.3 `mic_recorder.v`（修改）

- 接入 DDR2 端口（MIG `app_*` 信号）；
- 操作逻辑：

  | 输入 | 行为 |
  |---|---|
  | SW0 | 录音启/停；每次录音结束自动追加为一段新 take（自动分配 DDR2 地址） |
  | BTNC | 将**全部** take 顺序发送到 PC（LED14 指示发送中） |
  | SW15 | 顺序回放全部 take |
  | SW1 或 BTNU | 清空全部 take（建议，SW1 当前未用） |

- 可选项：7 段数码管显示当前 take 数。

### 4.4 `upload_wav.xdc`（修改）

- 新增 SW1（或 BTNU）引脚约束（若采用该清空方式）；
- 其余约束不变；DDR 引脚约束来自 MIG 生成的 XDC。

### 4.5 统一批量上传帧格式（按 `transport.md` §5 的 PCM1 扩展）

所有多字节整数使用小端序：

| 字段 | 长度 | 内容 |
|---|---:|---|
| Magic | 4 B | ASCII `P` `C` `M` `1` |
| Sample rate | 4 B | `19531` |
| Sample width | 1 B | `8` |
| Channels | 1 B | `1` |
| Num takes | 1 B | 本次上传的录音段数 |
| Take counts | 4 B × N | 每段样本数，按 take 顺序 |
| Payload | Σ counts B | 所有 take 的 8-bit 无符号 PCM 样本拼接 |
| Checksum | 2 B | Payload 的 CRC-16 |

PC 端一次收完、按段数拆分，避免逐段握手；发送期间禁止录音。

---

## 5. PC 端脚本（重写 `receive_wav.py`）

- 串口参数不变：921,600 bps / 8 数据位 / 1 停止位 / 无校验 / 无流控；
- 解析帧头、段数、各段样本数，校验 CRC-16；
- 每段保存 `recording_001.wav`、`recording_002.wav`、…（19,531 Hz、8-bit 单声道）；
- 修正提示文案（触发发送的是 BTNC，而非开关）；
- 依赖仍为 `pyserial`。

---

## 6. 验证步骤（按 `transport.md` §9 的可靠性检查）

1. **固定数据测试**：DDR2 写入递增序列 `00 01 02 … FE FF` → 读回 → UART 发出 → PC 校验字节顺序、长度、CRC。
2. **分段录音测试**：录 3~5 段不同长度的音频 → 按 BTNC 一次上传 → 检查每段 WAV 的时长与内容。
3. **边界测试**：连续录音直到 DDR2 写满 / take 表满；发送中禁止重新录音；发送完成后才允许回放或新一轮录音。

---

## 7. 带宽与容量估算

| 项目 | 值 |
|---|---|
| DDR2 容量 | 128 MiB ≈ 1.34 亿字节（8-bit 样本）≈ 114 分钟音频 |
| 采样率 | 19,531.25 Hz（100 MHz / 5120，非标准值，WAV 按 19531 写入） |
| UART 有效数据率 | 92,160 B/s（921,600 baud，8N1 每字节 10 bit） |
| 单段 10 s 录音上传耗时 | 约 2.1 s |
| 满 128 MiB 上传耗时 | 约 24 分钟（实际按录音总量远小于此） |

---

## 8. 工作量与风险

- **主要工作量**：MIG IP 配置 + `ddr_store.v` 跨时钟域与读写 FSM（约 300–500 行 RTL），这是"容量大"方案的固有成本。
- **风险 1**：MIG 集成耗时超出预期。可选折中：退回片内 BRAM 多段方案（4 × 3.36 s），改动小但容量有限。
- **风险 2**：非标准采样率 19,531.25 Hz 只影响 WAV 元数据，不影响播放。
- **不采用**：ILA/JTAG 作为传输接口（不适合连续大数据量文件传输，见 `transport.md` §8.3）。

---

## 9. 实施顺序

1. MIG IP 配置与工程接入（含时序验证）；
2. `ddr_store.v`（写/读 FSM + 异步 FIFO）；
3. `take_table.v`；
4. `mic_recorder.v` 顶层改造（多 take 管理、批量发送帧封装）；
5. `receive_wav.py` 重写（帧解析 + 多文件输出）；
6. 固定数据测试 → 分段录音测试 → 边界测试；
7. 更新本文档/操作指南并提交。
