from __future__ import annotations

from pathlib import Path

from axelo.config import settings
from axelo.platform_.services import ControlPlaneService, FrontierService, IngestService, ResourceManager, SchedulerService
from axelo.platform_.storage import FileEventBus, LocalObjectStore, LocalWarehouseSink, PlatformStore


class PlatformRuntime:
    def __init__(
        self,
        *,
        workspace: Path | None = None,
        database_url: str | None = None,
        event_root: Path | None = None,
        object_store_root: Path | None = None,
        warehouse_root: Path | None = None,
    ) -> None:
        self.workspace = Path(workspace or settings.workspace)
        settings.workspace = self.workspace
        self.platform_root = self.workspace / "platform"
        self.platform_root.mkdir(parents=True, exist_ok=True)

        default_db = database_url or settings.platform_database_url or f"sqlite:///{(self.platform_root / 'metadata.db').as_posix()}"
        self.store = PlatformStore(default_db)
        self.event_bus = FileEventBus(event_root or settings.platform_event_dir)
        self.object_store = LocalObjectStore(object_store_root or settings.platform_object_store_dir)
        self.warehouse = LocalWarehouseSink(warehouse_root or settings.platform_warehouse_dir)

        self.control = ControlPlaneService(self.store, self.event_bus)
        self.frontier = FrontierService(self.store, self.event_bus)
        self.resources = ResourceManager(self.store, self.event_bus)
        self.ingest = IngestService(self.store, self.event_bus, self.object_store, self.warehouse)
        self.scheduler = SchedulerService(self.store, self.control)

    @classmethod
    def from_settings(cls) -> "PlatformRuntime":
        return cls(
            workspace=settings.workspace,
            database_url=settings.platform_database_url or None,
            event_root=settings.platform_event_dir,
            object_store_root=settings.platform_object_store_dir,
            warehouse_root=settings.platform_warehouse_dir,
        )
