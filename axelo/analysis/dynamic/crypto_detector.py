from __future__ import annotations
import json
import re
from axelo.models.analysis import HookIntercept


def detect_algorithm(intercepts: list[HookIntercept]) -> list[dict]:
    """
    从 Hook 拦截的参数/返回值推断使用的加密算法。
    返回推断结果列表，每项包含 {api, algorithm, key_len, evidence}。
    """
    results = []
    for ic in intercepts:
        if "subtle" not in ic.api_name:
            continue
        try:
            args = json.loads(ic.args_repr)
        except Exception:
            continue

        # subtle.sign / subtle.digest 的第一个参数是算法描述符
        algo_arg = args[0] if args else None
        if not algo_arg:
            continue

        algo_name = None
        key_len = None

        if isinstance(algo_arg, dict):
            algo_name = algo_arg.get("name", "")
            key_len = algo_arg.get("hash", {}).get("name") if isinstance(algo_arg.get("hash"), dict) else None
        elif isinstance(algo_arg, str):
            algo_name = algo_arg

        if algo_name:
            results.append({
                "api": ic.api_name,
                "algorithm": algo_name,
                "key_len": key_len,
                "evidence": f"参数: {str(algo_arg)[:100]}",
            })

    return results


def extract_key_material(intercepts: list[HookIntercept]) -> list[str]:
    """
    尝试从 subtle.importKey / subtle.sign 的参数中提取密钥材料（hex 表示）。
    """
    keys = []
    for ic in intercepts:
        if "importKey" not in ic.api_name and "sign" not in ic.api_name:
            continue
        try:
            args = json.loads(ic.args_repr)
        except Exception:
            continue
        for arg in args:
            if isinstance(arg, dict) and arg.get("__type") in ("ArrayBuffer", "Uint8Array"):
                hex_val = arg.get("hex", "")
                if len(hex_val) >= 16:
                    keys.append(hex_val)
    return list(dict.fromkeys(keys))
