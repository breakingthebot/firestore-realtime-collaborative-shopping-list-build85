"""
FastAPI REST routes for shopping lists collection.
"""

from typing import List
from fastapi import APIRouter, HTTPException, Query, status
from src.models.schema import (
    ShoppingListCreate,
    ShoppingListUpdate,
    ShoppingListResponse,
    CollaboratorInvite,
    ActivityLogResponse,
)
from src.services.shopping_service import ShoppingService

router = APIRouter(prefix="/api/lists", tags=["Shopping Lists"])
service = ShoppingService()


@router.post(
    "",
    response_model=ShoppingListResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new collaborative shopping list",
)
def create_list_endpoint(list_in: ShoppingListCreate) -> ShoppingListResponse:
    """
    Create a root document at /shopping_lists/{list_id}.
    """
    return service.create_list(list_in)


@router.get(
    "",
    response_model=List[ShoppingListResponse],
    summary="List shopping lists for a user",
)
def list_user_lists_endpoint(
    user_id: str = Query(..., description="User ID to query lists for")
) -> List[ShoppingListResponse]:
    """
    Query all lists where collaborator_ids contains user_id.
    """
    return service.list_user_lists(user_id)


@router.get(
    "/{list_id}",
    response_model=ShoppingListResponse,
    summary="Get shopping list details and live item aggregates",
)
def get_list_endpoint(list_id: str) -> ShoppingListResponse:
    """
    Retrieve single shopping list by ID.
    """
    shopping_list = service.get_list(list_id)
    if not shopping_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list '{list_id}' not found",
        )
    return shopping_list


@router.patch(
    "/{list_id}",
    response_model=ShoppingListResponse,
    summary="Update shopping list title",
)
def update_list_endpoint(list_id: str, list_up: ShoppingListUpdate) -> ShoppingListResponse:
    """
    Update list title and increment revision.
    """
    updated = service.update_list(list_id, list_up)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list '{list_id}' not found",
        )
    return updated


@router.delete(
    "/{list_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete shopping list and subcollections",
)
def delete_list_endpoint(list_id: str) -> None:
    """
    Recursively delete list document and items/activity subcollections.
    """
    deleted = service.delete_list(list_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list '{list_id}' not found",
        )


@router.post(
    "/{list_id}/collaborators",
    response_model=ShoppingListResponse,
    summary="Invite a collaborator to the shopping list",
)
def invite_collaborator_endpoint(
    list_id: str,
    invite: CollaboratorInvite,
) -> ShoppingListResponse:
    """
    Add collaborator to the list and emit snapshot update to connected listeners.
    """
    updated = service.invite_collaborator(list_id, invite)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list '{list_id}' not found",
        )
    return updated


@router.get(
    "/{list_id}/activity",
    response_model=List[ActivityLogResponse],
    summary="Get recent activity log for the list",
)
def list_activity_endpoint(
    list_id: str,
    limit: int = Query(default=50, ge=1, le=200),
) -> List[ActivityLogResponse]:
    """
    Fetch subcollection activity entries ordered reverse-chronologically.
    """
    return service.list_activity(list_id, limit=limit)
