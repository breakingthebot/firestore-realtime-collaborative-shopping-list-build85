"""
Offline Synchronization and Conflict Resolution Service.
Processes queued offline mutations with Last-Write-Wins and Optimistic Revision checking.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any

from src.config import settings
from src.engine.firestore_client import get_firestore_engine
from src.models.schema import (
    OfflineSyncRequest,
    SyncResult,
    ItemCreate,
    ItemUpdate,
    ItemTogglePurchased,
)
from src.services.shopping_service import ShoppingService


class SyncService:
    """
    Orchestrates batch ingestion of offline mutations and multi-user conflict resolution.
    """

    def __init__(self) -> None:
        """
        Initialize sync service with shopping service and engine.
        """
        self.engine = get_firestore_engine()
        self.shopping_service = ShoppingService()

    def _now_iso(self) -> str:
        """
        Current UTC timestamp in ISO 8601 string format.
        """
        return datetime.now(timezone.utc).isoformat()

    def process_offline_sync(self, request: OfflineSyncRequest) -> SyncResult:
        """
        Process an array of queued offline mutations.
        Evaluates revision conflicts and timestamp precedence according to configured strategy.
        """
        applied_count = 0
        conflicts: List[Dict[str, Any]] = []
        sync_timestamp = self._now_iso()

        for mutation in request.mutations:
            action = mutation.action.upper()
            list_id = mutation.list_id
            item_id = mutation.item_id
            payload = mutation.payload

            try:
                if action == "ADD":
                    item_create = ItemCreate(
                        name=payload.get("name", "Unnamed Item"),
                        category=payload.get("category", "Produce"),
                        quantity=float(payload.get("quantity", 1.0)),
                        unit=payload.get("unit", "pcs"),
                        added_by=request.user_id,
                    )
                    self.shopping_service.add_item(list_id, item_create)
                    applied_count += 1

                elif action == "UPDATE":
                    if not item_id:
                        conflicts.append({
                            "mutation_id": mutation.mutation_id,
                            "error": "Missing item_id for UPDATE mutation",
                        })
                        continue

                    current_item = self.shopping_service.get_item(list_id, item_id)
                    if not current_item:
                        conflicts.append({
                            "mutation_id": mutation.mutation_id,
                            "error": f"Item '{item_id}' no longer exists",
                        })
                        continue

                    # Optimistic Revision Check strategy
                    if settings.SYNC_CONFLICT_STRATEGY == "REVISION_CHECK":
                        if (
                            mutation.expected_revision is not None
                            and current_item.revision > mutation.expected_revision
                        ):
                            conflicts.append({
                                "mutation_id": mutation.mutation_id,
                                "action": action,
                                "reason": "REVISION_CONFLICT",
                                "current_revision": current_item.revision,
                                "expected_revision": mutation.expected_revision,
                            })
                            continue

                    # Last Write Wins timestamp check
                    if settings.SYNC_CONFLICT_STRATEGY == "LAST_WRITE_WINS":
                        if mutation.client_timestamp < current_item.updated_at:
                            conflicts.append({
                                "mutation_id": mutation.mutation_id,
                                "action": action,
                                "reason": "STALE_TIMESTAMP_OVERWRITTEN",
                                "remote_updated_at": current_item.updated_at,
                                "client_timestamp": mutation.client_timestamp,
                            })
                            continue

                    item_up = ItemUpdate(
                        name=payload.get("name"),
                        category=payload.get("category"),
                        quantity=float(payload["quantity"]) if "quantity" in payload else None,
                        unit=payload.get("unit"),
                    )
                    self.shopping_service.update_item(list_id, item_id, item_up)
                    applied_count += 1

                elif action == "TOGGLE_PURCHASE":
                    if not item_id:
                        conflicts.append({
                            "mutation_id": mutation.mutation_id,
                            "error": "Missing item_id for TOGGLE_PURCHASE",
                        })
                        continue

                    toggle_in = ItemTogglePurchased(
                        is_purchased=bool(payload.get("is_purchased", True)),
                        user_id=request.user_id,
                    )
                    res = self.shopping_service.toggle_purchased(list_id, item_id, toggle_in)
                    if res:
                        applied_count += 1
                    else:
                        conflicts.append({
                            "mutation_id": mutation.mutation_id,
                            "error": f"Item '{item_id}' not found for purchase toggle",
                        })

                elif action == "DELETE":
                    if not item_id:
                        conflicts.append({
                            "mutation_id": mutation.mutation_id,
                            "error": "Missing item_id for DELETE",
                        })
                        continue

                    deleted = self.shopping_service.delete_item(list_id, item_id, user_id=request.user_id)
                    if deleted:
                        applied_count += 1
                    else:
                        conflicts.append({
                            "mutation_id": mutation.mutation_id,
                            "error": f"Item '{item_id}' was already deleted",
                        })

                else:
                    conflicts.append({
                        "mutation_id": mutation.mutation_id,
                        "error": f"Unknown mutation action '{action}'",
                    })

            except Exception as ex:
                conflicts.append({
                    "mutation_id": mutation.mutation_id,
                    "error": str(ex),
                })

        # Log collaborative sync event in activity log
        if applied_count > 0:
            self.shopping_service.log_activity(
                request.mutations[0].list_id if request.mutations else "unknown",
                "OFFLINE_SYNC_COMPLETED",
                request.user_id,
                f"Client '{request.client_id}' synced {applied_count} mutations with {len(conflicts)} conflicts",
            )

        return SyncResult(
            client_id=request.client_id,
            applied_count=applied_count,
            conflict_count=len(conflicts),
            conflicts=conflicts,
            sync_timestamp=sync_timestamp,
        )
