#!/usr/bin/env python3
"""接続中のコントローラからYAMLプロファイルを対話的に生成するツール.

使い方:
    uv run python tools/generate_profile.py
"""

from __future__ import annotations

import sys
import time

import evdev
from evdev import ecodes


def select_device() -> evdev.InputDevice:
    """接続中のデバイス一覧を表示し、ユーザーに選択させる."""
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    if not devices:
        print("デバイスが見つかりません", file=sys.stderr)
        sys.exit(1)

    print("=== 接続中のデバイス ===")
    for i, dev in enumerate(devices):
        print(
            f"  [{i}] {dev.name}  "
            f"(vendor={hex(dev.info.vendor)}, product={hex(dev.info.product)}, "
            f"path={dev.path})"
        )
    print()

    while True:
        try:
            idx = int(input("デバイス番号を選択してください: "))
            if 0 <= idx < len(devices):
                selected = devices[idx]
                print(f"  → {selected.name} を選択しました\n")
                return selected
        except (ValueError, EOFError):
            pass
        print("無効な番号です。もう一度入力してください。")


def detect_axis(dev: evdev.InputDevice, prompt: str) -> int | None:
    """指定された軸を操作させて、変化したABSコードを検出する.

    Returns:
        検出されたABSコード。スキップされた場合はNone
    """
    # 現在値を記録
    caps = dev.capabilities(verbose=False)
    abs_codes = {}
    if 3 in caps:
        for code, absinfo in caps[3]:
            abs_codes[code] = absinfo.value

    print(f"  {prompt}")
    print("  （操作してください。スキップする場合は Enter を押す）")

    # ノンブロッキングで読み取り
    import select

    detected = {}
    start = time.monotonic()
    timeout = 5.0

    while time.monotonic() - start < timeout:
        r, _, _ = select.select([dev.fd], [], [], 0.1)
        if not r:
            # stdinもチェック（Enterでスキップ）
            sr, _, _ = select.select([sys.stdin], [], [], 0)
            if sr:
                sys.stdin.readline()
                print("  → スキップ\n")
                return None
            continue

        for event in dev.read():
            if event.type != ecodes.EV_ABS:
                continue
            code = event.code
            if code not in abs_codes:
                continue
            diff = abs(event.value - abs_codes[code])
            if diff > 30:
                detected[code] = detected.get(code, 0) + diff

    if not detected:
        print("  → 変化が検出されませんでした\n")
        return None

    best = max(detected, key=detected.get)
    name = ecodes.ABS.get(best, f"unknown({best})")
    print(f"  → 検出: code={best} ({name})\n")
    return best


def detect_button(dev: evdev.InputDevice, prompt: str) -> int | None:
    """指定されたボタンを押させて、EVENTコードを検出する.

    Returns:
        検出されたKEYコード。スキップされた場合はNone
    """
    print(f"  {prompt}")
    print("  （ボタンを押してください。スキップする場合は Enter を押す）")

    import select

    start = time.monotonic()
    timeout = 5.0

    while time.monotonic() - start < timeout:
        r, _, _ = select.select([dev.fd], [], [], 0.1)
        if not r:
            sr, _, _ = select.select([sys.stdin], [], [], 0)
            if sr:
                sys.stdin.readline()
                print("  → スキップ\n")
                return None
            continue

        for event in dev.read():
            if event.type != ecodes.EV_KEY:
                continue
            if event.value == 1:  # 押下のみ
                code = event.code
                name = ecodes.keys.get(code, f"unknown({code})")
                print(f"  → 検出: code={code} ({name})\n")
                return code

    print("  → 検出されませんでした\n")
    return None


def _detect_hat_axis(
    dev: evdev.InputDevice, prompt: str,
) -> int | None:
    """十字キーのHAT軸を1方向検出する.

    ABS_HAT系コード（code >= 16）のみを対象とし、スティックのドリフトを無視する。
    """
    print(f"  {prompt}")
    print("  （操作してください。スキップする場合は Enter を押す）")

    import select

    start = time.monotonic()
    timeout = 5.0

    while time.monotonic() - start < timeout:
        r, _, _ = select.select([dev.fd], [], [], 0.1)
        if not r:
            sr, _, _ = select.select([sys.stdin], [], [], 0)
            if sr:
                sys.stdin.readline()
                print("  → スキップ\n")
                return None
            continue

        for event in dev.read():
            if event.type != ecodes.EV_ABS:
                continue
            # HAT軸のみ対象（ABS_HAT0X=16以降）。スティック軸を除外
            if event.code < 16:
                continue
            if event.value != 0:
                name = ecodes.ABS.get(event.code, f"unknown({event.code})")
                print(f"  → 検出: code={event.code} ({name})\n")
                return event.code

    print("  → 検出されませんでした\n")
    return None


def detect_dpad(
    dev: evdev.InputDevice,
) -> tuple[str, dict[str, int | None]]:
    """十字キーの方式を検出する.

    Returns:
        (dpad_type, dpad_mapping)
        dpad_type: "hat" or "button"
    """
    print("--- 十字キー検出 ---")
    print("  十字キーの「上」を押してください")
    print("  （操作してください。5秒以内に検出します）")

    import select

    start = time.monotonic()
    timeout = 5.0
    hat_codes: dict[str, int] = {}
    button_codes: dict[str, int] = {}

    while time.monotonic() - start < timeout:
        r, _, _ = select.select([dev.fd], [], [], 0.1)
        if not r:
            continue

        for event in dev.read():
            if event.type == ecodes.EV_ABS and event.code >= 16:
                # HAT方式（ABS_HAT系のみ）
                name = ecodes.ABS.get(event.code, f"unknown({event.code})")
                print(f"  → HAT方式を検出: code={event.code} ({name})\n")
                if event.value != 0:
                    hat_codes["hat_y"] = event.code
                    break
            elif event.type == ecodes.EV_KEY and event.value == 1:
                # ボタン方式
                name = ecodes.keys.get(event.code, f"unknown({event.code})")
                print(f"  → ボタン方式を検出: code={event.code} ({name})\n")
                button_codes["dpad_up"] = event.code
                break

        if hat_codes or button_codes:
            break

    if hat_codes:
        # hat_x も個別に検出
        while dev.read_one():
            pass
        hat_x = _detect_hat_axis(dev, "十字キーの「右」を押してください")
        if hat_x is not None:
            hat_codes["hat_x"] = hat_x
        return "hat", hat_codes

    # ボタン方式の場合、残りの方向も検出
    if button_codes:
        for direction, prompt in [
            ("dpad_down", "十字キーの「下」を押してください"),
            ("dpad_left", "十字キーの「左」を押してください"),
            ("dpad_right", "十字キーの「右」を押してください"),
        ]:
            code = detect_button(dev, prompt)
            if code is not None:
                button_codes[direction] = code
        return "button", button_codes

    print("  → 検出されませんでした\n")
    return "hat", {}


def code_to_ecode_name(code: int, code_type: str) -> str:
    """evdevコードをecodes定数名に逆引きする."""
    if code_type == "abs":
        name = ecodes.ABS.get(code)
        if isinstance(name, list):
            return name[0]
        return name or str(code)
    elif code_type == "key":
        name = ecodes.keys.get(code)
        if isinstance(name, tuple):
            # BTN_NORTH/BTN_X のような複数名 → 最初のものを使う
            return name[0]
        elif isinstance(name, list):
            return name[0]
        return name or str(code)
    return str(code)


def get_abs_range(dev: evdev.InputDevice, code: int) -> tuple[int, int]:
    """指定されたABSコードのmin/maxを取得."""
    caps = dev.capabilities(verbose=False)
    if 3 in caps:
        for c, absinfo in caps[3]:
            if c == code:
                return absinfo.min, absinfo.max
    return 0, 255


def generate_yaml(
    profile_name: str,
    vendor_id: int,
    product_id: int,
    description: str,
    sticks: dict[str, int],
    triggers: dict[str, int],
    buttons: dict[str, int],
    dpad_type: str,
    dpad: dict[str, int],
    abs_ranges: dict[int, tuple[int, int]],
) -> str:
    """YAMLプロファイル文字列を生成."""
    lines = []
    lines.append(f'# {description} コントローラープロファイル')
    lines.append(f'profile_name: "{profile_name}"')
    lines.append("")
    lines.append("devices:")
    lines.append(f"  - vendor_id: {hex(vendor_id)}")
    lines.append(f"    product_id: {hex(product_id)}")
    lines.append(f'    description: "{description}"')

    # sticks
    lines.append("")
    lines.append("sticks:")
    for name in ["left_x", "left_y", "right_x", "right_y"]:
        if name in sticks:
            code = sticks[name]
            ecode_name = code_to_ecode_name(code, "abs")
            mn, mx = abs_ranges.get(code, (0, 255))
            lines.append(
                f'  {name}: {{ code: "{ecode_name}", min: {mn}, max: {mx} }}'
            )

    # triggers
    lines.append("")
    lines.append("triggers:")
    for name in ["L2", "R2"]:
        if name in triggers:
            code = triggers[name]
            ecode_name = code_to_ecode_name(code, "abs")
            mn, mx = abs_ranges.get(code, (0, 255))
            lines.append(
                f'  {name}: {{ code: "{ecode_name}", min: {mn}, max: {mx} }}'
            )

    # buttons
    lines.append("")
    lines.append("buttons:")
    button_order = [
        "triangle", "circle", "cross", "square",
        "L1", "R1", "L3", "R3",
        "select", "start", "ps", "touchpad",
    ]
    for name in button_order:
        if name in buttons:
            code = buttons[name]
            ecode_name = code_to_ecode_name(code, "key")
            # ecodes定数名に解決できた場合は文字列、できなければ数値
            if ecode_name.startswith("BTN_") or ecode_name.startswith("KEY_"):
                lines.append(f'  {name}: "{ecode_name}"')
            else:
                lines.append(f"  {name}: {code}")

    # dpad
    lines.append("")
    lines.append("dpad:")
    lines.append(f'  type: "{dpad_type}"')
    if dpad_type == "hat":
        for key in ["hat_x", "hat_y"]:
            if key in dpad:
                ecode_name = code_to_ecode_name(dpad[key], "abs")
                lines.append(f'  {key}: "{ecode_name}"')

    lines.append("")
    return "\n".join(lines)


def main():
    print("=" * 50)
    print("  コントローラープロファイル生成ツール")
    print("=" * 50)
    print()

    dev = select_device()
    vendor_id = dev.info.vendor
    product_id = dev.info.product

    # ABS範囲を事前に取得
    abs_ranges: dict[int, tuple[int, int]] = {}
    caps = dev.capabilities(verbose=False)
    if 3 in caps:
        for code, absinfo in caps[3]:
            abs_ranges[code] = (absinfo.min, absinfo.max)

    # --- スティック検出 ---
    print("--- スティック検出 ---")
    sticks: dict[str, int] = {}

    stick_prompts = [
        ("left_x", "左スティックを「左右」に大きく倒してください"),
        ("left_y", "左スティックを「上下」に大きく倒してください"),
        ("right_x", "右スティックを「左右」に大きく倒してください"),
        ("right_y", "右スティックを「上下」に大きく倒してください"),
    ]

    for name, prompt in stick_prompts:
        # 前のイベントを消費
        while dev.read_one():
            pass
        code = detect_axis(dev, prompt)
        if code is not None:
            sticks[name] = code

    # --- トリガー検出 ---
    print("--- トリガー検出 ---")
    triggers: dict[str, int] = {}

    trigger_prompts = [
        ("L2", "L2トリガーを深く押してください"),
        ("R2", "R2トリガーを深く押してください"),
    ]

    for name, prompt in trigger_prompts:
        while dev.read_one():
            pass
        code = detect_axis(dev, prompt)
        if code is not None:
            triggers[name] = code

    # --- ボタン検出 ---
    print("--- ボタン検出 ---")
    buttons: dict[str, int] = {}

    button_prompts = [
        ("triangle", "△ボタンを押してください"),
        ("circle", "○ボタンを押してください"),
        ("cross", "×ボタンを押してください"),
        ("square", "□ボタンを押してください"),
        ("L1", "L1ボタンを押してください"),
        ("R1", "R1ボタンを押してください"),
        ("L3", "L3（左スティック押し込み）を押してください"),
        ("R3", "R3（右スティック押し込み）を押してください"),
        ("select", "SHARE / Createボタンを押してください"),
        ("start", "OPTIONS / Menuボタンを押してください"),
        ("ps", "PSボタンを押してください"),
        ("touchpad", "タッチパッドボタンを押してください"),
    ]

    for name, prompt in button_prompts:
        while dev.read_one():
            pass
        code = detect_button(dev, prompt)
        if code is not None:
            buttons[name] = code

    # --- 十字キー検出 ---
    while dev.read_one():
        pass
    dpad_type, dpad = detect_dpad(dev)

    # --- プロファイル名入力 ---
    print("--- プロファイル情報 ---")
    default_name = dev.name.replace(" ", "_")
    profile_name = input(f"プロファイル名 [{default_name}]: ").strip()
    if not profile_name:
        profile_name = default_name
    description = input(f"説明 [{dev.name}]: ").strip()
    if not description:
        description = dev.name

    # --- YAML生成 ---
    yaml_str = generate_yaml(
        profile_name=profile_name,
        vendor_id=vendor_id,
        product_id=product_id,
        description=description,
        sticks=sticks,
        triggers=triggers,
        buttons=buttons,
        dpad_type=dpad_type,
        dpad=dpad,
        abs_ranges=abs_ranges,
    )

    print()
    print("=" * 50)
    print("  生成されたプロファイル")
    print("=" * 50)
    print(yaml_str)

    # ファイル保存
    save = input("profiles/ に保存しますか？ [y/N]: ").strip().lower()
    if save == "y":
        from pathlib import Path

        profiles_dir = Path(__file__).parent.parent / "src" / "core_dual_shock" / "profiles"
        filename = profile_name.lower().replace(" ", "_") + ".yaml"
        filepath = profiles_dir / filename
        filepath.write_text(yaml_str)
        print(f"保存しました: {filepath}")
    else:
        print("保存をスキップしました。上記のYAMLをコピーして使ってください。")


if __name__ == "__main__":
    main()
