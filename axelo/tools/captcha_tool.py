"""
CAPTCHA 检测和处理工具

检测页面上的 CAPTCHA 挑战:
- reCAPTCHA
- hCaptcha  
- Cloudflare Turnstile
- 普通图像验证码

提供处理框架和通知机制

用法:
    captcha_tool.run({"page_html": "...", "page_url": "..."})
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from axelo.tools.base import BaseTool, ToolOutput, ToolResult, ToolStatus

log = structlog.get_logger(__name__)


class CaptchaTool(BaseTool):
    """CAPTCHA 检测工具"""

    def __init__(self):
        super().__init__()

    @property
    def name(self) -> str:
        return "captcha"
    
    @property
    def description(self) -> str:
        return "检测页面上的 CAPTCHA 挑战类型"
    
    def _create_schema(self) -> "ToolSchema":
        from axelo.tools.base import ToolSchema, ToolInput, ToolCategory, ToolOutput
        
        output_schema = [
            ToolOutput(name="detected", type="boolean", description="是否检测到 CAPTCHA"),
            ToolOutput(name="captcha_type", type="string", description="CAPTCHA 类型"),
            ToolOutput(name="confidence", type="number", description="检测置信度 0-1"),
            ToolOutput(name="detected_elements", type="array", description="检测到的页面元素"),
            ToolOutput(name="recommended_action", type="string", description="建议的处理方式"),
            ToolOutput(name="can_bypass", type="boolean", description="是否可以绕过"),
        ]
        
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.DETECTION,
            input_schema=[
                ToolInput(name="page_html", type="string", description="页面 HTML"),
                ToolInput(name="page_url", type="string", description="页面 URL"),
                ToolInput(name="page_title", type="string", description="页面标题"),
            ],
            output_schema=output_schema,
            timeout_seconds=10,
            retry_enabled=False,
        )

    async def execute(self, input_data: dict[str, Any], state: Any) -> ToolResult:
        return await self.run(input_data, state)

    async def run(self, input_data: dict, state: Any = None) -> ToolResult:
        page_html = input_data.get("page_html", "")
        page_url = input_data.get("page_url", "")
        page_title = input_data.get("page_title", "")

        if not page_html and not page_url:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: page_html or page_url",
            )

        try:
            log.info("captcha_check_start", url=page_url)

            # 检测 CAPTCHA
            detected, captcha_type, confidence, elements = self._detect_captcha(
                page_html, page_url, page_title
            )

            # 确定建议的操作
            recommended_action, can_bypass = self._get_recommendation(
                captcha_type, confidence
            )

            result = {
                "detected": detected,
                "captcha_type": captcha_type,
                "confidence": confidence,
                "detected_elements": elements,
                "recommended_action": recommended_action,
                "can_bypass": can_bypass,
            }

            log.info("captcha_check_complete",
                detected=detected,
                type=captcha_type,
                confidence=confidence,
            )

            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output=result,
            )

        except Exception as exc:
            log.error("captcha_check_failed", error=str(exc))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=f"CAPTCHA 检测失败: {exc}",
            )

    def _detect_captcha(
        self, html: str, url: str, title: str
    ) -> tuple[bool, str, float, list]:
        """检测 CAPTCHA 类型"""
        elements = []
        
        # 检查 URL 中的 CAPTCHA 指示
        url_lower = url.lower()
        if "captcha" in url_lower or "challenge" in url_lower:
            elements.append({
                "type": "url_indicator",
                "value": "URL contains captcha/challenge",
            })
        
        # 检查标题
        title_lower = title.lower() if title else ""
        if "captcha" in title_lower or "verification" in title_lower:
            elements.append({
                "type": "title_indicator", 
                "value": f"Title: {title}",
            })

        # 1. reCAPTCHA 检测
        recaptcha_patterns = [
            r'grecaptcha\.execute',
            r'recaptcha/api\.js',
            r'data-sitekey',
            r'class="g-recaptcha"',
            r'google\.com/recaptcha',
        ]
        for pattern in recaptcha_patterns:
            if re.search(pattern, html, re.IGNORECASE):
                elements.append({
                    "type": "recaptcha",
                    "pattern": pattern,
                })
                return True, "reCAPTCHA", 0.95, elements

        # 2. hCaptcha 检测
        hcaptcha_patterns = [
            r'hcaptcha\.com/api\.js',
            r'data-hcaptcha-sitekey',
            r'class="h-captcha"',
            r'hcaptcha\.com/challenge',
        ]
        for pattern in hcaptcha_patterns:
            if re.search(pattern, html, re.IGNORECASE):
                elements.append({
                    "type": "hcaptcha",
                    "pattern": pattern,
                })
                return True, "hCaptcha", 0.95, elements

        # 3. Cloudflare Turnstile 检测
        turnstile_patterns = [
            r'challenges\.cloudflare\.com',
            r'cf-challenge-platform',
            r'turnstile\.api\.js',
            r'data-sitekey',
        ]
        for pattern in turnstile_patterns:
            if re.search(pattern, html, re.IGNORECASE):
                # 检查是否是 Turnstile 而非其他 Cloudflare 挑战
                if "turnstile" in html.lower() or "challenge" in html.lower():
                    elements.append({
                        "type": "cloudflare_turnstile",
                        "pattern": pattern,
                    })
                    return True, "Cloudflare Turnstile", 0.85, elements

        # 4. Cloudflare 通用挑战
        if "cloudflare" in html.lower() and "challenge" in html.lower():
            elements.append({
                "type": "cloudflare_challenge",
                "value": "Cloudflare security challenge detected",
            })
            return True, "Cloudflare Challenge", 0.90, elements

        # 5. 普通图像验证码检测
        image_captcha_patterns = [
            r'<img[^>]+alt=["\']?(captcha|verification|security)["\']?',
            r'<input[^>]+name=["\']?(captcha|code|verification)',
            r'<canvas[^>]+class=["\']?captcha',
            r'captcha.*\.png',
        ]
        for pattern in image_captcha_patterns:
            if re.search(pattern, html, re.IGNORECASE):
                elements.append({
                    "type": "image_captcha",
                    "pattern": pattern,
                })
                return True, "Image CAPTCHA", 0.70, elements

        # 6. Simple text/数学验证码
        text_captcha_patterns = [
            r'请输入下面的验证码',
            r'请完成安全验证',
            r'enter the code',
            r'prove you are human',
        ]
        for pattern in text_captcha_patterns:
            if re.search(pattern, html):
                elements.append({
                    "type": "text_captcha",
                    "pattern": pattern,
                })
                return True, "Text CAPTCHA", 0.60, elements

        # 未检测到 CAPTCHA
        return False, "none", 0.0, []

    def _get_recommendation(self, captcha_type: str, confidence: float) -> tuple[str, bool]:
        """获取处理建议"""
        if confidence < 0.5:
            return "可能误检，请人工确认", True
        
        recommendations = {
            "reCAPTCHA": (
                "需要第三方服务解决 (如 2Captcha, Anti-Captcha) 或手动交互",
                False  # 难以自动绕过
            ),
            "hCaptcha": (
                "需要第三方服务解决或手动交互",
                False
            ),
            "Cloudflare Turnstile": (
                "尝试: 1) 使用真实浏览器环境 2) 等待后重试 3) 使用代理",
                True  # 有可能绕过
            ),
            "Cloudflare Challenge": (
                "尝试: 1) 等待自动跳转 2) 使用真实浏览器 3) 更换 IP",
                True
            ),
            "Image CAPTCHA": (
                "可以尝试 OCR (如 pytesseract) 或第三方服务",
                False
            ),
            "Text CAPTCHA": (
                "可以尝试简单 OCR 或机器学习识别",
                False
            ),
        }
        
        return recommendations.get(captcha_type, ("未知 CAPTCHA 类型", False))


# 注册工具
try:
    from axelo.tools.base import get_registry
    get_registry().register(CaptchaTool())
    log.info("captcha_tool_registered")
except Exception as e:
    log.warning("captcha_tool_register_failed", error=str(e))