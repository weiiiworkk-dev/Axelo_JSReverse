"""
Unified Storage Module

Consolidated storage:
- axelo/storage/adapter_registry.py
- axelo/storage/analysis_cache.py
- axelo/storage/session_state_store.py
- axelo/storage/workflow_store.py

Version: 2.0 (Unified)
Created: 2026-04-07
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

import structlog

log = structlog.get_logger()


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class StorageRecord:
    """Generic storage record"""
    id: str
    data: dict
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class AdapterRecord:
    """Adapter registry record"""
    adapter_id: str
    adapter_type: str  # "python_reconstruct", "js_bridge"
    target_url: str
    code: str
    manifest: dict
    verified: bool = False
    created_at: datetime = field(default_factory=datetime.now)


# =============================================================================
# UNIFIED STORAGE
# =============================================================================

class UnifiedStorage:
    """
    Unified storage manager combining functionality from multiple storage modules.
    """

    def __init__(self, storage_dir: Path):
        self._storage_dir = storage_dir
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = storage_dir / "unified_storage.db"
        self._init_database()

    def _init_database(self):
        """Initialize database schema"""
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        # Create unified table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS storage_records (
                id TEXT PRIMARY KEY,
                record_type TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()

    async def save(self, record_id: str, record_type: str, data: dict) -> None:
        """Save a record"""
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        cursor.execute(
            "INSERT OR REPLACE INTO storage_records (id, record_type, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (record_id, record_type, json.dumps(data), now, now)
        )
        
        conn.commit()
        conn.close()
        
        log.info("storage_save", record_id=record_id, record_type=record_type)

    async def load(self, record_id: str) -> Optional[dict]:
        """Load a record"""
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT data FROM storage_records WHERE id = ?",
            (record_id,)
        )
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            return json.loads(row[0])
        return None

    async def delete(self, record_id: str) -> None:
        """Delete a record"""
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM storage_records WHERE id = ?", (record_id,))
        
        conn.commit()
        conn.close()

    async def list_records(self, record_type: Optional[str] = None) -> list[dict]:
        """List all records, optionally filtered by type"""
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        if record_type:
            cursor.execute(
                "SELECT id, record_type, data, created_at, updated_at FROM storage_records WHERE record_type = ?",
                (record_type,)
            )
        else:
            cursor.execute(
                "SELECT id, record_type, data, created_at, updated_at FROM storage_records"
            )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": row[0],
                "record_type": row[1],
                "data": json.loads(row[2]),
                "created_at": row[3],
                "updated_at": row[4],
            }
            for row in rows
        ]


# =============================================================================
# ADAPTER REGISTRY (from adapter_registry.py)
# =============================================================================

class AdapterRegistry:
    """Registry for verified adapters (re-impl for compatibility)"""
    
    def __init__(self, registry_dir: Path):
        self._registry_dir = registry_dir
        self._registry_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = registry_dir / "adapters.db"
        self._init_db()
    
    def _init_db(self):
        """Initialize adapter database"""
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS adapters (
                adapter_id TEXT PRIMARY KEY,
                adapter_type TEXT NOT NULL,
                target_url TEXT NOT NULL,
                code TEXT,
                manifest TEXT,
                verified INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
    
    async def register(self, adapter: AdapterRecord) -> None:
        """Register an adapter"""
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT OR REPLACE INTO adapters (adapter_id, adapter_type, target_url, code, manifest, verified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                adapter.adapter_id,
                adapter.adapter_type,
                adapter.target_url,
                adapter.code,
                json.dumps(adapter.manifest),
                1 if adapter.verified else 0,
                adapter.created_at.isoformat()
            )
        )
        
        conn.commit()
        conn.close()
    
    async def find(self, target_url: str, adapter_type: str) -> Optional[AdapterRecord]:
        """Find an adapter"""
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT adapter_id, adapter_type, target_url, code, manifest, verified, created_at FROM adapters WHERE target_url = ? AND adapter_type = ? AND verified = 1",
            (target_url, adapter_type)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return AdapterRecord(
                adapter_id=row[0],
                adapter_type=row[1],
                target_url=row[2],
                code=row[3],
                manifest=json.loads(row[4]),
                verified=bool(row[5]),
                created_at=datetime.fromisoformat(row[6])
            )
        return None


# =============================================================================
# ANALYSIS CACHE (from analysis_cache.py)
# =============================================================================

class AnalysisCache:
    """Cache for analysis results"""
    
    def __init__(self, cache_dir: Path):
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
    
    async def get(self, key: str) -> Optional[dict]:
        """Get cached analysis"""
        cache_file = self._cache_dir / f"{key}.json"
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)
        return None
    
    async def set(self, key: str, value: dict) -> None:
        """Cache analysis result"""
        cache_file = self._cache_dir / f"{key}.json"
        with open(cache_file, "w") as f:
            json.dump(value, f)


# =============================================================================
# SESSION STATE STORE (from session_state_store.py)
# =============================================================================

class SessionStateStore:
    """Store for session states"""
    
    def __init__(self, store_dir: Path):
        self._store_dir = store_dir
        self._store_dir.mkdir(parents=True, exist_ok=True)
    
    async def save(self, session_id: str, state: dict) -> None:
        """Save session state"""
        state_file = self._store_dir / f"{session_id}.json"
        with open(state_file, "w") as f:
            json.dump(state, f)
    
    async def load(self, session_id: str) -> Optional[dict]:
        """Load session state"""
        state_file = self._store_dir / f"{session_id}.json"
        if state_file.exists():
            with open(state_file) as f:
                return json.load(f)
        return None


# =============================================================================
# WORKFLOW STORE (from workflow_store.py)
# =============================================================================

class WorkflowStore:
    """Store for workflow state"""
    
    def __init__(self, store_dir: Path):
        self._store_dir = store_dir
        self._store_dir.mkdir(parents=True, exist_ok=True)
    
    async def save_checkpoint(self, workflow_id: str, checkpoint: dict) -> None:
        """Save workflow checkpoint"""
        checkpoint_file = self._store_dir / f"{workflow_id}_checkpoint.json"
        with open(checkpoint_file, "w") as f:
            json.dump(checkpoint, f)
    
    async def load_checkpoint(self, workflow_id: str) -> Optional[dict]:
        """Load workflow checkpoint"""
        checkpoint_file = self._store_dir / f"{workflow_id}_checkpoint.json"
        if checkpoint_file.exists():
            with open(checkpoint_file) as f:
                return json.load(f)
        return None


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_storage(storage_dir: Path) -> UnifiedStorage:
    """Create unified storage instance"""
    return UnifiedStorage(storage_dir)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    "StorageRecord",
    "AdapterRecord",
    # Main classes
    "UnifiedStorage",
    "AdapterRegistry",
    "AnalysisCache",
    "SessionStateStore",
    "WorkflowStore",
    # Utilities
    "create_storage",
]
