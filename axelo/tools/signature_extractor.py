"""
Signature Extractor - 签名密钥提取器

三层密钥提取:
1. 硬编码密钥: 从JS代码中查找直接写的密钥
2. API获取密钥: 从网络请求中查找密钥获取接口
3. 计算密钥: 分析密钥生成逻辑

用法:
    extractor = SignatureExtractor()
    result = await extractor.extract(js_code, api_calls)
"""
from __future__ import annotations

import re
import asyncio
from typing import Any
from urllib.parse import urljoin

import structlog
from httpx import AsyncClient

log = structlog.get_logger(__name__)


class SignatureExtractor:
    """从JS中提取签名密钥"""
    
    # 常见的密钥变量名模式
    KEY_PATTERNS = [
        r'(?:key|secret|token|apiKey|api_key|apikey)\s*[:=]\s*["\']([a-zA-Z0-9]{16,})["\']',
        r'(?:key|secret|token)\s*=\s*["\']([a-zA-Z0-9]{16,})["\']',
        r'const\s+(\w*(?:Key|Secret|Token)\w*)\s*=\s*["\']([^"\']{16,})["\']',
        r'let\s+(\w*(?:Key|Secret|Token)\w*)\s*=\s*["\']([^"\']{16,})["\']',
    ]
    
    # CryptoJS 密钥模式
    CRYPTOJS_PATTERNS = [
        r'CryptoJS\.enc\.Utf8\.parse\(["\']([a-zA-Z0-9]{16,})["\']',
        r'CryptoJS\.AES\.encrypt\([^,]+,\s*["\']([a-zA-Z0-9]{16,})["\']',
        r'new\s+JSEncrypt\([^)]*["\']([a-zA-Z0-9]{16,})["\']',
    ]
    
    # 可能的密钥获取API模式
    KEY_API_PATTERNS = [
        r'fetch\s*\(\s*["\']([^"\']*(?:key|token|secret)[^"\']*)["\']',
        r'axios\.\w+\s*\(\s*["\']([^"\']*(?:key|token|secret)[^"\']*)["\']',
        r'\$\.ajax\s*\(\s*{\s*url\s*:\s*["\']([^"\']*(?:key|token|secret)[^"\']*)["\']',
    ]
    
    def __init__(self):
        self._client = None
    
    async def extract(self, js_code: str, api_calls: list = None) -> dict:
        """
        提取签名密钥
        
        Returns:
            {
                "key_source": "hardcoded" | "api" | "computed" | "unknown",
                "key_value": str | None,
                "algorithm": str | None,
                "param_format": str | None,
                "confidence": float,
                "details": dict,
            }
        """
        result = {
            "key_source": "unknown",
            "key_value": None,
            "algorithm": None,
            "param_format": None,
            "confidence": 0.0,
            "details": {},
        }
        
        if not js_code:
            return result
        
        # Layer 1: 硬编码密钥
        log.info("signature_extractor_layer1_hardcoded")
        hardcoded = self._find_hardcoded_key(js_code)
        if hardcoded:
            result.update(hardcoded)
            result["key_source"] = "hardcoded"
            result["confidence"] = 0.8
            log.info("signature_extractor_found_hardcoded", key=result.get("key_value", "")[:10])
            return result
        
        # Layer 2: API获取密钥
        if api_calls:
            log.info("signature_extractor_layer2_api")
            api_key = await self._find_api_key(js_code, api_calls)
            if api_key:
                result.update(api_key)
                result["key_source"] = "api"
                result["confidence"] = 0.6
                log.info("signature_extractor_found_api", key_source=api_key.get("key_value"))
                return result
        
        # Layer 3: 计算密钥 (分析密钥生成逻辑)
        log.info("signature_extractor_layer3_computed")
        computed = self._analyze_key_computation(js_code)
        if computed:
            result.update(computed)
            result["key_source"] = "computed"
            result["confidence"] = 0.4
            log.info("signature_extractor_found_computed", algorithm=computed.get("algorithm"))
            return result
        
        log.info("signature_extractor_not_found")
        return result
    
    def _find_hardcoded_key(self, js_code: str) -> dict | None:
        """查找硬编码密钥"""
        
        # 方法1: 通用密钥模式
        for pattern in self.KEY_PATTERNS:
            matches = re.finditer(pattern, js_code, re.IGNORECASE)
            for match in matches:
                # 排除明显的测试/假密钥
                if match.group(1):
                    key_value = match.group(1) if match.lastindex == 1 else match.group(2)
                    if key_value and len(key_value) >= 16:
                        # 检查是否是假密钥
                        if self._is_fake_key(key_value):
                            continue
                        
                        return {
                            "key_value": key_value,
                            "algorithm": self._detect_algorithm_from_context(js_code, match.start()),
                            "param_format": self._detect_param_format(js_code),
                        }
        
        # 方法2: CryptoJS 密钥模式
        for pattern in self.CRYPTOJS_PATTERNS:
            matches = re.finditer(pattern, js_code)
            for match in matches:
                if match.group(1):
                    key_value = match.group(1)
                    if len(key_value) >= 16:
                        return {
                            "key_value": key_value,
                            "algorithm": "AES/CBC",
                            "param_format": "encrypted",
                        }
        
        return None
    
    async def _find_api_key(self, js_code: str, api_calls: list) -> dict | None:
        """查找API获取的密钥"""
        
        # 从JS代码中找密钥获取接口
        key_api_urls = []
        for pattern in self.KEY_API_PATTERNS:
            matches = re.finditer(pattern, js_code, re.IGNORECASE)
            for match in matches:
                url = match.group(1)
                if url and ("key" in url.lower() or "token" in url.lower()):
                    key_api_urls.append(url)
        
        if not key_api_urls:
            return None
        
        # 尝试访问密钥API (如果有提供基础URL)
        for url in key_api_urls[:3]:
            try:
                if not self._client:
                    self._client = AsyncClient(timeout=10.0)
                
                # 完整URL
                full_url = url if url.startswith("http") else f"https://{url}"
                
                response = await self._client.get(full_url)
                if response.status_code == 200:
                    # 尝试从响应中提取密钥
                    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else None
                    
                    if data:
                        # 常见密钥字段
                        key_fields = ["key", "token", "secret", "apiKey", "api_key", "access_token"]
                        for field in key_fields:
                            if field in data:
                                return {
                                    "key_value": str(data[field]),
                                    "algorithm": "from_api",
                                    "param_format": "api_response",
                                    "details": {"api_url": full_url, "response_fields": list(data.keys())},
                                }
            except Exception as e:
                log.debug("signature_extractor_api_fetch_failed", url=url, error=str(e))
        
        return None
    
    def _analyze_key_computation(self, js_code: str) -> dict | None:
        """分析密钥生成逻辑"""
        
        # 查找密钥生成函数
        key_gen_patterns = [
            r'function\s+(\w*key\w*)\s*\([^)]*\)',
            r'const\s+(\w*key\w*)\s*=\s*(?:function|\([^)]*\)\s*=>)',
            r'generate\w*Key\s*\(',
            r'create\w*Key\s*\(',
            r'md5\s*\([^)]+\)',
            r'sha\d+\s*\([^)]+\)',
        ]
        
        for pattern in key_gen_patterns:
            matches = re.finditer(pattern, js_code, re.IGNORECASE)
            for match in matches:
                func_name = match.group(1) if match.lastindex else "generateKey"
                
                # 提取函数体
                start = match.start()
                end = min(start + 500, len(js_code))
                func_body = js_code[start:end]
                
                # 检测算法
                algorithm = None
                if "md5" in func_body.lower():
                    algorithm = "MD5"
                elif "sha256" in func_body.lower():
                    algorithm = "SHA256"
                elif "sha1" in func_body.lower():
                    algorithm = "SHA1"
                elif "aes" in func_body.lower():
                    algorithm = "AES"
                
                if algorithm:
                    return {
                        "key_value": None,  # 无法直接获取，需要执行
                        "algorithm": algorithm,
                        "param_format": "computed",
                        "details": {
                            "generation_function": func_name,
                            "algorithm_detected": algorithm,
                        },
                    }
        
        return None
    
    def _detect_algorithm_from_context(self, js_code: str, position: int) -> str | None:
        """从上下文检测算法"""
        
        # 获取附近200字符
        start = max(0, position - 100)
        end = min(len(js_code), position + 100)
        context = js_code[start:end].lower()
        
        if "hmac" in context or "sha256" in context:
            return "HMAC-SHA256"
        if "sha1" in context:
            return "HMAC-SHA1"
        if "sha512" in context:
            return "HMAC-SHA512"
        if "md5" in context:
            return "MD5"
        if "aes" in context:
            return "AES"
        if "rsa" in context:
            return "RSA"
        
        return None
    
    def _detect_param_format(self, js_code: str) -> str | None:
        """检测签名参数格式"""
        
        # 查找签名函数调用
        sign_patterns = [
            r'sign\w*\s*\(\s*([^)]+)\)',
            r'signature\s*=\s*([^;\n]+)',
            r'generateSignature\s*\(\s*([^)]+)\)',
        ]
        
        for pattern in sign_patterns:
            match = re.search(pattern, js_code, re.IGNORECASE)
            if match:
                params = match.group(1).strip()
                # 分析参数格式
                if "&" in params:
                    return "query_string"
                if "JSON" in params or "{" in params:
                    return "json_body"
                if "Base64" in params:
                    return "base64"
        
        return "default"
    
    def _is_fake_key(self, key: str) -> bool:
        """检查是否是假密钥 (测试用)"""
        
        fake_patterns = [
            "test", "demo", "example", "sample",
            "placeholder", "xxx", "your_",
            "123456", "abcdef",
            "YOUR_", "REPLACE_",
        ]
        
        key_lower = key.lower()
        return any(pattern in key_lower for pattern in fake_patterns)
    
    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None


# 注册为工具辅助类
# 使用方式: from axelo.tools.signature_extractor import SignatureExtractor
