#!/usr/bin/env python3
"""仮想シリアルポートを作成し、受信データを表示するテストツール.

使い方:
    1. このスクリプトを起動:
        uv run python tools/virtual_serial_receiver.py

    2. 表示されたポートを使って core_dual_shock を起動:
        uv run python -m core_dual_shock --port /dev/pts/XX --dry-run

    または実際にシリアル送信:
        uv run python -m core_dual_shock --port /dev/pts/XX

pty標準ライブラリのみ使用。追加インストール不要。
"""

from __future__ import annotations

import os
import pty
import select
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core_dual_shock.tkg_transmitter import calc_crc8


def decode_frame(raw: str) -> str:
    """ASCIIフレーム文字列をデコードして人間が読める形式にする."""
    raw = raw.strip()
    try:
        values = [int(x, 16) for x in raw.split(",")]
    except ValueError:
        return f"  [parse error] {raw!r}"

    if len(values) != 7:
        return f"  [length error: {len(values)} bytes] {raw}"

    header, vel_x, vel_y, vel_yaw, firing, opt2, crc = values

    # Header
    is_estop = not bool(header & 0x80)
    datatype = (header >> 5) & 0x03
    timestamp = (header >> 2) & 0x07

    # Velocity (unsigned -> signed)
    def to_signed(v: int) -> int:
        return v if v < 128 else v - 256

    # Firing
    wheel_speed = (firing >> 6) & 0x03
    fire = (firing >> 4) & 0x03
    taimatu = (firing >> 2) & 0x03
    hand = (firing >> 1) & 0x01
    angle = firing & 0x01

    # OPT2
    speed_mode = (opt2 >> 7) & 0x01
    mg = (opt2 >> 5) & 0x03

    # CRC check
    frame_bytes = bytes(values)
    expected_crc = calc_crc8(frame_bytes)
    crc_ok = "OK" if crc == expected_crc else f"NG(expected {expected_crc:02x})"

    return (
        f"  ts={timestamp} estop={'Y' if is_estop else 'N'} dtype={datatype} "
        f"vel=({to_signed(vel_x):+4d},{to_signed(vel_y):+4d},{to_signed(vel_yaw):+4d}) "
        f"whl={wheel_speed} fire={fire} tai={taimatu} hand={hand} ang={angle} "
        f"spd={'slow' if speed_mode else 'std'} mg={mg} crc={crc_ok}"
    )


def main() -> None:
    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)

    print("=" * 60)
    print(f"仮想シリアルポート: {slave_name}")
    print()
    print("別ターミナルで以下を実行:")
    print(f"  uv run python -m core_dual_shock --port {slave_name}")
    print()
    print("Ctrl+C で終了")
    print("=" * 60)
    print()

    frame_count = 0
    buf = b""

    try:
        while True:
            readable, _, _ = select.select([master_fd], [], [], 1.0)
            if not readable:
                continue

            data = os.read(master_fd, 4096)
            if not data:
                break

            buf += data

            while b"\r\n" in buf:
                line, buf = buf.split(b"\r\n", 1)
                frame_count += 1
                raw_str = line.decode("ascii", errors="replace")
                decoded = decode_frame(raw_str)
                print(f"#{frame_count:4d} [{raw_str}]")
                print(decoded)

    except KeyboardInterrupt:
        print(f"\n終了 (受信フレーム数: {frame_count})")
    finally:
        os.close(master_fd)
        os.close(slave_fd)


if __name__ == "__main__":
    main()
