from __future__ import annotations
from dataclasses import dataclass
from axelo.models.analysis import StaticAnalysis
from axelo.models.target import TargetSite
from axelo.memory.schema import SitePattern


@dataclass
class DifficultyScore:
    level: str              # easy / medium / hard / extreme
    score: int              # 0-100，越高越难
    reasons: list[str]
    recommended_path: str   # "rules_only" / "static_only" / "static+dynamic" / "full+human"


# 极端难度特征（需要多轮人工介入）
EXTREME_SIGNALS = [
    "wasm",                  # WebAssembly 加密
    "obfuscator",            # 强混淆
    "anti_debug",            # 反调试
    "vm_protect",            # 虚拟机保护
    "custom_vm",
]

# 高难度特征（需要动态 Hook）
HARD_SIGNALS = [
    "canvas",
    "webgl",
    "fingerprint",
    "subtle",               # WebCrypto
    "rsa",
    "device_id",
]

# 中等难度（静态分析可处理）
MEDIUM_SIGNALS = [
    "hmac",
    "sha256",
    "md5",
    "base64",
    "timestamp",
    "nonce",
    "sign",
]


def classify(
    target: TargetSite,
    static_results: dict[str, StaticAnalysis],
    known_pattern: SitePattern | None = None,
) -> DifficultyScore:
    """
    规则优先分类器。
    分层决策：先检查记忆库已知模式，再看静态特征，最后看 bundle 复杂度。
    """
    # 如果记忆库有已知模式，直接使用
    if known_pattern and known_pattern.verified:
        return DifficultyScore(
            level=known_pattern.difficulty,
            score=_level_to_score(known_pattern.difficulty),
            reasons=[f"记忆库已知站点（{known_pattern.success_count}次成功）"],
            recommended_path=_level_to_path(known_pattern.difficulty),
        )

    score = 0
    reasons: list[str] = []

    # 汇总所有 bundle 的特征
    all_crypto: list[str] = []
    all_env: list[str] = []
    total_candidates = 0
    total_funcs = 0

    for sa in static_results.values():
        all_crypto.extend([c.lower() for c in sa.crypto_imports])
        all_env.extend([e.lower() for e in sa.env_access])
        total_candidates += len(sa.token_candidates)
        total_funcs += len(sa.function_map)

    combined = " ".join(all_crypto + all_env)

    # 极端信号（单个即可触发 extreme）
    for sig in EXTREME_SIGNALS:
        if sig in combined:
            score += 80
            reasons.append(f"发现极端特征: {sig}")

    # 高难度信号
    for sig in HARD_SIGNALS:
        if sig in combined:
            score += 15
            reasons.append(f"发现高难特征: {sig}")

    # 中等信号（存在但不加分）
    medium_count = sum(1 for sig in MEDIUM_SIGNALS if sig in combined)
    if medium_count > 0 and score == 0:
        score = 20 + medium_count * 5
        reasons.append(f"标准加密模式 ({medium_count}种)")

    # bundle 复杂度
    if total_funcs > 5000:
        score += 10
        reasons.append(f"Bundle 函数量大({total_funcs})")
    if total_candidates == 0:
        score += 15
        reasons.append("无明显候选函数（混淆严重）")

    # 映射到难度等级
    if score >= 80:
        level = "extreme"
    elif score >= 30:
        level = "hard"
    elif score >= 10:
        level = "medium"
    else:
        level = "easy"

    return DifficultyScore(
        level=level,
        score=score,
        reasons=reasons or ["无特殊特征"],
        recommended_path=_level_to_path(level),
    )


def _level_to_score(level: str) -> int:
    return {"easy": 10, "medium": 30, "hard": 60, "extreme": 90}.get(level, 30)


def _level_to_path(level: str) -> str:
    return {
        "easy":    "rules_only",
        "medium":  "static_only",
        "hard":    "static+dynamic",
        "extreme": "full+human",
    }.get(level, "static_only")
