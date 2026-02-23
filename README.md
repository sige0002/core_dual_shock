# core_dual_shock

DualShock / DualSense コントローラーの入力を読み取り、正規化・デッドゾーン処理を行うPythonライブラリ。
遠隔ロボット操縦など、コントローラー入力を外部デバイスへ転送する用途を想定。

## 対応デバイス

- DualShock 4 (USB / Bluetooth)
- DualSense

## モジュール構成

```
src/core_dual_shock/
├── device.py            # evdevでコントローラーを自動検出し、イベント読み取りを提供
├── input_state.py       # 全チャンネルの生値をスレッドセーフに保持し、スナップショットを返す
├── mapper.py            # デバイスプロファイルに基づき正規化・デッドゾーン処理を行う
├── profile_loader.py    # profiles/ 内のYAMLを読み込み、evdevコードを解決する
├── main.py              # DualShockReaderクラス（イテレータ）とCLIエントリーポイント
├── tkg_transmitter.py   # TKG通信プロトコル実装（フレーム組み立て・シリアル送信）
└── profiles/
    ├── dualshock4.yaml  # DualShock4のボタン/軸/デバイスID定義
    └── dualsense.yaml   # DualSenseのボタン/軸/デバイスID定義
```

**処理の流れ:**

1. `device.py` が `/dev/input/` から対応コントローラーを検出
2. `profile_loader.py` が YAML からボタン/軸の evdev コード対応表を読み込む
3. `main.py` のイベントループが evdev イベントを受信し `input_state.py` の状態テーブルを更新
4. 50Hz 周期で `mapper.py` がスナップショットを正規化・デッドゾーン処理して返す

## 必要環境

- Linux
- Python 3.12 以上
- uv
- DualShock 4 または DualSense がUSBまたはBluetoothで接続済み

## セットアップ

### 1. システムパッケージのインストール

Python拡張モジュールのビルドやevdevの利用に必要なパッケージをインストールします。

```bash
sudo apt update
sudo apt install -y build-essential python3-dev libffi-dev libudev-dev
```

| パッケージ | 用途 |
|---|---|
| `build-essential` | gcc, make 等のビルドツール一式 |
| `python3-dev` | Python C拡張のヘッダファイル |
| `libffi-dev` | ctypes / cffi のビルドに必要 |
| `libudev-dev` | evdev のビルドに必要 |

### 2. uv のインストール

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. リポジトリのクローン

```bash
git clone https://github.com/sadasue/core_dual_shock.git
cd core_dual_shock
```

### 4. 依存パッケージのインストール

```bash
uv sync
```

### 5. デバイスの権限設定

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

`DualShockReader` はイテレータプロトコルを実装しています。`iter()` / `next()` で1フレームずつ取得できます。

```python
from core_dual_shock.main import DualShockReader

reader = DualShockReader(deadzone=15)
it = iter(reader)

try:
    while True:
        snapshot = next(it)
        # snapshot.buttons: dict[str, int]  — 各ボタン 0 or 1
        # snapshot.analog:  dict[str, int]  — 各軸 0-255
        print(snapshot.buttons["cross"], snapshot.analog["left_x"])
except KeyboardInterrupt:
    reader.stop()
```

### 使用例: UART でロボットへ送信

コントローラー入力を pyserial 経由で UART 送信する例です。

```python
import struct

import serial

from core_dual_shock.main import DualShockReader

ser = serial.Serial("/dev/ttyUSB0", 115200)
reader = DualShockReader(deadzone=15)
it = iter(reader)

try:
    while True:
        snapshot = next(it)

        # スティック + トリガーを 6 バイトにパック
        payload = struct.pack(
            "6B",
            snapshot.analog["left_x"],
            snapshot.analog["left_y"],
            snapshot.analog["right_x"],
            snapshot.analog["right_y"],
            snapshot.analog["L2"],
            snapshot.analog["R2"],
        )
        ser.write(payload)
except KeyboardInterrupt:
    reader.stop()
    ser.close()
```

#### ボタン状態をビットフィールドで送る

```python
import struct

import serial

from core_dual_shock.main import DualShockReader

BUTTON_ORDER = [
    "cross", "circle", "triangle", "square",
    "L1", "R1", "L3", "R3",
    "dpad_up", "dpad_down", "dpad_left", "dpad_right",
    "select", "start", "ps", "touchpad",
]

ser = serial.Serial("/dev/ttyUSB0", 115200)
reader = DualShockReader(deadzone=15)
it = iter(reader)

try:
    while True:
        snapshot = next(it)

        # 16ボタンを 2 バイトのビットフィールドに変換
        bits = 0
        for i, name in enumerate(BUTTON_ORDER):
            if snapshot.buttons[name]:
                bits |= 1 << i

        # ボタン(2B) + スティック(4B) + トリガー(2B) = 8 バイト
        payload = struct.pack(
            "<H6B",
            bits,
            snapshot.analog["left_x"],
            snapshot.analog["left_y"],
            snapshot.analog["right_x"],
            snapshot.analog["right_y"],
            snapshot.analog["L2"],
            snapshot.analog["R2"],
        )
        ser.write(payload)
except KeyboardInterrupt:
    reader.stop()
    ser.close()
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

## TKG Transmitter（TKG通信プロトコル送信）

コントローラーの入力をTKG通信プロトコル（7バイトフレーム）に変換し、シリアルポート経由で送信する機能です。

### TKG送信モード

```bash
uv run python -m core_dual_shock --port /dev/ttyUSB0
```

起動すると `TKG mode: /dev/ttyUSB0 @ 115200bps` と表示され、50Hzでコントローラー入力をTKGプロトコルに変換して送信します。

### ドライランモード（シリアル接続なしで動作確認）

```bash
uv run python -m core_dual_shock --dry-run
```

シリアルデバイスなしでフレーム変換を検証できます。パック済みバイト列を逆符号化して全フィールド・CRC8検算・実測送信Hz・フレーム通番を表示します。

```
#12      2.2s   5.0Hz [  OK ] ts=3 vel=(  +0, +63,  +0) whl=1 fire=0 tai=0 hand=0 ang=0 spd=1 mg=0 crc=OK [A4 00 3F 00 40 80 xx]
```

Ctrl+C で停止すると送信統計サマリを表示します。

```
--- 50 frames / 10.0s (avg 5.00 Hz) ---
```

### オプション

| 引数 | 説明 | デフォルト |
|---|---|---|
| `--port` | シリアルポート（指定しなければ従来のJSON出力モード） | なし |
| `--baudrate` | ボーレート | 115200 |
| `--hz` | マイコンへの送信レート [Hz] | 5 |
| `--dry-run` | シリアル接続なしでフレームを画面表示 | - |

詳細なプロトコル仕様・ボタン割り当て・トラブルシューティングは [README_transmitter.md](README_transmitter.md) を参照してください。

## コントローラープロファイル

コントローラーの定義（ベンダー/プロダクトID、ボタンマッピング、軸設定）は YAML ファイルで管理されています。

```
src/core_dual_shock/profiles/
├── dualshock4.yaml
└── dualsense.yaml
```

### 新しいコントローラーを追加する

Python コードを編集する必要はありません。`profiles/` に YAML ファイルを追加するだけで対応できます。

```yaml
profile_name: "MyController"

devices:
  - vendor_id: 0x1234
    product_id: 0x5678
    description: "My Controller USB"

sticks:
  left_x:  { code: "ABS_X",  min: 0, max: 255 }
  left_y:  { code: "ABS_Y",  min: 0, max: 255 }
  right_x: { code: "ABS_RX", min: 0, max: 255 }
  right_y: { code: "ABS_RY", min: 0, max: 255 }

triggers:
  L2: { code: "ABS_Z",  min: 0, max: 255 }
  R2: { code: "ABS_RZ", min: 0, max: 255 }

buttons:
  triangle: "BTN_NORTH"
  circle:   "BTN_EAST"
  cross:    "BTN_SOUTH"
  square:   "BTN_WEST"
  L1:       "BTN_TL"
  R1:       "BTN_TR"
  L3:       "BTN_THUMBL"
  R3:       "BTN_THUMBR"
  select:   "BTN_SELECT"
  start:    "BTN_START"
  ps:       "BTN_MODE"
  touchpad: 547           # 整数値も指定可能

dpad:
  type: "hat"
  hat_x: "ABS_HAT0X"
  hat_y: "ABS_HAT0Y"
```

- `code` には evdev コード名（`"ABS_X"`, `"BTN_SOUTH"` 等）を文字列で記述します
- 標準名がないコードは整数値で直接指定できます
- コントローラーの Vendor/Product ID は `evtest` コマンドや `cat /proc/bus/input/devices` で確認できます

## テスト

```bash
# 全テスト
uv run python -m pytest tests/ -v

# TKG Transmitter のテストのみ（47件）
uv run python -m pytest tests/test_tkg_transmitter.py -v
```

TKG Transmitter のテストはモックを使用するため、コントローラーやシリアルデバイスがなくても実行できます。

| テストカテゴリ | 件数 | 検証内容 |
|---|---|---|
| CRC8計算 | 5 | 全ゼロ入力、既知パターン、データ変更時の変化 |
| Header組み立て | 8 | ESTOP/DATATYPE/TIMESTAMPの各ビット配置 |
| FIRING組み立て | 7 | 各フィールドのビット位置 |
| OPT2組み立て | 6 | BODY_SPEED_MODE/MG_ACTIONのビット位置 |
| duty変換 | 7 | 境界値・クランプ処理 |
| ワイヤーフォーマット | 6 | ASCII hex表現、カンマ区切り、CRLF終端 |
| build_frame統合 | 8 | フレーム長、CRC整合性、ESTOP制御 |
