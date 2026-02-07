"""YAMLプロファイルの読み込み・evdevコード解決モジュール."""

from __future__ import annotations

import functools
from pathlib import Path

import yaml
from evdev import ecodes


_PROFILES_DIR = Path(__file__).parent / "profiles"


def _resolve_ecode(value: str | int) -> int:
    """evdevコード名を整数に解決する.

    Args:
        value: evdevコード名(例: "ABS_X") または整数値

    Returns:
        evdevコードの整数値

    Raises:
        ValueError: 不明なevdevコード名の場合
    """
    if isinstance(value, int):
        return value
    code = getattr(ecodes, value, None)
    if code is None:
        raise ValueError(f"Unknown evdev code: {value}")
    return code


def _load_single(path: Path) -> tuple[str, dict, list[tuple[int, int]]]:
    """YAML 1ファイルを読み込み、PROFILES互換のdictを返す.

    Args:
        path: YAMLファイルのパス

    Returns:
        (profile_name, profile_dict, [(vendor_id, product_id), ...])
    """
    with open(path) as f:
        raw = yaml.safe_load(f)

    profile_name = raw["profile_name"]

    # デバイス一覧
    device_ids = []
    for dev in raw["devices"]:
        device_ids.append((dev["vendor_id"], dev["product_id"]))

    # sticks
    sticks = {}
    for name, cfg in raw["sticks"].items():
        sticks[name] = {
            "code": _resolve_ecode(cfg["code"]),
            "min": cfg["min"],
            "max": cfg["max"],
        }

    # triggers
    triggers = {}
    for name, cfg in raw["triggers"].items():
        triggers[name] = {
            "code": _resolve_ecode(cfg["code"]),
            "min": cfg["min"],
            "max": cfg["max"],
        }

    # buttons
    buttons = {}
    for name, code_val in raw["buttons"].items():
        buttons[name] = _resolve_ecode(code_val)

    # dpad
    dpad_raw = raw["dpad"]
    dpad_type = dpad_raw["type"]
    dpad = {}
    if dpad_type == "hat":
        dpad["hat_x"] = _resolve_ecode(dpad_raw["hat_x"])
        dpad["hat_y"] = _resolve_ecode(dpad_raw["hat_y"])

    profile_dict = {
        "vendor": raw["devices"][0]["vendor_id"],
        "sticks": sticks,
        "triggers": triggers,
        "buttons": buttons,
        "dpad_type": dpad_type,
        "dpad": dpad,
    }

    return profile_name, profile_dict, device_ids


@functools.cache
def load_all_profiles() -> tuple[dict, dict]:
    """profiles/ 内の全YAMLを読み込む.

    Returns:
        (profiles_dict, device_mapping_dict)
        - profiles_dict: {profile_name: profile_dict, ...}
        - device_mapping_dict: {(vendor_id, product_id): profile_name, ...}
    """
    profiles: dict[str, dict] = {}
    device_mapping: dict[tuple[int, int], str] = {}

    for yaml_path in sorted(_PROFILES_DIR.glob("*.yaml")):
        name, profile, device_ids = _load_single(yaml_path)
        profiles[name] = profile
        for vid_pid in device_ids:
            device_mapping[vid_pid] = name

    return profiles, device_mapping
