"""
Codegen Tool - 代码生成工具

基于分析结果生成可运行的爬虫代码
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from axelo.tools.base import (
    BaseTool,
    ToolInput,
    ToolOutput,
    ToolSchema,
    ToolState,
    ToolResult,
    ToolStatus,
    ToolCategory,
)

log = structlog.get_logger()


@dataclass
class CodegenOutput:
    """代码生成输出"""
    python_code: str = ""
    js_code: str = ""
    requirements: list[str] = field(default_factory=list)
    manifest: dict = field(default_factory=dict)


class CodegenTool(BaseTool):
    """代码生成工具"""
    
    def __init__(self):
        super().__init__()
    
    @property
    def name(self) -> str:
        return "codegen"
    
    @property
    def description(self) -> str:
        return "代码生成：根据签名假设生成可运行的爬虫代码"
    
    def _create_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.CODEGEN,
            input_schema=[
                ToolInput(
                    name="hypothesis",
                    type="string",
                    description="签名假设",
                    required=True,
                ),
                ToolInput(
                    name="signature_type",
                    type="string",
                    description="签名类型",
                    required=False,
                ),
                ToolInput(
                    name="algorithm",
                    type="string",
                    description="算法",
                    required=False,
                ),
                ToolInput(
                    name="target_url",
                    type="string",
                    description="目标 URL",
                    required=True,
                ),
                ToolInput(
                    name="key_location",
                    type="string",
                    description="密钥位置",
                    required=False,
                ),
                ToolInput(
                    name="output_format",
                    type="string",
                    description="输出格式: python, js, both",
                    required=False,
                    default="python",
                ),
            ],
            output_schema=[
                ToolOutput(name="python_code", type="string", description="Python 代码"),
                ToolOutput(name="js_code", type="string", description="JavaScript 代码"),
                ToolOutput(name="requirements", type="array", description="依赖列表"),
                ToolOutput(name="manifest", type="object", description="清单"),
            ],
            timeout_seconds=120,
            retry_enabled=True,
            max_retries=2,
        )
    
    async def execute(self, input_data: dict[str, Any], state: ToolState) -> ToolResult:
        """执行代码生成"""
        hypothesis = input_data.get("hypothesis")
        target_url = input_data.get("target_url")
        
        if not hypothesis:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: hypothesis",
            )
        
        if not target_url:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: target_url",
            )
        
        try:
            output = self._generate(input_data)
            
            log.info("codegen_success", 
                     url=target_url, 
                     algorithm=input_data.get("algorithm", "unknown"))
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output={
                    "python_code": output.python_code,
                    "js_code": output.js_code,
                    "requirements": output.requirements,
                    "manifest": output.manifest,
                },
            )
            
        except Exception as exc:
            log.error("codegen_tool_failed", error=str(exc))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(exc),
            )
    
    def _generate(self, input_data: dict) -> CodegenOutput:
        """生成代码"""
        output = CodegenOutput()
        
        algorithm = input_data.get("algorithm", "unknown")
        signature_type = input_data.get("signature_type", "")
        target_url = input_data.get("target_url", "")
        key_location = input_data.get("key_location", "")
        output_format = input_data.get("output_format", "python")
        hypothesis = input_data.get("hypothesis", "")
        
        # 生成 Python 代码
        if output_format in ("python", "both"):
            output.python_code = self._generate_python(
                target_url,
                algorithm,
                signature_type,
                key_location,
                hypothesis,
            )
        
        # 生成 JS 代码
        if output_format in ("js", "both"):
            output.js_code = self._generate_js(
                target_url,
                algorithm,
                signature_type,
                key_location,
            )
        
        # 依赖
        output.requirements = [
            "httpx>=0.27.0",
            "playwright>=1.48.0",
        ]
        
        # 根据算法添加额外依赖
        algos_lower = algorithm.lower() if algorithm else ""
        if "aes" in algos_lower or "rsa" in algos_lower:
            output.requirements.append("pycryptodome>=3.18.0")
        if "hmac" in algos_lower:
            output.requirements.append("pycryptodome>=3.18.0")
        
        # 清单
        output.manifest = {
            "target_url": target_url,
            "signature_type": signature_type,
            "algorithm": algorithm,
            "key_location": key_location,
            "hypothesis": hypothesis[:200],
            "output_format": output_format,
            "generated_at": "2026-04-08",
        }
        
        return output
    
    def _generate_python(self, url: str, algorithm: str, sig_type: str, 
                        key_location: str, hypothesis: str) -> str:
        """生成 Python 代码"""
        
        # 根据算法选择不同的签名实现
        algos = algorithm.lower() if algorithm else ""
        
        if "hmac" in algos or "sha" in algos:
            sig_impl = self._python_hmac_impl(algos)
        elif "aes" in algos:
            sig_impl = self._python_aes_impl()
        elif "rsa" in algos:
            sig_impl = self._python_rsa_impl()
        else:
            sig_impl = self._python_generic_impl()
        
        return f'''"""
Auto-generated crawler for {url}
Generated by Axelo AI

Signature Analysis:
- Algorithm: {algorithm}
- Type: {sig_type}
- Hypothesis: {hypothesis[:100]}

Instructions:
1. Replace SECRET_KEY with actual key
2. Adjust parameter construction as needed
3. Test with different parameter values
"""
import asyncio
import hashlib
import hmac
import base64
import json
from datetime import datetime
from urllib.parse import urlencode, quote

import httpx

{sig_impl}


async def make_request(url: str, params: dict = None) -> dict:
    """Make authenticated request"""
    # Generate signature
    signature = generate_signature(SECRET_KEY, params or {{}})
    
    # Add signature to params
    request_params = dict(params or {{}})
    request_params["signature"] = signature
    request_params["timestamp"] = str(int(datetime.now().timestamp() * 1000))
    
    async with httpx.AsyncClient(
        timeout=30.0,
        headers={{
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }}
    ) as client:
        response = await client.get(url, params=request_params)
        return {{
            "status": response.status_code,
            "headers": dict(response.headers),
            "data": response.text,
            "json": response.json() if response.headers.get("content-type", "").startswith("application/json") else None,
        }}


async def main():
    target_url = "{url}"
    
    # Example parameters - adjust based on target API
    params = {{
        "page": 1,
        "size": 20,
    }}
    
    result = await make_request(target_url, params)
    print(f"Status: {{result['status']}}")
    print(f"Response: {{result['data'][:500]}}")


if __name__ == "__main__":
    asyncio.run(main())
'''
    
    def _python_hmac_impl(self, algo: str) -> str:
        """HMAC 实现"""
        hash_algo = "sha256"
        if "sha1" in algo:
            hash_algo = "sha1"
        elif "sha512" in algo:
            hash_algo = "sha512"
        
        return f'''
# Configuration - REPLACE WITH ACTUAL KEY
SECRET_KEY = "YOUR_SECRET_KEY_HERE"

def generate_signature(secret_key: str, params: dict) -> str:
    """Generate HMAC-{hash_algo.upper()} signature"""
    # Sort parameters and create string
    sorted_params = sorted(params.items())
    param_str = "&".join([f"{{k}}={{v}}" for k, v in sorted_params])
    
    # Create signature
    message = f"{{param_str}}&key={{secret_key}}"
    signature = hmac.new(
        secret_key.encode(),
        message.encode(),
        getattr(hashlib, hash_algo)
    ).hexdigest()
    
    return signature
'''
    
    def _python_aes_impl(self) -> str:
        """AES 实现"""
        return '''
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import base64
import json

SECRET_KEY = "YOUR_32BYTE_KEY_HERE"  # Must be 32 bytes for AES-256

def generate_signature(secret_key: str, params: dict) -> str:
    """Generate AES signature"""
    # Convert params to JSON and pad
    data = json.dumps(params, sort_keys=True)
    padded = pad(data.encode(), AES.block_size)
    
    # Encrypt
    cipher = AES.new(secret_key.encode(), AES.MODE_CBC, iv=b'0000000000000000')
    encrypted = cipher.encrypt(padded)
    
    # Base64 encode
    return base64.b64encode(encrypted).decode()
'''
    
    def _python_rsa_impl(self) -> str:
        """RSA 实现"""
        return '''
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256
import base64

# Load private key - REPLACE with actual key
PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
YOUR_PRIVATE_KEY_HERE
-----END RSA PRIVATE KEY-----"""

SECRET_KEY = PRIVATE_KEY

def generate_signature(secret_key: str, params: dict) -> str:
    """Generate RSA-SHA256 signature"""
    # Create message
    sorted_params = sorted(params.items())
    message = "&".join([f"{k}={v}" for k, v in sorted_params])
    
    # Load key and sign
    key = RSA.import_key(secret_key)
    h = SHA256.new(message.encode())
    signer = pkcs1_15.new(key)
    signature = signer.sign(h)
    
    return base64.b64encode(signature).decode()
'''
    
    def _python_generic_impl(self) -> str:
        """通用实现"""
        return '''
SECRET_KEY = "YOUR_SECRET_KEY_HERE"

def generate_signature(secret_key: str, params: dict) -> str:
    """Generate signature based on sorted parameters"""
    # Sort parameters
    sorted_params = sorted(params.items())
    param_str = "&".join([f"{k}={v}" for k, v in sorted_params])
    
    # Default: SHA256 hash
    import hashlib
    message = f"{param_str}&key={secret_key}"
    return hashlib.sha256(message.encode()).hexdigest()
'''
    
    def _generate_js(self, url: str, algorithm: str, sig_type: str, 
                     key_location: str) -> str:
        """生成 JS 代码"""
        
        algos = algorithm.lower() if algorithm else ""
        
        if "hmac" in algos or "sha" in algos:
            sig_impl = self._js_hmac_impl(algos)
        elif "aes" in algos:
            sig_impl = self._js_aes_impl()
        else:
            sig_impl = self._js_generic_impl()
        
        return f'''/**
 * Auto-generated crawler for {url}
 * Algorithm: {algorithm}
 * Type: {sig_type}
 */

{sig_impl}

async function makeRequest(url, params = {{}}) {{
    const signature = generateSignature(SECRET_KEY, params);
    
    // Add signature and timestamp
    const requestParams = new URLSearchParams(params);
    requestParams.append('signature', signature);
    requestParams.append('timestamp', Date.now().toString());
    
    const fullUrl = `${{url}}?${{requestParams.toString()}}`;
    
    const response = await fetch(fullUrl, {{
        method: 'GET',
        headers: {{
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
        }}
    }});
    
    return {{
        status: response.status,
        data: await response.text(),
        json: await response.json().catch(() => null),
    }};
}}

// Example usage
(async () => {{
    const url = "{url}";
    const params = {{ page: 1, size: 20 }};
    
    const result = await makeRequest(url, params);
    console.log(`Status: ${{result.status}}`);
    console.log(`Response: ${{result.data.substring(0, 500)}}`);
}})();
'''
    
    def _js_hmac_impl(self, algo: str) -> str:
        """JS HMAC 实现"""
        hash_algo = "SHA-256"
        if "sha1" in algo:
            hash_algo = "SHA-1"
        elif "sha512" in algo:
            hash_algo = "SHA-512"
        
        return f'''
const SECRET_KEY = "YOUR_SECRET_KEY_HERE";

async function generateSignature(secretKey, params) {{
    // Sort params
    const sorted = Object.keys(params).sort();
    const paramStr = sorted.map(k => `${{k}}=${{params[k]}}`).join('&');
    
    const message = `${{paramStr}}&key=${{secretKey}}`;
    
    // HMAC-{hash_algo}
    const encoder = new TextEncoder();
    const keyData = encoder.encode(secretKey);
    const msgData = encoder.encode(message);
    
    const cryptoKey = await crypto.subtle.importKey(
        'raw', keyData,
        {{ name: 'HMAC', hash: '{hash_algo}' }},
        false, ['sign']
    );
    
    const signature = await crypto.subtle.sign('HMAC', cryptoKey, msgData);
    const hashArray = Array.from(new Uint8Array(signature));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}}
'''
    
    def _js_aes_impl(self) -> str:
        """JS AES 实现"""
        return '''
const SECRET_KEY = "YOUR_32BYTE_KEY_HERE";  // 32 bytes

async function generateSignature(secretKey, params) {{
    // Import AES key
    const key = await crypto.subtle.importKey(
        'raw',
        new TextEncoder().encode(secretKey),
        { name: 'AES-CBC' },
        false,
        ['encrypt']
    );
    
    // Encode params as JSON
    const data = JSON.stringify(params, Object.keys(params).sort());
    const iv = new Uint8Array(16); // Zero IV
    
    const encrypted = await crypto.subtle.encrypt(
        {{ name: 'AES-CBC', iv }},
        key,
        new TextEncoder().encode(data)
    );
    
    // Base64 encode
    return btoa(String.fromCharCode(...new Uint8Array(encrypted)));
}}
'''
    
    def _js_generic_impl(self) -> str:
        """JS 通用实现"""
        return '''
const SECRET_KEY = "YOUR_SECRET_KEY_HERE";

async function generateSignature(secretKey, params) {{
    // Sort params
    const sorted = Object.keys(params).sort();
    const paramStr = sorted.map(k => `${{k}}=${{params[k]}}`).join('&');
    
    const message = `${{paramStr}}&key=${{secretKey}}`;
    
    // SHA-256 hash
    const encoder = new TextEncoder();
    const data = encoder.encode(message);
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}}
'''


# 注册工具
from axelo.tools.base import get_registry

get_registry().register(CodegenTool())