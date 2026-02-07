# core_dual_shock

DualShock / DualSense コントローラーの入力を読み取り、正規化・デッドゾーン処理を行うPythonライブラリ。

## 対応デバイス

- DualShock 4 (USB / Bluetooth)
- DualSense

## 必要環境

- Linux
- Python 3.12 以上
- uv

## セットアップ

### 1. uv のインストール

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. リポジトリのクローン

```bash
git clone https://github.com/sadasue/core_dual_shock.git
cd core_dual_shock
```

### 3. 依存パッケージのインストール

```bash
uv sync
```

### 4. デバイスの権限設定

evdev でコントローラーにアクセスするには、`/dev/input/event*` への読み取り権限が必要です。

```bash
# 現在のユーザーを input グループに追加（再ログイン後に有効）
sudo usermod -aG input $USER
```

または、実行時に `sudo` を使用します。

## 使い方

### CLI モード (JSON出力)

50Hz で正規化済みの入力状態を JSON 行として stdout に出力します。

```bash
uv run python -m core_dual_shock
```

出力例:

```json
{"buttons": {"triangle": 0, "circle": 0, "cross": 1, "square": 0, ...}, "analog": {"left_x": 192, "left_y": 128, "right_x": 128, "right_y": 128, "L2": 0, "R2": 175}}
```

Ctrl+C で停止します。

### ライブラリとして使用

```python
from core_dual_shock.main import DualShockReader

reader = DualShockReader(deadzone=10)

for snapshot in reader:
    print(snapshot.buttons["cross"])   # 0 or 1
    print(snapshot.analog["left_x"])   # 0-255 (128が中立)
```

### キー名一覧

`snapshot.buttons` と `snapshot.analog` で使用できるキー名は以下の通りです。

#### ボタン (`snapshot.buttons[key]`) — 値: 0 (離す) / 1 (押す)

| キー名 | 説明 |
|---|---|
| `"triangle"` | △ ボタン |
| `"circle"` | ○ ボタン |
| `"cross"` | × ボタン |
| `"square"` | □ ボタン |
| `"L1"` | L1 ボタン |
| `"R1"` | R1 ボタン |
| `"L3"` | L3 (左スティック押し込み) |
| `"R3"` | R3 (右スティック押し込み) |
| `"dpad_up"` | 十字キー 上 |
| `"dpad_down"` | 十字キー 下 |
| `"dpad_left"` | 十字キー 左 |
| `"dpad_right"` | 十字キー 右 |
| `"select"` | SHARE / SELECT |
| `"start"` | OPTIONS / START |
| `"ps"` | PS ボタン |
| `"touchpad"` | タッチパッド押し込み |

#### アナログ (`snapshot.analog[key]`) — 値: 0-255

| キー名 | 説明 | 中立値 |
|---|---|---|
| `"left_x"` | 左スティック X 軸 | 128 |
| `"left_y"` | 左スティック Y 軸 | 128 |
| `"right_x"` | 右スティック X 軸 | 128 |
| `"right_y"` | 右スティック Y 軸 | 128 |
| `"L2"` | L2 トリガー | 0 |
| `"R2"` | R2 トリガー | 0 |

## テスト

```bash
uv run pytest tests/ -v
```
