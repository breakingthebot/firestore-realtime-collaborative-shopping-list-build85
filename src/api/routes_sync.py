"""
FastAPI REST routes for offline mutation synchronization and conflict resolution.
"""

from typing import Dict, Any
from fastapi import APIRouter, status
from src.config import settings
from src.models.schema import OfflineSyncRequest, SyncResult
from src.services.sync_service import SyncService

router = APIRouter(prefix="/api/sync", tags=["Offline Synchronization"])
sync_service = SyncService()


@router.post(
    "/offline-batch",
    response_model=SyncResult,
    status_code=status.HTTP_200_OK,
    summary="Batch sync queued offline mutations with conflict resolution",
)
def sync_offline_mutations_endpoint(request: OfflineSyncRequest) -> SyncResult:
    """
    Ingest an array of offline mutations, applying changes and resolving conflicts
    via the configured strategy (LAST_WRITE_WINS or REVISION_CHECK).
    """
    return sync_service.process_offline_sync(request)


@router.get(
    "/status",
    response_model=Dict[str, Any],
    summary="Check offline sync configuration and conflict strategy",
)
def get_sync_status_endpoint() -> Dict[str, Any]:
    """
    Returns current synchronization conflict strategy and settings.
    """
    return {
        "conflict_strategy": settings.SYNC_CONFLICT_STRATEGY,
        "offline_support_enabled": True,
        "supported_actions": ["ADD", "UPDATE", "TOGGLE_PURCHASE", "DELETE"],
    }
