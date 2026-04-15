from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine, select
from axelo.memory.schema import SitePattern, JSBundleCache, SolutionTemplate, ReverseSession
import structlog

log = structlog.get_logger()


class MemoryDB:
    """
    SQLite 结构化记忆库。
    所有操作同步执行（SQLite 不需要 async 驱动）。
    """

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{db_path}", echo=False)
        SQLModel.metadata.create_all(self._engine)
        self._seed_templates()

    # ── Bundle 缓存 ──────────────────────────────────────────────

    def get_bundle_cache(self, content_hash: str) -> JSBundleCache | None:
        with Session(self._engine) as s:
            return s.exec(select(JSBundleCache).where(JSBundleCache.content_hash == content_hash)).first()

    def save_bundle_cache(self, cache: JSBundleCache) -> JSBundleCache:
        with Session(self._engine) as s:
            existing = s.exec(select(JSBundleCache).where(JSBundleCache.content_hash == cache.content_hash)).first()
            if existing:
                existing.analysis_json = cache.analysis_json
                existing.algorithm_type = cache.algorithm_type
                existing.token_candidate_count = cache.token_candidate_count
                s.add(existing)
                s.commit()
                return existing
            s.add(cache)
            s.commit()
            s.refresh(cache)
            return cache

    # ── 站点模式 ─────────────────────────────────────────────────

    def get_site_pattern(self, domain: str) -> SitePattern | None:
        with Session(self._engine) as s:
            return s.exec(
                select(SitePattern)
                .where(
                    SitePattern.domain == domain,
                    (SitePattern.verified == True) | (SitePattern.success_count > 0),
                )
                .order_by(SitePattern.success_count.desc())
            ).first()

    def save_site_pattern(self, pattern: SitePattern) -> SitePattern:
        with Session(self._engine) as s:
            s.add(pattern)
            s.commit()
            s.refresh(pattern)
        return pattern

    def update_pattern_stats(self, domain: str, success: bool) -> None:
        with Session(self._engine) as s:
            pattern = s.exec(select(SitePattern).where(SitePattern.domain == domain)).first()
            if pattern:
                if success:
                    pattern.success_count += 1
                else:
                    pattern.fail_count += 1
                pattern.last_seen = datetime.now()
                s.add(pattern)
                s.commit()

    # ── 解法模板 ─────────────────────────────────────────────────

    def get_template(self, template_id: int) -> SolutionTemplate | None:
        with Session(self._engine) as s:
            return s.get(SolutionTemplate, template_id)

    def get_template_by_name(self, name: str) -> SolutionTemplate | None:
        with Session(self._engine) as s:
            return s.exec(select(SolutionTemplate).where(SolutionTemplate.name == name)).first()

    def list_templates(self, algorithm_type: str | None = None) -> list[SolutionTemplate]:
        with Session(self._engine) as s:
            q = select(SolutionTemplate)
            if algorithm_type:
                q = q.where(SolutionTemplate.algorithm_type == algorithm_type)
            return list(s.exec(q).all())

    # ── 会话记录 ─────────────────────────────────────────────────

    def save_session(self, record: ReverseSession) -> ReverseSession:
        with Session(self._engine) as s:
            existing = s.exec(select(ReverseSession).where(ReverseSession.session_id == record.session_id)).first()
            if existing:
                for field in record.model_fields:
                    if field != "id":
                        setattr(existing, field, getattr(record, field))
                s.add(existing)
                s.commit()
                return existing
            s.add(record)
            s.commit()
            s.refresh(record)
        return record

    def get_similar_sessions(self, domain: str, algorithm_type: str = "") -> list[ReverseSession]:
        with Session(self._engine) as s:
            q = select(ReverseSession).where(ReverseSession.domain == domain, ReverseSession.verified == True)
            if algorithm_type:
                q = q.where(ReverseSession.algorithm_type == algorithm_type)
            return list(s.exec(q.limit(5)).all())

    def get_recent_sessions(self, domain: str, limit: int = 10) -> list[ReverseSession]:
        with Session(self._engine) as s:
            q = (
                select(ReverseSession)
                .where(ReverseSession.domain == domain)
                .order_by(ReverseSession.created_at.desc())
                .limit(limit)
            )
            return list(s.exec(q).all())

    def list_verified_sessions(
        self,
        domain: str | None = None,
        limit: int | None = None,
    ) -> list[ReverseSession]:
        with Session(self._engine) as s:
            q = select(ReverseSession).where(ReverseSession.verified == True)
            if domain:
                q = q.where(ReverseSession.domain == domain)
            q = q.order_by(ReverseSession.created_at.desc())
            if limit is not None:
                q = q.limit(limit)
            return list(s.exec(q).all())

    def get_sessions_by_ids(self, session_ids: list[str]) -> list[ReverseSession]:
        if not session_ids:
            return []
        with Session(self._engine) as s:
            rows = list(
                s.exec(select(ReverseSession).where(ReverseSession.session_id.in_(session_ids))).all()
            )
        rank = {session_id: index for index, session_id in enumerate(session_ids)}
        rows.sort(key=lambda row: rank.get(row.session_id, len(rank)))
        return rows

    # ── 种子数据 ─────────────────────────────────────────────────

    def _seed_templates(self) -> None:
        """预置常见算法模板"""
        templates = [
            SolutionTemplate(
                name="hmac-sha256-timestamp",
                algorithm_type="hmac",
                description="HMAC-SHA256 签名，输入包含时间戳和 nonce",
                input_fields=json.dumps(["url", "method", "timestamp", "nonce", "secret_key"]),
                output_fields=json.dumps(["X-Sign", "X-Timestamp", "X-Nonce"]),
                python_code='''import hmac, hashlib, time, secrets, base64

class TokenGenerator:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode()

    def generate(self, url: str, method: str = "GET", body: str = "", **kwargs) -> dict[str, str]:
        ts = str(int(time.time() * 1000))
        nonce = secrets.token_hex(8)
        sign_str = f"{method.upper()}\\n{url}\\n{ts}\\n{nonce}\\n{body}"
        sign = hmac.new(self.secret_key, sign_str.encode(), hashlib.sha256).hexdigest()
        return {"X-Sign": sign, "X-Timestamp": ts, "X-Nonce": nonce}
''',
            ),
            SolutionTemplate(
                name="md5-params-salt",
                algorithm_type="md5",
                description="MD5 参数签名，params 排序后拼接 salt",
                input_fields=json.dumps(["params", "salt"]),
                output_fields=json.dumps(["sign"]),
                python_code='''import hashlib, urllib.parse

class TokenGenerator:
    def __init__(self, salt: str):
        self.salt = salt

    def generate(self, params: dict, **kwargs) -> dict[str, str]:
        sorted_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        sign_str = sorted_str + self.salt
        sign = hashlib.md5(sign_str.encode()).hexdigest()
        return {"sign": sign}
''',
            ),
            SolutionTemplate(
                name="canvas-fingerprint-bridge",
                algorithm_type="fingerprint",
                description="Canvas/WebGL 浏览器指纹，需要 JS 桥接",
                input_fields=json.dumps([]),
                output_fields=json.dumps(["X-Device-ID", "X-Fp"]),
                bridge_code='''// bridge_server.js snippet
const canvas = new OffscreenCanvas(200, 50);
const ctx = canvas.getContext("2d");
ctx.fillText("axelo", 10, 10);
const fp = canvas.toDataURL().slice(-32);
''',
            ),
        ]
        with Session(self._engine) as s:
            for t in templates:
                existing = s.exec(select(SolutionTemplate).where(SolutionTemplate.name == t.name)).first()
                if not existing:
                    s.add(t)
            s.commit()
        log.debug("memory_db_ready")
