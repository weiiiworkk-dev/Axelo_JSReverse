"""
Atomic Writer - 原子写入工具

提供安全的文件写入操作，防止并发写入导致的数据损坏。

特性:
- 原子写入: 先写临时文件，再原子重命名
- 跨平台: 支持 Windows/Linux/Mac
- 错误处理: 自动清理失败的临时文件
- fsync: 确保数据刷入磁盘

用法:
    from axelo.storage.atomic_writer import AtomicWriter
    
    # 写入 JSON
    AtomicWriter.write_json(Path("data.json"), {"key": "value"})
    
    # 读取 JSON
    data = AtomicWriter.read_json(Path("data.json"))
"""
from __future__ import annotations

import os
import json
import tempfile
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class AtomicWriter:
    """原子写入工具类"""
    
    @staticmethod
    def write_json(path: Path, data: dict, indent: int = 2) -> None:
        """
        原子写入 JSON 文件
        
        Args:
            path: 目标文件路径
            data: 要写入的字典数据
            indent: JSON 缩进
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # 1. 创建临时文件
        temp_fd, temp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=".tmp_",
            suffix=".json"
        )
        
        try:
            # 2. 写入数据
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=indent)
                f.flush()
                # 强制刷盘，确保数据写入
                os.fsync(f.fileno())
            
            # 3. 原子重命名
            # 在 Windows 上，如果目标文件存在，需要先删除
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
            
            os.replace(temp_path, path)
            log.debug("atomic_write_json_success", path=str(path))
            
        except Exception as e:
            # 4. 失败时清理临时文件
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except OSError:
                pass
            log.error("atomic_write_json_failed", path=str(path), error=str(e))
            raise
    
    @staticmethod
    def read_json(path: Path) -> dict | None:
        """
        安全读取 JSON 文件
        
        Args:
            path: 文件路径
            
        Returns:
            解析后的字典，失败返回 None
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, OSError) as e:
            log.warning("atomic_read_json_failed", path=str(path), error=str(e))
            return None
    
    @staticmethod
    def write_text(path: Path, content: str) -> None:
        """
        原子写入文本文件
        
        Args:
            path: 目标文件路径
            content: 要写入的文本
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        temp_fd, temp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=".tmp_",
            suffix=".txt"
        )
        
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
            
            os.replace(temp_path, path)
            log.debug("atomic_write_text_success", path=str(path))
            
        except Exception as e:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except OSError:
                pass
            log.error("atomic_write_text_failed", path=str(path), error=str(e))
            raise
    
    @staticmethod
    def read_text(path: Path) -> str | None:
        """
        安全读取文本文件
        
        Args:
            path: 文件路径
            
        Returns:
            文件内容，失败返回 None
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except (FileNotFoundError, OSError) as e:
            log.warning("atomic_read_text_failed", path=str(path), error=str(e))
            return None
    
    @staticmethod
    def write_bytes(path: Path, content: bytes) -> None:
        """
        原子写入二进制文件
        
        Args:
            path: 目标文件路径
            content: 二进制内容
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        temp_fd, temp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=".tmp_",
            suffix=".bin"
        )
        
        try:
            with os.fdopen(temp_fd, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
            
            os.replace(temp_path, path)
            log.debug("atomic_write_bytes_success", path=str(path))
            
        except Exception as e:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except OSError:
                pass
            log.error("atomic_write_bytes_failed", path=str(path), error=str(e))
            raise


# 便捷函数
def atomic_write_json(path: Path, data: dict) -> None:
    """便捷函数: 原子写入 JSON"""
    AtomicWriter.write_json(path, data)


def atomic_read_json(path: Path) -> dict | None:
    """便捷函数: 读取 JSON"""
    return AtomicWriter.read_json(path)


def atomic_write_text(path: Path, content: str) -> None:
    """便捷函数: 原子写入文本"""
    AtomicWriter.write_text(path, content)


def atomic_read_text(path: Path) -> str | None:
    """便捷函数: 读取文本"""
    return AtomicWriter.read_text(path)