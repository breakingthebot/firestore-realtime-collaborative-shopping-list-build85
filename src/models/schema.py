"""
Pydantic data schemas for Firestore Shopping List and real-time offline sync.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ShoppingListCreate(BaseModel):
    """
    Schema for creating a new shared shopping list.
    """

    title: str = Field(..., min_length=1, max_length=120, description="List title")
    owner_id: str = Field(..., min_length=1, max_length=64, description="User ID of the list creator")


class ShoppingListUpdate(BaseModel):
    """
    Schema for updating shopping list title or metadata.
    """

    title: Optional[str] = Field(default=None, min_length=1, max_length=120)


class CollaboratorInvite(BaseModel):
    """
    Schema for adding a collaborator to a shopping list.
    """

    user_id: str = Field(..., min_length=1, max_length=64, description="Collaborator user ID to invite")


class ShoppingListResponse(BaseModel):
    """
    Public response schema for a shopping list document.
    """

    id: str
    title: str
    owner_id: str
    collaborator_ids: List[str]
    created_at: str
    updated_at: str
    revision: int
    item_count: int = 0
    completed_count: int = 0


class ItemCreate(BaseModel):
    """
    Schema for creating an item inside a shopping list subcollection.
    """

    name: str = Field(..., min_length=1, max_length=120, description="Item name (e.g. Organic Apples)")
    category: str = Field(default="Produce", description="Category: Produce, Dairy, Bakery, Meat, Pantry, Household")
    quantity: float = Field(default=1.0, gt=0.0, description="Item quantity")
    unit: str = Field(default="pcs", description="Measurement unit (e.g. pcs, kg, lbs, pack)")
    added_by: str = Field(..., min_length=1, max_length=64, description="User who added the item")


class ItemUpdate(BaseModel):
    """
    Schema for updating item name, category, or quantity.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    category: Optional[str] = Field(default=None)
    quantity: Optional[float] = Field(default=None, gt=0.0)
    unit: Optional[str] = Field(default=None)


class ItemTogglePurchased(BaseModel):
    """
    Schema for checking off or unchecking an item.
    """

    is_purchased: bool
    user_id: str = Field(..., min_length=1, max_length=64, description="User performing the toggle")


class ItemResponse(BaseModel):
    """
    Public response schema for an item subcollection document.
    """

    id: str
    list_id: str
    name: str
    category: str
    quantity: float
    unit: str
    is_purchased: bool
    purchased_by: Optional[str] = None
    purchased_at: Optional[str] = None
    added_by: str
    created_at: str
    updated_at: str
    revision: int


class OfflineMutation(BaseModel):
    """
    Represents a client mutation queued during offline mode.
    """

    mutation_id: str
    list_id: str
    item_id: Optional[str] = None
    action: str = Field(..., description="Action: ADD, UPDATE, TOGGLE_PURCHASE, DELETE")
    client_timestamp: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    expected_revision: Optional[int] = None


class OfflineSyncRequest(BaseModel):
    """
    Payload for batch synchronizing queued offline mutations.
    """

    client_id: str
    user_id: str
    mutations: List[OfflineMutation]


class SyncResult(BaseModel):
    """
    Report returned after resolving offline sync batch.
    """

    client_id: str
    applied_count: int
    conflict_count: int
    conflicts: List[Dict[str, Any]]
    sync_timestamp: str


class ActivityLogResponse(BaseModel):
    """
    Audit log record stored in the list's activity subcollection.
    """

    id: str
    list_id: str
    action: str
    user_id: str
    description: str
    timestamp: str


class FirestoreStatsResponse(BaseModel):
    """
    Telemetry and engine metrics.
    """

    total_documents: int
    active_listeners: int
    total_reads: int
    total_writes: int
    total_deletes: int
    total_broadcasts: int
