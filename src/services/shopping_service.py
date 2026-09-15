"""
Shopping List domain service.
Manages Firestore collections, subcollections, item life cycles, and activity logs.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from src.config import settings
from src.engine.firestore_client import get_firestore_engine
from src.models.schema import (
    ShoppingListCreate,
    ShoppingListUpdate,
    ShoppingListResponse,
    CollaboratorInvite,
    ItemCreate,
    ItemUpdate,
    ItemTogglePurchased,
    ItemResponse,
    ActivityLogResponse,
)


class ShoppingService:
    """
    Handles Firestore operations for shared shopping lists and subcollections.
    """

    def __init__(self) -> None:
        """
        Initialize service with active Firestore engine.
        """
        self.engine = get_firestore_engine()

    def _now_iso(self) -> str:
        """
        Current UTC timestamp in ISO 8601 string format.
        """
        return datetime.now(timezone.utc).isoformat()

    # =========================================================================
    # SHOPPING LISTS COLLECTION
    # =========================================================================

    def create_list(self, list_in: ShoppingListCreate) -> ShoppingListResponse:
        """
        Create a new shopping list document in the 'shopping_lists' collection.
        Path: /shopping_lists/{list_id}
        """
        list_id = f"list_{uuid.uuid4().hex[:12]}"
        path = f"{settings.COLLECTION_LISTS}/{list_id}"
        now = self._now_iso()

        doc_data = {
            "id": list_id,
            "title": list_in.title,
            "owner_id": list_in.owner_id,
            "collaborator_ids": [list_in.owner_id],
            "created_at": now,
            "updated_at": now,
            "revision": 1,
        }

        stored = self.engine.set_document(path, doc_data)
        self.log_activity(list_id, "LIST_CREATED", list_in.owner_id, f"Created shopping list '{list_in.title}'")

        return ShoppingListResponse(
            id=stored["id"],
            title=stored["title"],
            owner_id=stored["owner_id"],
            collaborator_ids=stored["collaborator_ids"],
            created_at=stored["created_at"],
            updated_at=stored["updated_at"],
            revision=stored["revision"],
            item_count=0,
            completed_count=0,
        )

    def get_list(self, list_id: str) -> Optional[ShoppingListResponse]:
        """
        Fetch shopping list document and compute item aggregate counts.
        """
        path = f"{settings.COLLECTION_LISTS}/{list_id}"
        doc = self.engine.get_document(path)
        if not doc:
            return None

        # Fetch subcollection items to compute live counts
        items_path = f"{settings.COLLECTION_LISTS}/{list_id}/{settings.SUBCOLLECTION_ITEMS}"
        items = self.engine.list_collection(items_path)
        item_count = len(items)
        completed_count = sum(1 for it in items if it.get("is_purchased") is True)

        return ShoppingListResponse(
            id=doc["id"],
            title=doc["title"],
            owner_id=doc["owner_id"],
            collaborator_ids=doc.get("collaborator_ids", []),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
            revision=doc.get("revision", 1),
            item_count=item_count,
            completed_count=completed_count,
        )

    def list_user_lists(self, user_id: str) -> List[ShoppingListResponse]:
        """
        Query all shopping lists where the user is an owner or collaborator.
        """
        all_lists = self.engine.list_collection(
            settings.COLLECTION_LISTS,
            filters=[("collaborator_ids", "array_contains", user_id)],
            order_by_field="updated_at",
            descending=True,
        )

        results: List[ShoppingListResponse] = []
        for doc in all_lists:
            list_id = doc["id"]
            items_path = f"{settings.COLLECTION_LISTS}/{list_id}/{settings.SUBCOLLECTION_ITEMS}"
            items = self.engine.list_collection(items_path)
            item_count = len(items)
            completed_count = sum(1 for it in items if it.get("is_purchased") is True)

            results.append(
                ShoppingListResponse(
                    id=doc["id"],
                    title=doc["title"],
                    owner_id=doc["owner_id"],
                    collaborator_ids=doc.get("collaborator_ids", []),
                    created_at=doc["created_at"],
                    updated_at=doc["updated_at"],
                    revision=doc.get("revision", 1),
                    item_count=item_count,
                    completed_count=completed_count,
                )
            )

        return results

    def update_list(
        self,
        list_id: str,
        list_up: ShoppingListUpdate,
    ) -> Optional[ShoppingListResponse]:
        """
        Update shopping list document attributes.
        """
        path = f"{settings.COLLECTION_LISTS}/{list_id}"
        updates: Dict[str, Any] = {}
        if list_up.title is not None:
            updates["title"] = list_up.title

        updated = self.engine.update_document(path, updates)
        if not updated:
            return None

        return self.get_list(list_id)

    def delete_list(self, list_id: str) -> bool:
        """
        Delete a shopping list document and all subcollections recursively.
        """
        path = f"{settings.COLLECTION_LISTS}/{list_id}"
        return self.engine.delete_document(path)

    def invite_collaborator(
        self,
        list_id: str,
        invite: CollaboratorInvite,
    ) -> Optional[ShoppingListResponse]:
        """
        Add a collaborator user ID to the list document.
        """
        path = f"{settings.COLLECTION_LISTS}/{list_id}"
        doc = self.engine.get_document(path)
        if not doc:
            return None

        collaborators = list(doc.get("collaborator_ids", []))
        if invite.user_id not in collaborators:
            collaborators.append(invite.user_id)
            self.engine.update_document(path, {"collaborator_ids": collaborators})
            self.log_activity(
                list_id,
                "COLLABORATOR_JOINED",
                invite.user_id,
                f"User '{invite.user_id}' joined as collaborator",
            )

        return self.get_list(list_id)

    # =========================================================================
    # ITEMS SUBCOLLECTION
    # =========================================================================

    def add_item(self, list_id: str, item_in: ItemCreate) -> ItemResponse:
        """
        Add an item document to a list's items subcollection.
        Path: /shopping_lists/{list_id}/items/{item_id}
        """
        list_doc = self.engine.get_document(f"{settings.COLLECTION_LISTS}/{list_id}")
        if not list_doc:
            raise ValueError(f"Shopping list '{list_id}' not found")

        item_id = f"item_{uuid.uuid4().hex[:12]}"
        item_path = f"{settings.COLLECTION_LISTS}/{list_id}/{settings.SUBCOLLECTION_ITEMS}/{item_id}"
        now = self._now_iso()

        item_data = {
            "id": item_id,
            "list_id": list_id,
            "name": item_in.name,
            "category": item_in.category,
            "quantity": float(item_in.quantity),
            "unit": item_in.unit,
            "is_purchased": False,
            "purchased_by": None,
            "purchased_at": None,
            "added_by": item_in.added_by,
            "created_at": now,
            "updated_at": now,
            "revision": 1,
        }

        stored = self.engine.set_document(item_path, item_data)

        # Update parent list updated_at
        self.engine.update_document(f"{settings.COLLECTION_LISTS}/{list_id}", {"updated_at": now})
        self.log_activity(
            list_id,
            "ITEM_ADDED",
            item_in.added_by,
            f"Added {item_in.quantity} {item_in.unit} of '{item_in.name}'",
        )

        return ItemResponse(**stored)

    def get_item(self, list_id: str, item_id: str) -> Optional[ItemResponse]:
        """
        Fetch single item from subcollection.
        """
        path = f"{settings.COLLECTION_LISTS}/{list_id}/{settings.SUBCOLLECTION_ITEMS}/{item_id}"
        doc = self.engine.get_document(path)
        if not doc:
            return None
        return ItemResponse(**doc)

    def list_items(
        self,
        list_id: str,
        category: Optional[str] = None,
        is_purchased: Optional[bool] = None,
    ) -> List[ItemResponse]:
        """
        Query items in the list's subcollection with optional category and status filtering.
        """
        subcoll_path = f"{settings.COLLECTION_LISTS}/{list_id}/{settings.SUBCOLLECTION_ITEMS}"
        filters: List[Any] = []
        if category:
            filters.append(("category", "==", category))
        if is_purchased is not None:
            filters.append(("is_purchased", "==", is_purchased))

        docs = self.engine.list_collection(
            subcoll_path,
            filters=filters,
            order_by_field="created_at",
            descending=False,
        )

        return [ItemResponse(**d) for d in docs]

    def update_item(
        self,
        list_id: str,
        item_id: str,
        item_up: ItemUpdate,
    ) -> Optional[ItemResponse]:
        """
        Update item properties (name, category, quantity, unit).
        """
        path = f"{settings.COLLECTION_LISTS}/{list_id}/{settings.SUBCOLLECTION_ITEMS}/{item_id}"
        updates: Dict[str, Any] = {}

        if item_up.name is not None:
            updates["name"] = item_up.name
        if item_up.category is not None:
            updates["category"] = item_up.category
        if item_up.quantity is not None:
            updates["quantity"] = float(item_up.quantity)
        if item_up.unit is not None:
            updates["unit"] = item_up.unit

        updated = self.engine.update_document(path, updates)
        if not updated:
            return None

        # Touch parent list timestamp
        self.engine.update_document(f"{settings.COLLECTION_LISTS}/{list_id}", {"updated_at": self._now_iso()})
        return ItemResponse(**updated)

    def toggle_purchased(
        self,
        list_id: str,
        item_id: str,
        toggle_in: ItemTogglePurchased,
    ) -> Optional[ItemResponse]:
        """
        Toggle item purchased status with user attribution and timestamp.
        """
        path = f"{settings.COLLECTION_LISTS}/{list_id}/{settings.SUBCOLLECTION_ITEMS}/{item_id}"
        existing = self.engine.get_document(path)
        if not existing:
            return None

        now = self._now_iso()
        updates = {
            "is_purchased": toggle_in.is_purchased,
            "purchased_by": toggle_in.user_id if toggle_in.is_purchased else None,
            "purchased_at": now if toggle_in.is_purchased else None,
        }

        updated = self.engine.update_document(path, updates)
        if not updated:
            return None

        action = "ITEM_PURCHASED" if toggle_in.is_purchased else "ITEM_UNPURCHASED"
        desc = (
            f"Marked '{existing.get('name')}' as purchased"
            if toggle_in.is_purchased
            else f"Unchecked '{existing.get('name')}'"
        )
        self.log_activity(list_id, action, toggle_in.user_id, desc)
        self.engine.update_document(f"{settings.COLLECTION_LISTS}/{list_id}", {"updated_at": now})

        return ItemResponse(**updated)

    def delete_item(self, list_id: str, item_id: str, user_id: str = "system") -> bool:
        """
        Delete an item document from the subcollection.
        """
        path = f"{settings.COLLECTION_LISTS}/{list_id}/{settings.SUBCOLLECTION_ITEMS}/{item_id}"
        existing = self.engine.get_document(path)
        if not existing:
            return False

        deleted = self.engine.delete_document(path)
        if deleted:
            self.log_activity(
                list_id,
                "ITEM_DELETED",
                user_id,
                f"Removed '{existing.get('name')}' from list",
            )
            self.engine.update_document(f"{settings.COLLECTION_LISTS}/{list_id}", {"updated_at": self._now_iso()})
            return True
        return False

    # =========================================================================
    # ACTIVITY SUBCOLLECTION
    # =========================================================================

    def log_activity(
        self,
        list_id: str,
        action: str,
        user_id: str,
        description: str,
    ) -> None:
        """
        Append an audit log record into the list's activity subcollection.
        Path: /shopping_lists/{list_id}/activity/{activity_id}
        """
        activity_id = f"act_{uuid.uuid4().hex[:12]}"
        path = f"{settings.COLLECTION_LISTS}/{list_id}/{settings.SUBCOLLECTION_ACTIVITY}/{activity_id}"
        now = self._now_iso()

        activity_data = {
            "id": activity_id,
            "list_id": list_id,
            "action": action,
            "user_id": user_id,
            "description": description,
            "timestamp": now,
        }

        self.engine.set_document(path, activity_data)

    def list_activity(self, list_id: str, limit: int = 50) -> List[ActivityLogResponse]:
        """
        Query activity log subcollection ordered reverse-chronologically.
        """
        subcoll_path = f"{settings.COLLECTION_LISTS}/{list_id}/{settings.SUBCOLLECTION_ACTIVITY}"
        docs = self.engine.list_collection(
            subcoll_path,
            order_by_field="timestamp",
            descending=True,
            limit=limit,
        )
        return [ActivityLogResponse(**d) for d in docs]
