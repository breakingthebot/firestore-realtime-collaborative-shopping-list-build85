"""
FastAPI REST routes for shopping list items subcollection.
Path: /shopping_lists/{list_id}/items/{item_id}
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from src.models.schema import (
    ItemCreate,
    ItemUpdate,
    ItemTogglePurchased,
    ItemResponse,
)
from src.services.shopping_service import ShoppingService

router = APIRouter(prefix="/api/lists/{list_id}/items", tags=["List Items"])
service = ShoppingService()


@router.post(
    "",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an item to the shopping list subcollection",
)
def add_item_endpoint(list_id: str, item_in: ItemCreate) -> ItemResponse:
    """
    Create a new item document at /shopping_lists/{list_id}/items/{item_id}.
    """
    try:
        return service.add_item(list_id, item_in)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get(
    "",
    response_model=List[ItemResponse],
    summary="List all items in the shopping list",
)
def list_items_endpoint(
    list_id: str,
    category: Optional[str] = Query(default=None, description="Filter by category (Produce, Dairy, etc.)"),
    is_purchased: Optional[bool] = Query(default=None, description="Filter by purchase status"),
) -> List[ItemResponse]:
    """
    Query items from subcollection with optional category and completion status filters.
    """
    return service.list_items(list_id, category=category, is_purchased=is_purchased)


@router.get(
    "/{item_id}",
    response_model=ItemResponse,
    summary="Get single item details",
)
def get_item_endpoint(list_id: str, item_id: str) -> ItemResponse:
    """
    Fetch single item from subcollection.
    """
    item = service.get_item(list_id, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item '{item_id}' not found in list '{list_id}'",
        )
    return item


@router.patch(
    "/{item_id}",
    response_model=ItemResponse,
    summary="Update item properties",
)
def update_item_endpoint(
    list_id: str,
    item_id: str,
    item_up: ItemUpdate,
) -> ItemResponse:
    """
    Update item name, category, quantity, or unit.
    """
    updated = service.update_item(list_id, item_id, item_up)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item '{item_id}' not found in list '{list_id}'",
        )
    return updated


@router.post(
    "/{item_id}/toggle",
    response_model=ItemResponse,
    summary="Toggle purchased status with user attribution",
)
def toggle_purchased_endpoint(
    list_id: str,
    item_id: str,
    toggle_in: ItemTogglePurchased,
) -> ItemResponse:
    """
    Toggle item completion status and record who checked it off.
    """
    updated = service.toggle_purchased(list_id, item_id, toggle_in)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item '{item_id}' not found in list '{list_id}'",
        )
    return updated


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an item from the list",
)
def delete_item_endpoint(
    list_id: str,
    item_id: str,
    user_id: str = Query(default="user", description="User performing the deletion"),
) -> None:
    """
    Delete item document from the subcollection.
    """
    deleted = service.delete_item(list_id, item_id, user_id=user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item '{item_id}' not found in list '{list_id}'",
        )
