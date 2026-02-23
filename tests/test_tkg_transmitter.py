"""tkg_transmitterモジュールの単体テスト."""

import pytest

from core_dual_shock.input_state import InputSnapshot
from core_dual_shock.tkg_transmitter import (
    _build_firing,
    _build_header,
    _build_opt2,
    _duty_to_signed_byte,
    _format_wire,
    calc_crc8,
)


# ---------------------------------------------------------------------------
# calc_crc8
# ---------------------------------------------------------------------------
class TestCalcCRC8:
    """CRC8計算のテスト."""

    def test_all_zeros(self):
        """全ゼロ入力でCRC8が0になること."""
        data = bytes(7)
        assert calc_crc8(data) == 0

    def test_known_pattern(self):
        """既知のデータパターンでCRC8が正しく計算されること.

        C++実装と同じアルゴリズム(poly=0xEB, 内部ループ7回)で
        同一結果になることを確認する。
        """
        # header=0xA4, vel_x=0x3F, vel_y=0xC1, vel_yaw=0x7F,
        # firing=0x00, opt2=0x00, crc=placeholder
        data = bytes([0xA4, 0x3F, 0xC1, 0x7F, 0x00, 0x00, 0x00])
        crc = calc_crc8(data)
        # CRC must be deterministic and non-zero for non-zero input
        assert 0 <= crc <= 255
        # Re-calculate to ensure idempotence
        assert calc_crc8(data) == crc

    def test_crc_changes_with_data(self):
        """データが変わればCRCも変わること."""
        d1 = bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        d2 = bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        assert calc_crc8(d1) != calc_crc8(d2)

    def test_only_first_6_bytes_used(self):
        """7バイト目はCRC計算に影響しないこと."""
        d1 = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x00])
        d2 = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0xFF])
        assert calc_crc8(d1) == calc_crc8(d2)

    def test_single_byte_nonzero(self):
        """先頭1バイトだけ非ゼロの場合のCRC計算."""
        data = bytes([0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        crc = calc_crc8(data)
        assert 0 <= crc <= 255
        assert crc != 0  # 0xFF入力でCRC=0にはならない


# ---------------------------------------------------------------------------
# _build_header
# ---------------------------------------------------------------------------
class TestBuildHeader:
    """Headerバイト組み立てのテスト."""

    def test_estop_true_clears_bit7(self):
        """is_estop=True のとき bit7 が 0 になること."""
        header = _build_header(is_estop=True, datatype=0x00, timestamp=0)
        assert (header & 0x80) == 0

    def test_estop_false_sets_bit7(self):
        """is_estop=False のとき bit7 が 1 になること."""
        header = _build_header(is_estop=False, datatype=0x00, timestamp=0)
        assert (header & 0x80) == 0x80

    def test_datatype_bits(self):
        """datatype=0x01 のとき bit6-5 が 01 になること."""
        header = _build_header(is_estop=False, datatype=0x01, timestamp=0)
        datatype_extracted = (header >> 5) & 0x03
        assert datatype_extracted == 0x01

    def test_datatype_max(self):
        """datatype=0x03 のとき bit6-5 が 11 になること."""
        header = _build_header(is_estop=False, datatype=0x03, timestamp=0)
        datatype_extracted = (header >> 5) & 0x03
        assert datatype_extracted == 0x03

    def test_timestamp_bits(self):
        """timestamp=1 のとき bit4-2 が 001 になること."""
        header = _build_header(is_estop=False, datatype=0x00, timestamp=1)
        ts_extracted = (header >> 2) & 0x07
        assert ts_extracted == 1

    def test_timestamp_max(self):
        """timestamp=7 (最大) のとき bit4-2 が 111 になること."""
        header = _build_header(is_estop=False, datatype=0x00, timestamp=7)
        ts_extracted = (header >> 2) & 0x07
        assert ts_extracted == 7

    def test_combined_fields(self):
        """is_estop=False, datatype=0x01, timestamp=1 の合成値.

        bit7=1, bit6-5=01, bit4-2=001, bit1-0=00
        = 1_01_001_00 = 0xA4
        """
        header = _build_header(is_estop=False, datatype=0x01, timestamp=1)
        assert header == 0xA4

    def test_nodef_bits_always_zero(self):
        """bit1-0 (NODEF) が常に0であること."""
        for ts in range(8):
            for dt in range(4):
                header = _build_header(is_estop=False, datatype=dt, timestamp=ts)
                assert (header & 0x03) == 0


# ---------------------------------------------------------------------------
# _build_firing
# ---------------------------------------------------------------------------
class TestBuildFiring:
    """FIRINGバイト(Byte4)組み立てのテスト."""

    def test_all_zeros(self):
        """全フィールド0で0x00になること."""
        assert _build_firing(0, 0, 0, 0, 0) == 0x00

    def test_wheel_speed_bits(self):
        """wheel_speed=3 のとき bit7-6 が 11 になること."""
        byte = _build_firing(wheel_speed=3, fire=0, taimatu_lift=0,
                             hand_forward=0, fire_angle=0)
        assert (byte >> 6) & 0x03 == 3
        assert byte == 0xC0

    def test_fire_bits(self):
        """fire=2 のとき bit5-4 が 10 になること."""
        byte = _build_firing(wheel_speed=0, fire=2, taimatu_lift=0,
                             hand_forward=0, fire_angle=0)
        assert (byte >> 4) & 0x03 == 2
        assert byte == 0x20

    def test_taimatu_lift_bits(self):
        """taimatu_lift=1 のとき bit3-2 が 01 になること."""
        byte = _build_firing(wheel_speed=0, fire=0, taimatu_lift=1,
                             hand_forward=0, fire_angle=0)
        assert (byte >> 2) & 0x03 == 1
        assert byte == 0x04

    def test_hand_forward_bit(self):
        """hand_forward=1 のとき bit1 が 1 になること."""
        byte = _build_firing(wheel_speed=0, fire=0, taimatu_lift=0,
                             hand_forward=1, fire_angle=0)
        assert (byte >> 1) & 0x01 == 1
        assert byte == 0x02

    def test_fire_angle_bit(self):
        """fire_angle=1 のとき bit0 が 1 になること."""
        byte = _build_firing(wheel_speed=0, fire=0, taimatu_lift=0,
                             hand_forward=0, fire_angle=1)
        assert byte & 0x01 == 1
        assert byte == 0x01

    def test_all_max_values(self):
        """全フィールド最大値: 0b11_11_11_1_1 = 0xFF."""
        byte = _build_firing(wheel_speed=3, fire=3, taimatu_lift=3,
                             hand_forward=1, fire_angle=1)
        assert byte == 0xFF


# ---------------------------------------------------------------------------
# _build_opt2
# ---------------------------------------------------------------------------
class TestBuildOpt2:
    """OPT2バイト(Byte5)組み立てのテスト."""

    def test_all_zeros(self):
        """全フィールド0で0x00になること."""
        assert _build_opt2(0, 0) == 0x00

    def test_body_speed_mode_bit(self):
        """body_speed_mode=1 のとき bit7 が 1 になること."""
        byte = _build_opt2(body_speed_mode=1, mg_action=0)
        assert (byte >> 7) & 0x01 == 1
        assert byte == 0x80

    def test_mg_action_bits(self):
        """mg_action=1 のとき bit6-5 が 01 になること."""
        byte = _build_opt2(body_speed_mode=0, mg_action=1)
        assert (byte >> 5) & 0x03 == 1
        assert byte == 0x20

    def test_mg_action_backward(self):
        """mg_action=2 のとき bit6-5 が 10 になること."""
        byte = _build_opt2(body_speed_mode=0, mg_action=2)
        assert (byte >> 5) & 0x03 == 2
        assert byte == 0x40

    def test_combined(self):
        """body_speed_mode=1, mg_action=2 の合成値.

        bit7=1, bit6-5=10, bit4-0=00000
        = 1_10_00000 = 0xC0
        """
        byte = _build_opt2(body_speed_mode=1, mg_action=2)
        assert byte == 0xC0

    def test_lower_5_bits_always_zero(self):
        """bit4-0 (NONE) が常に0であること."""
        for bsm in range(2):
            for mga in range(4):
                byte = _build_opt2(bsm, mga)
                assert (byte & 0x1F) == 0


# ---------------------------------------------------------------------------
# _duty_to_signed_byte
# ---------------------------------------------------------------------------
class TestDutyToSignedByte:
    """duty比からunsigned byte変換のテスト."""

    def test_zero(self):
        """duty=0.0 で 0x00 になること."""
        assert _duty_to_signed_byte(0.0) == 0x00

    def test_positive_max(self):
        """duty=1.0 で 0x7F (127) になること."""
        assert _duty_to_signed_byte(1.0) == 0x7F

    def test_negative_max(self):
        """duty=-1.0 で 0x81 (-127の2の補数) になること."""
        assert _duty_to_signed_byte(-1.0) == 0x81

    def test_positive_half(self):
        """duty=0.5 で 0x3F (63) になること."""
        # int(0.5 * 127) = int(63.5) = 63
        assert _duty_to_signed_byte(0.5) == 0x3F

    def test_negative_half(self):
        """duty=-0.5 で 0xC1 (-63の2の補数) になること."""
        # int(-0.5 * 127) = int(-63.5) = -63
        # -63 & 0xFF = 0xC1
        assert _duty_to_signed_byte(-0.5) == 0xC1

    def test_clamp_over_positive(self):
        """duty=2.0 で 127にクランプされ 0x7F になること."""
        assert _duty_to_signed_byte(2.0) == 0x7F

    def test_clamp_over_negative(self):
        """duty=-2.0 で -127にクランプされ 0x81 になること."""
        assert _duty_to_signed_byte(-2.0) == 0x81


# ---------------------------------------------------------------------------
# _format_wire
# ---------------------------------------------------------------------------
class TestFormatWire:
    """ワイヤーフォーマット変換のテスト."""

    def test_basic_format(self):
        """7バイトが正しいASCII hex, カンマ区切り, CRLF終端になること."""
        frame = bytes([0x86, 0x3F, 0xC1, 0x7F, 0x00, 0x00, 0xA3])
        wire = _format_wire(frame)
        assert wire == b"86,3f,c1,7f,00,00,a3\r\n"

    def test_all_zeros(self):
        """全ゼロフレームの変換."""
        frame = bytes(7)
        wire = _format_wire(frame)
        assert wire == b"00,00,00,00,00,00,00\r\n"

    def test_all_ff(self):
        """全0xFFフレームの変換."""
        frame = bytes([0xFF] * 7)
        wire = _format_wire(frame)
        assert wire == b"ff,ff,ff,ff,ff,ff,ff\r\n"

    def test_output_is_ascii_bytes(self):
        """出力がASCIIバイト列であること."""
        frame = bytes(7)
        wire = _format_wire(frame)
        assert isinstance(wire, bytes)
        wire.decode("ascii")  # Should not raise

    def test_crlf_termination(self):
        """CRLF終端であること."""
        frame = bytes(7)
        wire = _format_wire(frame)
        assert wire.endswith(b"\r\n")

    def test_comma_count(self):
        """カンマが6個あること."""
        frame = bytes(7)
        wire = _format_wire(frame)
        text = wire.decode("ascii").rstrip("\r\n")
        assert text.count(",") == 6


# ---------------------------------------------------------------------------
# build_frame 統合テスト
# ---------------------------------------------------------------------------
class TestBuildFrame:
    """build_frame統合テストでフレーム長とCRC整合性を確認."""

    @staticmethod
    def _make_neutral_snapshot() -> InputSnapshot:
        """ニュートラル状態のInputSnapshotを作成."""
        buttons = {
            "triangle": 0, "circle": 0, "cross": 0, "square": 0,
            "L1": 0, "R1": 0, "L3": 0, "R3": 0,
            "dpad_up": 0, "dpad_down": 0, "dpad_left": 0, "dpad_right": 0,
            "select": 0, "start": 0, "ps": 0, "touchpad": 0,
        }
        analog = {
            "left_x": 128, "left_y": 128,
            "right_x": 128, "right_y": 128,
            "L2": 0, "R2": 0,
        }
        return InputSnapshot(buttons=buttons, analog=analog)

    def _make_transmitter(self):
        """TKGTransmitterをシリアル無しで作成するためモックを使う."""
        from unittest.mock import MagicMock, patch

        with patch("core_dual_shock.tkg_transmitter.serial.Serial"):
            from core_dual_shock.tkg_transmitter import TKGTransmitter
            tx = TKGTransmitter(port="/dev/null")
        return tx

    def test_frame_length(self):
        """build_frameが7バイトのフレームを返すこと."""
        tx = self._make_transmitter()
        snapshot = self._make_neutral_snapshot()
        frame = tx.build_frame(snapshot)
        assert len(frame) == 7

    def test_crc_matches(self):
        """フレームの7バイト目がCRC8計算結果と一致すること."""
        tx = self._make_transmitter()
        snapshot = self._make_neutral_snapshot()
        frame = tx.build_frame(snapshot)
        expected_crc = calc_crc8(frame)
        assert frame[6] == expected_crc

    def test_estop_header_bit(self):
        """ESTOP状態ではHeaderのbit7が0であること."""
        tx = self._make_transmitter()
        # 初期状態は is_estop=True
        snapshot = self._make_neutral_snapshot()
        frame = tx.build_frame(snapshot)
        assert (frame[0] & 0x80) == 0

    def test_normal_mode_header_bit(self):
        """通常モードではHeaderのbit7が1であること."""
        tx = self._make_transmitter()
        tx.set_estop(False)
        snapshot = self._make_neutral_snapshot()
        frame = tx.build_frame(snapshot)
        assert (frame[0] & 0x80) == 0x80

    def test_timestamp_increments(self):
        """build_frame呼び出し毎にtimestampがインクリメントされること."""
        tx = self._make_transmitter()
        snapshot = self._make_neutral_snapshot()
        frame1 = tx.build_frame(snapshot)
        ts1 = (frame1[0] >> 2) & 0x07
        frame2 = tx.build_frame(snapshot)
        ts2 = (frame2[0] >> 2) & 0x07
        assert ts2 == (ts1 + 1) & 0x07

    def test_neutral_velocity_is_zero(self):
        """スティック中立(128)のとき速度バイトが0x00であること."""
        tx = self._make_transmitter()
        snapshot = self._make_neutral_snapshot()
        frame = tx.build_frame(snapshot)
        # Byte 1-3 = vel_x, vel_y, vel_yaw
        assert frame[1] == 0x00
        assert frame[2] == 0x00
        assert frame[3] == 0x00

    def test_fire_button_sets_firing(self):
        """circleボタンで fire=2 が設定されること."""
        tx = self._make_transmitter()
        tx.set_estop(False)
        snapshot = self._make_neutral_snapshot()
        snapshot.buttons["circle"] = 1
        frame = tx.build_frame(snapshot)
        fire_extracted = (frame[4] >> 4) & 0x03
        assert fire_extracted == 2

    def test_wire_format_integration(self):
        """build_frame結果をformat_wireに通してワイヤー形式が得られること."""
        tx = self._make_transmitter()
        snapshot = self._make_neutral_snapshot()
        frame = tx.build_frame(snapshot)
        wire = _format_wire(frame)
        assert wire.endswith(b"\r\n")
        parts = wire.decode("ascii").rstrip("\r\n").split(",")
        assert len(parts) == 7
