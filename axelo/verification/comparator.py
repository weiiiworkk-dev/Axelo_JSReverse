from __future__ import annotations
import re
import hmac
import base64
from axelo.models.target import RequestCapture


class TokenComparator:
    """
    比对生成的 token/签名字段与捕获的 ground truth。
    支持精确匹配、格式匹配（长度/前缀/编码格式）、时效性字段豁免。
    """

    # 时效性字段（每次必然不同，只检查格式不检查值）
    TEMPORAL_FIELDS = {
        "x-timestamp", "x-ts", "x-nonce", "x-request-id",
        "x-trace-id", "timestamp", "nonce",
    }
    IGNORED_GENERATED_FIELDS = {
        "cookie",
        "content-length",
        "host",
        "connection",
        "accept-encoding",
        "transfer-encoding",
    }

    # Base64 格式检测
    B64_PATTERN = re.compile(r'^[A-Za-z0-9+/]{16,}={0,2}$')
    # Hex 格式检测
    HEX_PATTERN = re.compile(r'^[0-9a-fA-F]{16,}$')

    def compare(
        self,
        generated: dict[str, str],
        ground_truth: RequestCapture,
    ) -> "CompareResult":
        gt_headers = {k.lower(): v for k, v in ground_truth.request_headers.items()}
        results: list[FieldResult] = []
        missing_fields: list[str] = []
        matched_fields: list[str] = []
        compared_fields = 0

        for field, gen_value in generated.items():
            field_lower = field.lower()
            if field_lower in self.IGNORED_GENERATED_FIELDS:
                continue
            compared_fields += 1
            gt_value = gt_headers.get(field_lower)

            if gt_value is None:
                missing_fields.append(field)
                results.append(FieldResult(field=field, status="missing", message="目标请求中未找到此字段"))
                continue

            if field_lower in self.TEMPORAL_FIELDS:
                # 时效性字段：只检查格式
                ok, msg = self._check_format(gen_value, gt_value)
                status = "format_ok" if ok else "format_mismatch"
                results.append(FieldResult(field=field, status=status, message=msg, gen=gen_value, gt=gt_value))
                if ok:
                    matched_fields.append(field)
            else:
                # 签名字段：检查格式（值每次不同，无法精确比对）
                ok, msg = self._check_format(gen_value, gt_value)
                status = "format_ok" if ok else "format_mismatch"
                results.append(FieldResult(field=field, status=status, message=msg, gen=gen_value, gt=gt_value))
                if ok:
                    matched_fields.append(field)

        overall_ok = len(missing_fields) == 0 and len(matched_fields) == compared_fields
        return CompareResult(
            ok=overall_ok,
            field_results=results,
            matched=matched_fields,
            missing=missing_fields,
            score=len(matched_fields) / max(compared_fields, 1),
        )

    def _check_format(self, gen: str, gt: str) -> tuple[bool, str]:
        # 相同格式检测
        gen_is_b64 = bool(self.B64_PATTERN.match(gen))
        gt_is_b64 = bool(self.B64_PATTERN.match(gt))
        gen_is_hex = bool(self.HEX_PATTERN.match(gen))
        gt_is_hex = bool(self.HEX_PATTERN.match(gt))

        if gen_is_b64 and gt_is_b64:
            if abs(len(gen) - len(gt)) <= 4:
                return True, f"Base64格式匹配，长度近似({len(gen)} vs {len(gt)})"
            return False, f"Base64长度差异过大({len(gen)} vs {len(gt)})"

        if gen_is_hex and gt_is_hex:
            if len(gen) == len(gt):
                return True, f"Hex格式匹配，长度相同({len(gen)})"
            return False, f"Hex长度不同({len(gen)} vs {len(gt)})"

        # 通用长度匹配
        if abs(len(gen) - len(gt)) <= max(len(gt) * 0.2, 4):
            return True, f"长度近似({len(gen)} vs {len(gt)})"

        return False, f"格式/长度不匹配: gen={gen[:30]!r} gt={gt[:30]!r}"


class FieldResult:
    def __init__(self, field: str, status: str, message: str, gen: str = "", gt: str = ""):
        self.field = field
        self.status = status
        self.message = message
        self.gen = gen
        self.gt = gt

    def __repr__(self):
        return f"[{self.status}] {self.field}: {self.message}"


class CompareResult:
    def __init__(self, ok: bool, field_results: list[FieldResult],
                 matched: list[str], missing: list[str], score: float):
        self.ok = ok
        self.field_results = field_results
        self.matched = matched
        self.missing = missing
        self.score = score

    def summary(self) -> str:
        lines = [f"得分: {self.score:.0%} | {'✓ 通过' if self.ok else '✗ 未通过'}"]
        for r in self.field_results:
            icon = "✓" if r.status.endswith("ok") else "✗"
            lines.append(f"  {icon} {r.field}: {r.message}")
        return "\n".join(lines)
