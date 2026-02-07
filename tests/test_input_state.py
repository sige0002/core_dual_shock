"""InputStateクラスの単体テスト."""

import pytest

from core_dual_shock.input_state import (
    BUTTON_NEUTRAL,
    BUTTONS,
    STICK_NEUTRAL,
    TRIGGER_NEUTRAL,
    InputState,
)


class TestInputState:
    """InputStateクラスのテストケース."""

    def test_initial_buttons_are_neutral(self):
        """初期状態でボタンが全て0であること."""
        state = InputState()
        snapshot = state.snapshot()

        for button in BUTTONS:
            assert snapshot.buttons[button] == BUTTON_NEUTRAL

    def test_initial_analog_values(self):
        """初期状態でスティックが128、トリガーが0であること."""
        state = InputState()
        snapshot = state.snapshot()

        # スティックは中立位置(128)
        assert snapshot.analog["left_x"] == STICK_NEUTRAL
        assert snapshot.analog["left_y"] == STICK_NEUTRAL
        assert snapshot.analog["right_x"] == STICK_NEUTRAL
        assert snapshot.analog["right_y"] == STICK_NEUTRAL

        # トリガーは0
        assert snapshot.analog["L2"] == TRIGGER_NEUTRAL
        assert snapshot.analog["R2"] == TRIGGER_NEUTRAL

    def test_update_button_reflects_in_snapshot(self):
        """update_button後にsnapshotで値が反映されること."""
        state = InputState()

        # ボタンを押す
        state.update_button("cross", 1)
        snapshot = state.snapshot()

        assert snapshot.buttons["cross"] == 1
        # 他のボタンは影響を受けない
        assert snapshot.buttons["triangle"] == 0

    def test_update_analog_reflects_in_snapshot(self):
        """update_analog後にsnapshotで値が反映されること."""
        state = InputState()

        # スティックを傾ける
        state.update_analog("left_x", 200)
        snapshot = state.snapshot()

        assert snapshot.analog["left_x"] == 200
        # 他のアナログチャンネルは影響を受けない
        assert snapshot.analog["left_y"] == STICK_NEUTRAL

    def test_multiple_updates_reflect_in_snapshot(self):
        """複数チャンネルを更新してsnapshotで全て反映されること(同時入力テスト)."""
        state = InputState()

        # 複数のボタンとアナログを同時に更新
        state.update_button("cross", 1)
        state.update_button("triangle", 1)
        state.update_analog("left_x", 50)
        state.update_analog("right_y", 200)
        state.update_analog("L2", 100)

        snapshot = state.snapshot()

        # 全ての更新が反映されている
        assert snapshot.buttons["cross"] == 1
        assert snapshot.buttons["triangle"] == 1
        assert snapshot.analog["left_x"] == 50
        assert snapshot.analog["right_y"] == 200
        assert snapshot.analog["L2"] == 100

        # 更新していないチャンネルはニュートラル値のまま
        assert snapshot.buttons["circle"] == 0
        assert snapshot.analog["right_x"] == STICK_NEUTRAL

    def test_reset_returns_all_channels_to_neutral(self):
        """resetで全チャンネルがニュートラルに戻ること."""
        state = InputState()

        # 複数のチャンネルを更新
        state.update_button("cross", 1)
        state.update_button("square", 1)
        state.update_analog("left_x", 255)
        state.update_analog("R2", 200)

        # 値が変わっていることを確認
        snapshot_before = state.snapshot()
        assert snapshot_before.buttons["cross"] == 1
        assert snapshot_before.analog["left_x"] == 255

        # リセット
        state.reset()

        # 全てニュートラルに戻る
        snapshot_after = state.snapshot()

        # ボタンは全て0
        for button in BUTTONS:
            assert snapshot_after.buttons[button] == BUTTON_NEUTRAL

        # スティックは128
        assert snapshot_after.analog["left_x"] == STICK_NEUTRAL
        assert snapshot_after.analog["left_y"] == STICK_NEUTRAL
        assert snapshot_after.analog["right_x"] == STICK_NEUTRAL
        assert snapshot_after.analog["right_y"] == STICK_NEUTRAL

        # トリガーは0
        assert snapshot_after.analog["L2"] == TRIGGER_NEUTRAL
        assert snapshot_after.analog["R2"] == TRIGGER_NEUTRAL
