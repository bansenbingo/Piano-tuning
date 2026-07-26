"""Nexys A7 录音数据接收 & WAV 转换工具
========================================

硬件连接：
  将 Nexys A7 的 PROG USB 口（J6）通过 USB 线连接计算机。
  Windows 通常自动安装 FTDI VCP 驱动，设备管理器中出现 COM 端口。

串口参数：
  波特率 921,600 bps / 8 数据位 / 1 停止位 / 无校验 / 无流控

数据格式：
  A7 发送的每个字节是 8 bit 无符号 PCM 样本（PDM 计数器值 0-128，静音≈64）。
  采样率 19,531.25 Hz（100 MHz / 5120），单声道。
  总共发送 record_count 个字节（≤ 195,313，约 10 秒）。

依赖: pyserial (pip install pyserial)
"""

import sys
import serial
import wave
import struct
import os

# 端口可通过命令行覆盖: python receive_wav.py COM7
# Windows: COMx（FT2232 会出现两个 COM 口，UART 是编号较大的那个）
# macOS:   /dev/cu.usbserial-XXXXB   Linux: /dev/ttyUSB1
PORT        = sys.argv[1] if len(sys.argv) > 1 else "COM15"
BAUD        = 921600
SAMPLE_RATE = 19531

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
OUT_RAW     = os.path.join(SCRIPT_DIR, "recording.raw")
OUT_WAV     = os.path.join(SCRIPT_DIR, "recording.wav")


def main():
    print(f"打开串口 {PORT}, 波特率 {BAUD} ...")
    try:
        ser = serial.Serial(PORT, BAUD, timeout=60)
    except serial.SerialException as e:
        print(f"错误: 无法打开 {PORT} — {e}")
        print("请检查: 1) USB 线已连接  2) COM 端口号是否正确  3) 串口未被其他程序占用")
        sys.exit(1)

    print("等待 FPGA 传输... (在 A7 上先录音 SW0, 再上拨 SW14 开始发送)")
    print("按 Ctrl+C 可随时中断\n")

    raw_data = bytearray()
    try:
        while True:
            chunk = ser.read(4096)
            if not chunk:
                if raw_data:
                    break          # 数据流已结束
                continue           # 尚未开始, 继续等待
            if not raw_data:
                ser.timeout = 20    # 收到首字节后, 20 秒无数据即视为传输结束
            raw_data.extend(chunk)
            print(f"  已接收 {len(raw_data)} 字节", end="\r")
    except KeyboardInterrupt:
        print("\n用户中断接收")
    finally:
        ser.close()

    if not raw_data:
        print("未收到任何数据, 请确认 FPGA 已触发发送。")
        sys.exit(1)

    print(f"\n收到 {len(raw_data)} 字节 ({len(raw_data) / SAMPLE_RATE:.2f} 秒)")

    with open(OUT_RAW, "wb") as f:
        f.write(raw_data)
    print(f"原始数据 -> {OUT_RAW}")

    with wave.open(OUT_WAV, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(1)
        wav.setframerate(SAMPLE_RATE)
        for sample in raw_data:
            wav.writeframesraw(struct.pack("B", sample))
    print(f"WAV 文件 -> {OUT_WAV}")
    print("完成。")


if __name__ == "__main__":
    main()
