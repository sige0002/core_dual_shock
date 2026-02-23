# TKG Transmitter

DualShockコントローラーの入力をTKG通信プロトコルに変換し、シリアルポート経由で送信する機能。

## 前提条件

- Linux
- Python 3.12 以上
- uv
- DualShock 4 または DualSense がUSBまたはBluetoothで接続済み
- TKG受信機がシリアルポート（例: `/dev/ttyUSB0`）に接続済み

## セットアップ

```bash
cd core_dual_shock
uv sync
```

## テストの実行

コントローラーやシリアルデバイスがなくても実行できます。

```bash
# TKG Transmitter のテストのみ
uv run python -m pytest tests/test_tkg_transmitter.py -v

# 全テスト
uv run python -m pytest tests/ -v
```

### テスト内容（47件）

| カテゴリ | 件数 | 検証内容 |
|---|---|---|
| CRC8計算 | 5 | 全ゼロ入力、既知パターン、データ変更時の変化、7バイト目の非影響 |
| Header組み立て | 8 | ESTOP/DATATYPE/TIMESTAMPの各ビット配置、合成値 `0xA4` の一致 |
| FIRING組み立て | 7 | 各フィールド(WHEEL/FIRE/TAIMATU/HAND/ANGLE)のビット位置 |
| OPT2組み立て | 6 | BODY_SPEED_MODE/MG_ACTIONのビット位置、下位5bitが常に0 |
| duty変換 | 7 | 0.0/1.0/-1.0/0.5/-0.5/クランプ処理 |
| ワイヤーフォーマット | 6 | ASCII hex表現、カンマ区切り、CRLF終端 |
| build_frame統合 | 8 | フレーム長、CRC整合性、ESTOP制御、タイムスタンプ、速度ゼロ |

## 実行方法

### TKG送信モード

```bash
uv run python -m core_dual_shock --port /dev/ttyUSB0
```

起動すると `TKG mode: /dev/ttyUSB0 @ 115200bps, 5.0Hz` と表示され、デフォルト5Hzでコントローラー入力をTKGプロトコルに変換して送信します。Ctrl+C で停止。

### ドライランモード（シリアル接続なしで動作確認）

```bash
uv run python -m core_dual_shock --dry-run
```

シリアルデバイスなしでコントローラー入力→TKGフレーム変換を検証できます。
パック済みバイト列を逆符号化して全フィールドを表示し、CRC8の一致も確認します。

表示例:
```
#12      2.2s   5.0Hz [  OK ] ts=3 vel=(  +0, +63,  +0) whl=1 fire=0 tai=0 hand=0 ang=0 spd=1 mg=0 crc=OK [A4 00 3F 00 40 80 xx]
```

Ctrl+C で停止すると送信統計サマリを表示します:
```
--- 50 frames / 10.0s (avg 5.00 Hz) ---
```

| 表示項目 | 意味 |
|---|---|
| `#N` | フレーム通番 |
| `N.Ns` | 開始からの経過時間 |
| `N.NHz` | 直近の実測送信周波数 |
| `ESTOP` / `OK` | Byte0 bit7 から逆符号化した緊急停止状態 |
| `ts` | Byte0 bit4-2 タイムスタンプ (0-7) |
| `vel` | Byte1-3 を signed char として逆符号化 (-127~127) |
| `whl` | Byte4 bit7-6 ホイール速度 (0-3) |
| `fire` | Byte4 bit5-4 発射状態 (0-2) |
| `tai` | Byte4 bit3-2 松明リフト (0-2) |
| `hand` | Byte4 bit1 ハンド前後 (0-1) |
| `ang` | Byte4 bit0 発射角度 (0-1) |
| `spd` | Byte5 bit7 速度モード (0-1) |
| `mg` | Byte5 bit6-5 MG動作 (0-2) |
| `crc` | Byte6 のCRC8検算結果 (OK/NG) |
| `[XX XX ...]` | 7バイトのフレームデータ（16進ダンプ） |

### オプション

| 引数 | 説明 | デフォルト |
|---|---|---|
| `--port` | シリアルポート（指定しなければ従来のJSON出力モード） | なし |
| `--baudrate` | ボーレート | 115200 |
| `--hz` | マイコンへの送信レート [Hz] | 5 |
| `--dry-run` | シリアル接続なしでフレームを画面表示 | - |

### 従来のJSON出力モード（変更なし）

```bash
uv run python -m core_dual_shock
```

## コントローラーのボタン割り当て

### 移動系

| ボタン/スティック | 機能 |
|---|---|
| 左スティック Y軸 | VEL_X（前後移動、符号反転） |
| 左スティック X軸 | VEL_Y（左右移動、符号反転） |
| 右スティック X軸 | VEL_YAW（旋回） |
| L1 | 押している間: 標準速度 / 離すと: 低速モード |

### 射撃系

| ボタン | 機能 |
|---|---|
| dpad 上 | ホイール速度UP（エッジ検出：押した瞬間に1段階UP） |
| dpad 下 | ホイール速度DOWN（エッジ検出：押した瞬間に1段階DOWN） |
| circle | 連射（FIRE_RAPID） |
| cross | 単発（FIRE_SINGLE） |
| triangle | 発射角度 上向き（FIRING_ANGLE_UPPER） |

### 機構系

| ボタン | 機能 |
|---|---|
| dpad 上 | 松明リフト上昇 |
| dpad 下 | 松明リフト下降 |
| square | ハンド前進（状態保持：離しても維持） |
| R1 | ハンド後退（状態保持：離しても維持） |
| dpad 右 | MG前進 |
| dpad 左 | MG後退 |

### 緊急停止

| ボタン | 機能 |
|---|---|
| select (SHARE / Create) | ESTOP有効化 |
| start (OPTIONS) | ESTOP解除 |

ESTOP有効時は以下が強制オーバーライドされます:
- ホイール速度 → 0（停止）
- ハンド → 後退
- 松明リフト → 停止

## 通信プロトコル仕様

### フレーム構造（7バイト）

```
[Header][VEL_X][VEL_Y][VEL_YAW][FIRING][OPT2][CRC8]
 Byte0   Byte1  Byte2   Byte3   Byte4  Byte5  Byte6
```

### ワイヤーフォーマット

バイナリではなく **ASCIIテキスト** で送信します。

```
%02x,%02x,%02x,%02x,%02x,%02x,%02x\r\n
```

例: `86,3f,c1,7f,00,00,a3\r\n`

### シリアル設定

| 項目 | 値 |
|---|---|
| ボーレート | 115200 bps |
| データビット | 8 bit |
| パリティ | なし |
| ストップビット | 1 bit |
| フロー制御 | なし |

### 各バイトの詳細

#### Byte 0: Header

```
Bit:  7       6   5     4   3   2     1   0
    [ESTOP][DATATYPE ][TIMESTAMP   ][NODEF ]
```

| ビット | 名称 | 説明 |
|---|---|---|
| 7 | IS_ESTOP | 0=ESTOP有効, 1=通常動作 |
| 6-5 | DATATYPE | 0x01=CMD1（通常操作） |
| 4-2 | TIMESTAMP | 0-7 送信毎にインクリメント |
| 1-0 | NODEF | 0固定 |

#### Byte 1-3: 速度指令

signed char（-127 ~ 127、2の補数表現）。duty比(-1.0~1.0)を `int(duty * 127)` で変換。

#### Byte 4: FIRING

```
Bit:  7   6   5   4   3   2     1            0
    [WHEEL  ][FIRE  ][TAIMATU ][HAND_FORWARD][FIRE_ANGLE]
```

#### Byte 5: OPT2

```
Bit:  7              6   5   4   3   2   1   0
    [BODY_SPEED_MODE][MG    ][0固定             ]
```

#### Byte 6: CRC8

- ポリノミアル: `0xEB`
- 計算対象: Byte 0-5（6バイト）
- 内部ループ: **7回**（標準CRC-8の8回ではない）

## ファイル構成

```
src/core_dual_shock/
├── tkg_transmitter.py   # TKG通信プロトコル実装（新規追加）
├── main.py              # --port引数とTKGモードを追加
├── device.py            # コントローラー検出（変更なし）
├── input_state.py       # 入力状態管理（変更なし）
├── mapper.py            # 正規化処理（変更なし）
└── ...

tests/
└── test_tkg_transmitter.py  # TKGプロトコルの単体テスト（47件）
```

## トラブルシューティング

### `DualShock controller not found`
- コントローラーがUSBまたはBluetoothで接続されているか確認
- `ls /dev/input/event*` でデバイスが認識されているか確認
- `sudo usermod -aG input $USER` で権限を追加（再ログイン必要）

### シリアルポートが開けない
- `ls /dev/ttyUSB*` でデバイスが存在するか確認
- `sudo usermod -aG dialout $USER` で権限を追加（再ログイン必要）

### テストだけ実行したい（デバイスなし）
テストはモックを使用するため、コントローラーやシリアルデバイスなしで実行できます。
```bash
uv run python -m pytest tests/test_tkg_transmitter.py -v
```
