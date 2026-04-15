"""
Dynamic Analyzer - 动态JS执行分析器

在浏览器环境中执行JS，观察真实行为，提取签名相关信息。

用法:
    analyzer = DynamicAnalyzer()
    result = await analyzer.analyze(page, target_function)
"""
from __future__ import annotations

import json
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class DynamicAnalyzer:
    """动态JS执行分析器"""
    
    # 注入脚本 - 追踪 fetch/XHR 调用
    TRACKER_SCRIPT = """
    (function() {
        window.__axelo_traces = [];
        window.__axelo_signatures = [];
        
        // 追踪 fetch
        const originalFetch = window.fetch;
        window.fetch = function(url, options) {
            window.__axelo_traces.push({
                type: 'fetch',
                url: typeof url === 'string' ? url : url.toString(),
                method: options?.method || 'GET',
                timestamp: Date.now()
            });
            return originalFetch.apply(this, arguments).then(response => {
                // 克隆响应以读取
                const clone = response.clone();
                clone.text().then(text => {
                    window.__axelo_traces.push({
                        type: 'fetch_response',
                        url: typeof url === 'string' ? url : url.toString(),
                        status: response.status,
                        body_length: text.length
                    });
                });
                return response;
            }).catch(err => {
                window.__axelo_traces.push({
                    type: 'fetch_error',
                    url: typeof url === 'string' ? url : url.toString(),
                    error: err.message
                });
                throw err;
            });
        };
        
        // 追踪 XHR
        const originalXHROpen = XMLHttpRequest.prototype.open;
        const originalXHRSend = XMLHttpRequest.prototype.send;
        
        XMLHttpRequest.prototype.open = function(method, url) {
            this.__axelo_url = url;
            this.__axelo_method = method;
            return originalXHROpen.apply(this, arguments);
        };
        
        XMLHttpRequest.prototype.send = function(body) {
            window.__axelo_traces.push({
                type: 'xhr',
                url: this.__axelo_url,
                method: this.__axelo_method,
                body: body ? body.toString().substring(0, 500) : null,
                timestamp: Date.now()
            });
            
            this.addEventListener('load', function() {
                window.__axelo_traces.push({
                    type: 'xhr_response',
                    url: this.__axelo_url,
                    status: this.status,
                    response_length: this.responseText ? this.responseText.length : 0
                });
            });
            
            return originalXHRSend.apply(this, arguments);
        };
        
        // 追踪签名相关函数调用
        const signatureFuncs = ['sign', 'signature', 'generateSignature', 'getSignature', 'encrypt', 'hash'];
        signatureFuncs.forEach(funcName => {
            if (window[funcName]) {
                const original = window[funcName];
                window[funcName] = function(...args) {
                    window.__axelo_signatures.push({
                        function: funcName,
                        args: args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(', '),
                        timestamp: Date.now()
                    });
                    return original.apply(this, args);
                };
            }
        });
        
        console.log('[Axelo] Dynamic tracker injected');
    })();
    """
    
    # 清理脚本
    CLEANUP_SCRIPT = """
    (function() {
        delete window.__axelo_traces;
        delete window.__axelo_signatures;
        console.log('[Axelo] Dynamic tracker cleaned up');
    })();
    """
    
    def __init__(self):
        pass
    
    async def analyze(self, page, target_functions: list = None) -> dict:
        """
        分析页面上的JS行为
        
        Args:
            page: Playwright page 对象
            target_functions: 可选，要触发的函数名列表
            
        Returns:
            {
                "traces": [...],
                "api_calls": [...],
                "signature_calls": [...],
                "analysis": {...}
            }
        """
        log.info("dynamic_analyzer_start")
        
        result = {
            "traces": [],
            "api_calls": [],
            "signature_calls": [],
            "analysis": {},
        }
        
        try:
            # 1. 注入追踪脚本
            await page.evaluate(self.TRACKER_SCRIPT)
            log.debug("dynamic_analyzer_injected")
            
            # 2. 触发目标函数 (如果有)
            if target_functions:
                for func_name in target_functions:
                    try:
                        await page.evaluate(f"if(window.{func_name}) window.{func_name}()")
                    except Exception as e:
                        log.debug("dynamic_analyzer_trigger_failed", func=func_name, error=str(e))
            
            # 3. 等待一段时间让请求发出
            await page.wait_for_timeout(2000)
            
            # 4. 收集追踪数据
            traces = await page.evaluate("window.__axelo_traces || []")
            signatures = await page.evaluate("window.__axelo_signatures || []")
            
            result["traces"] = traces
            result["signature_calls"] = signatures
            
            # 5. 分析 API 调用
            api_calls = []
            for trace in traces:
                if trace.get("type") in ["fetch", "xhr"]:
                    url = trace.get("url", "")
                    # 过滤出可能是API的请求
                    if "/api" in url or "/ajax" in url or "?" in url:
                        api_calls.append({
                            "url": url,
                            "method": trace.get("method", "GET"),
                            "type": trace.get("type"),
                        })
            
            result["api_calls"] = api_calls
            
            # 6. 分析签名调用
            analysis = self._analyze_signatures(signatures, api_calls)
            result["analysis"] = analysis
            
            log.info("dynamic_analyzer_complete", 
                traces=len(traces), 
                api_calls=len(api_calls),
                signatures=len(signatures))
            
        except Exception as e:
            log.error("dynamic_analyzer_failed", error=str(e))
            result["analysis"]["error"] = str(e)
        
        finally:
            # 7. 清理追踪脚本
            try:
                await page.evaluate(self.CLEANUP_SCRIPT)
            except Exception as exc:
                log.error("dynamic_analyzer_cleanup_failed", error=str(exc))
        
        return result
    
    def _analyze_signatures(self, signatures: list, api_calls: list) -> dict:
        """分析签名调用"""
        
        analysis = {
            "has_signatures": len(signatures) > 0,
            "signature_functions": [],
            "likely_signatures": [],
        }
        
        # 提取签名函数名
        func_names = set()
        for sig in signatures:
            func_names.add(sig.get("function", "unknown"))
        
        analysis["signature_functions"] = list(func_names)
        
        # 识别可能的签名函数
        for api_call in api_calls:
            url = api_call.get("url", "")
            # 检查是否有签名参数
            signature_params = ["sign", "signature", "token", "key", "_", "t", "v"]
            has_signature = any(param in url.lower() for param in signature_params)
            
            if has_signature:
                analysis["likely_signatures"].append({
                    "url": url,
                    "method": api_call.get("method"),
                })
        
        return analysis


# 注册为工具辅助类
# 使用方式: from axelo.tools.dynamic_analyzer import DynamicAnalyzer