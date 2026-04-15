"""
增强的 JS 反混淆器 - Advanced Deobfuscator

在现有的内置方法基础上，增加更多高级反混淆技术:
- 更精确的字符串数组解码
- 更好的控制流还原
- 代码结构分析
- 函数和变量追踪

这是现有 deobfuscate_tool.py 的增强模块
"""

import re
from typing import Any


class AdvancedDeobfuscator:
    """高级反混淆器 - 增强版"""
    
    def __init__(self):
        self._string_arrays = {}
        self._variable_map = {}
    
    def deobfuscate(self, js_code: str) -> dict:
        """执行高级反混淆"""
        
        # 1. 预处理 - 规范化代码
        code = self._preprocess(js_code)
        
        # 2. 提取字符串数组
        self._extract_string_arrays(code)
        
        # 3. 替换字符串数组引用
        code = self._replace_string_references(code)
        
        # 4. 恢复十六进制变量名
        code = self._restore_variables(code)
        
        # 5. 简化控制流
        code = self._simplify_control_flow(code)
        
        # 6. 美化输出
        code = self._prettify(code)
        
        # 计算改善度
        improvement = self._calculate_improvement(js_code, code)
        
        return {
            "code": code,
            "improvement": improvement,
            "techniques_used": self._get_techniques(),
        }
    
    def _preprocess(self, code: str) -> str:
        """预处理 - 清理和规范化"""
        # 移除注释
        code = re.sub(r'//.*?$', '', code, flags=re.MULTILINE)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        
        # 规范化空白
        code = re.sub(r'\s+', ' ', code)
        
        return code
    
    def _extract_string_arrays(self, code: str) -> None:
        """提取字符串数组"""
        # 匹配各种格式的字符串数组
        patterns = [
            # var _0x1234 = ["...", "...", "..."]
            r'var\s+(_0x[a-f0-9]+)\s*=\s*\[([^\]]+)\]',
            # const _0x1234 = ["...", "...", "..."]
            r'const\s+(_0x[a-f0-9]+)\s*=\s*\[([^\]]+)\]',
            # let _0x1234 = ["...", "...", "..."]
            r'let\s+(_0x[a-f0-9]+)\s*=\s*\[([^\]]+)\]',
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, code):
                var_name = match.group(1)
                strings = match.group(2)
                
                # 解析字符串列表
                string_list = re.findall(r'"([^"]*)"', strings)
                if string_list:
                    self._string_arrays[var_name] = string_list
    
    def _replace_string_references(self, code: str) -> str:
        """替换字符串数组引用"""
        for var_name, strings in self._string_arrays.items():
            # 替换数组访问 _0x1234[0] -> "actual_string"
            for i, s in enumerate(strings):
                # 跳过空字符串和太短的
                if len(s) > 2:
                    code = re.sub(
                        rf'{var_name}\[{i}\]',
                        f'"{self._escape_string(s)}"',
                        code
                    )
        
        return code
    
    def _escape_string(self, s: str) -> str:
        """转义字符串中的特殊字符"""
        return s.replace('\\', '\\\\').replace('"', '\\"')
    
    def _restore_variables(self, code: str) -> str:
        """恢复变量名为有意义的名称"""
        # 统计变量使用频率
        var_usage = {}
        
        # 查找十六进制变量使用
        hex_vars = re.findall(r'_0x([a-f0-9]{4,})', code)
        for var in hex_vars:
            var_usage[var] = var_usage.get(var, 0) + 1
        
        # 按使用频率排序，分配有意义的名称
        sorted_vars = sorted(var_usage.items(), key=lambda x: x[1], reverse=True)
        
        # 分配名称
        prefixes = ['data', 'config', 'utils', 'func', 'str', 'val', 'key', 'cache']
        
        for i, (var, _) in enumerate(sorted_vars[:50]):
            if i < len(prefixes):
                new_name = f'{prefixes[i]}_{var[:6]}'  # 保持唯一性
                self._variable_map[f'_0x{var}'] = new_name
                code = re.sub(rf'\b_0x{var}\b', new_name, code)
        
        return code
    
    def _simplify_control_flow(self, code: str) -> str:
        """简化控制流"""
        # 移除空的 switch 语句
        code = re.sub(r'switch\s*\([^)]+\)\s*\{\s*\}', '', code)
        
        # 简化死代码
        code = re.sub(r'if\s*\(\s*false\s*\)\s*\{[^}]*\}', '', code)
        
        # 简化 constant conditions
        code = re.sub(r'if\s*\(\s*true\s*\)\s*', 'if (1) ', code)
        
        # 移除重复的分号
        code = re.sub(r';+', ';', code)
        
        return code
    
    def _prettify(self, code: str) -> str:
        """美化代码"""
        lines = []
        indent = 0
        indent_str = "    "  # 4 空格
        
        for line in code.split(';'):
            line = line.strip()
            if not line:
                continue
            
            # 调整缩进
            if line.startswith('}') or line.startswith(']'):
                indent = max(0, indent - 1)
            
            lines.append(indent_str * indent + line)
            
            if line.endswith('{') or line.endswith('['):
                indent += 1
        
        return '\n'.join(lines)
    
    def _calculate_improvement(self, original: str, deobfuscated: str) -> dict:
        """计算反混淆改善度"""
        # 计算可读性指标
        original_lines = len(original.split('\n'))
        deobfuscated_lines = len(deobfuscated.split('\n'))
        
        # 计算字符串替换数量
        string_replacements = sum(len(arr) for arr in self._string_arrays.values())
        
        # 计算变量恢复数量
        variables_restored = len(self._variable_map)
        
        return {
            "original_lines": original_lines,
            "deobfuscated_lines": deobfuscated_lines,
            "line_ratio": deobfuscated_lines / original_lines if original_lines > 0 else 1,
            "strings_decoded": string_replacements,
            "variables_restored": variables_restored,
            "readability_score": min(100, (string_replacements * 5 + variables_restored * 3)),
        }
    
    def _get_techniques(self) -> list:
        """获取使用的技术列表"""
        techniques = []
        
        if self._string_arrays:
            techniques.append("string_array_decoding")
        
        if self._variable_map:
            techniques.append("variable_restoration")
        
        techniques.extend(["control_flow_simplification", "code_prettifying"])
        
        return techniques


# 独立函数接口
def advanced_deobfuscate(js_code: str) -> dict:
    """高级反混淆 - 独立函数接口"""
    deobfuscator = AdvancedDeobfuscator()
    return deobfuscator.deobfuscate(js_code)


# 测试
if __name__ == "__main__":
    test_code = '''
    var _0x1a2b = ["hello","world","test","data","config"];
    function _0x3c4d() {
        return _0x1a2b[0] + _0x1a2b[1];
    }
    var _0x5e6f = _0x1a2b[2];
    '''
    
    result = advanced_deobfuscate(test_code)
    print("=== Result ===")
    print(result["code"])
    print("\n=== Improvement ===")
    print(result["improvement"])