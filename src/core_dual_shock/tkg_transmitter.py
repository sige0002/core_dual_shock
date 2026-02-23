"""TKG通信プロトコルモジュール.

7バイトの論理フレームを組み立て、ASCIIテキスト形式でシリアル送信する。
ワイヤーフォーマット: "%02x,%02x,%02x,%02x,%02x,%02x,%02x\r\n"
"""

from __future__ import annotations

import serial

from core_dual_shock.input_state import InputSnapshot


def calc_crc8(data: bytes) -> int:
    """TKG独自CRC8を計算する.

    内部ループが7回（標準CRC-8は8回）。元C++実装に準拠。

    Args:
        data: 7バイトのフレームデータ（先頭6バイトが計算対象）

    Returns:
        CRC8値 (0-255)
    """
    poly = 0xEB
    crc = 0
    for i in range(6):
        crc ^= data[i]
        for _ in range(7):
            if (crc & 0x80) == 0x80:
                crc = poly ^ ((crc << 1) & 0xFF)
            else:
                crc = (crc << 1) & 0xFF
    return crc


def _duty_to_signed_byte(duty: float) -> int:
    """duty比 (-1.0~1.0) を unsigned byte (0x00-0xFF) に変換.

    内部で signed char (-127~127) にクランプし、2の補数表現で返す。
    """
    val = max(-127, min(127, int(duty * 127)))
    return val & 0xFF


def _stick_to_duty(value: int) -> float:
    """スティック値 (0-255, 中立128) を duty比 (-1.0~1.0) に変換."""
    return (value - 128) / 128.0


def _build_header(is_estop: bool, datatype: int, timestamp: int) -> int:
    """Headerバイトを組み立てる.

    Bit7: IS_ESTOP (0=ESTOP有効, 1=通常)
    Bit6-5: DATATYPE
    Bit4-2: TIMESTAMP
    Bit1-0: 未定義(0)
    """
    header = 0
    header |= (0 if is_estop else 1) << 7
    header |= (datatype & 0x03) << 5
    header |= (timestamp & 0x07) << 2
    return header


def _build_firing(
    wheel_speed: int,
    fire: int,
    taimatu_lift: int,
    hand_forward: int,
    fire_angle: int,
) -> int:
    """FIRINGバイト(Byte4)を組み立てる."""
    byte = 0
    byte |= (wheel_speed & 0x03) << 6
    byte |= (fire & 0x03) << 4
    byte |= (taimatu_lift & 0x03) << 2
    byte |= (hand_forward & 0x01) << 1
    byte |= fire_angle & 0x01
    return byte


def _build_opt2(body_speed_mode: int, mg_action: int) -> int:
    """OPT2バイト(Byte5)を組み立てる."""
    byte = 0
    byte |= (body_speed_mode & 0x01) << 7
    byte |= (mg_action & 0x03) << 5
    return byte


def _format_wire(frame: bytes) -> bytes:
    """7バイトの論理フレームをワイヤーフォーマットに変換.

    出力例: b"86,3f,c1,7f,00,00,a3\\r\\n"
    """
    text = ",".join(f"{b:02x}" for b in frame) + "\r\n"
    return text.encode("ascii")


# --- データ型定数 ---
DATATYPE_CMD1 = 0x01


class TKGTransmitter:
    """TKG通信プロトコルでデータをシリアル送信するクラス."""

    def __init__(self, port: str, baudrate: int = 115200):
        """シリアルポートを初期化.

        Args:
            port: シリアルポート名 (例: "/dev/ttyUSB0")
            baudrate: ボーレート (デフォルト: 115200)
        """
        self._serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        self._timestamp: int = 0
        self._is_estop: bool = True

        # 状態保持が必要なフィールド
        self._wheel_speed: int = 0
        self._hand_forward: int = 0

    def build_frame(self, snapshot: InputSnapshot) -> bytes:
        """InputSnapshotを7バイトの論理フレームに変換.

        Args:
            snapshot: コントローラーの入力スナップショット

        Returns:
            7バイトのフレームデータ
        """
        buttons = snapshot.buttons
        analog = snapshot.analog

        # --- Header ---
        self._timestamp = (self._timestamp + 1) & 0x07
        header = _build_header(self._is_estop, DATATYPE_CMD1, self._timestamp)

        # --- 速度指令 (Byte 1-3) ---
        vel_x = _duty_to_signed_byte(-_stick_to_duty(analog.get("left_y", 128)))
        vel_y = _duty_to_signed_byte(-_stick_to_duty(analog.get("left_x", 128)))
        vel_yaw = _duty_to_signed_byte(_stick_to_duty(analog.get("right_x", 128)))

        # --- 速度モード (Byte 5) ---
        body_speed_mode = 0 if buttons.get("L1", 0) else 1

        # --- ホイール速度 (エッジ検出で段階変更) ---
        # wheel_speedは状態保持（build_frame外部からset_wheel_speedで制御）

        # --- 発射制御 ---
        fire = 0
        if buttons.get("circle", 0):
            fire = 2  # 連射
        elif buttons.get("cross", 0):
            fire = 1  # 単発

        fire_angle = buttons.get("triangle", 0)

        # --- 松明リフト ---
        taimatu_lift = 0
        if buttons.get("dpad_up", 0):
            taimatu_lift = 1  # 上昇
        elif buttons.get("dpad_down", 0):
            taimatu_lift = 2  # 下降

        # --- ハンド ---
        if buttons.get("square", 0):
            self._hand_forward = 1
        elif buttons.get("R1", 0):
            self._hand_forward = 0

        # --- MG ---
        mg_action = 0
        if buttons.get("dpad_right", 0):
            mg_action = 1  # 前進
        elif buttons.get("dpad_left", 0):
            mg_action = 2  # 後退

        # --- ESTOP時のオーバーライド ---
        if self._is_estop:
            self._wheel_speed = 0
            self._hand_forward = 0
            taimatu_lift = 0

        # --- バイト組み立て ---
        firing = _build_firing(
            self._wheel_speed, fire, taimatu_lift,
            self._hand_forward, fire_angle,
        )
        opt2 = _build_opt2(body_speed_mode, mg_action)

        # --- CRC8計算 ---
        data = bytes([header, vel_x, vel_y, vel_yaw, firing, opt2, 0x00])
        crc = calc_crc8(data)
        return bytes([header, vel_x, vel_y, vel_yaw, firing, opt2, crc])

    def send(self, frame: bytes) -> None:
        """フレームをワイヤーフォーマットに変換してシリアル送信.

        Args:
            frame: 7バイトの論理フレーム
        """
        wire_data = _format_wire(frame)
        self._serial.write(wire_data)

    def set_estop(self, is_estop: bool) -> None:
        """緊急停止状態を設定.

        Args:
            is_estop: True=ESTOP有効, False=通常動作
        """
        self._is_estop = is_estop

    def wheel_speed_up(self) -> None:
        """ホイール速度を1段階上げる（最大3）."""
        if self._wheel_speed < 3:
            self._wheel_speed += 1

    def wheel_speed_down(self) -> None:
        """ホイール速度を1段階下げる（最小0）."""
        if self._wheel_speed > 0:
            self._wheel_speed -= 1

    def close(self) -> None:
        """シリアルポートをクローズ."""
        if self._serial.is_open:
            self._serial.close()
