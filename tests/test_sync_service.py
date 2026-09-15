"""
Unit tests for SyncService.
Tests offline mutation processing, replay idempotency, and conflict resolution strategies.
"""

import time
from datetime import datetime, timezone

from src.config import settings
from src.models.schema import (
    ShoppingListCreate,
    ItemCreate,
    ItemUpdate,
    OfflineMutation,
    OfflineSyncRequest,
)
from src.services.shopping_service import ShoppingService
from src.services.sync_service import SyncService


def test_offline_sync_add_mutations():
    """
    Test processing queued offline ADD mutations adds items to the list.
    """
    shopping_svc = ShoppingService()
    sync_svc = SyncService()

    l = shopping_svc.create_list(ShoppingListCreate(title="Camping Trip", owner_id="user_camp"))

    request = OfflineSyncRequest(
        client_id="device_iphone_12",
        user_id="user_camp",
        mutations=[
            OfflineMutation(
                mutation_id="m1",
                list_id=l.id,
                action="ADD",
                client_timestamp="2026-09-14T10:00:00Z",
                payload={"name": "Sleeping Bag", "category": "Gear", "quantity": 2, "unit": "pcs"},
            ),
            OfflineMutation(
                mutation_id="m2",
                list_id=l.id,
                action="ADD",
                client_timestamp="2026-09-14T10:01:00Z",
                payload={"name": "Flashlight", "category": "Gear", "quantity": 1, "unit": "pcs"},
            ),
        ],
    )

    result = sync_svc.process_offline_sync(request)
    assert result.applied_count == 2
    assert result.conflict_count == 0

    items = shopping_svc.list_items(l.id)
    assert len(items) == 2
    names = [i.name for i in items]
    assert "Sleeping Bag" in names
    assert "Flashlight" in names


def test_offline_sync_update_mutation_success():
    """
    Test processing an UPDATE mutation modifies an existing item.
    """
    shopping_svc = ShoppingService()
    sync_svc = SyncService()

    l = shopping_svc.create_list(ShoppingListCreate(title="BBQ", owner_id="griller"))
    item = shopping_svc.add_item(l.id, ItemCreate(name="Buns", quantity=1, added_by="griller"))

    # Slight pause to ensure client timestamp is strictly greater than item.updated_at
    time.sleep(0.01)
    fresh_client_timestamp = datetime.now(timezone.utc).isoformat()

    request = OfflineSyncRequest(
        client_id="device_android",
        user_id="griller",
        mutations=[
            OfflineMutation(
                mutation_id="m_up",
                list_id=l.id,
                item_id=item.id,
                action="UPDATE",
                client_timestamp=fresh_client_timestamp,
                payload={"quantity": 4, "unit": "packs"},
                expected_revision=item.revision,
            )
        ],
    )

    result = sync_svc.process_offline_sync(request)
    assert result.applied_count == 1
    assert result.conflict_count == 0

    updated_item = shopping_svc.get_item(l.id, item.id)
    assert updated_item.quantity == 4.0
    assert updated_item.unit == "packs"


def test_offline_sync_toggle_purchase_mutation():
    """
    Test queued offline TOGGLE_PURCHASE marks item as purchased upon reconnect.
    """
    shopping_svc = ShoppingService()
    sync_svc = SyncService()

    l = shopping_svc.create_list(ShoppingListCreate(title="Dinner", owner_id="chef"))
    item = shopping_svc.add_item(l.id, ItemCreate(name="Pasta", added_by="chef"))

    request = OfflineSyncRequest(
        client_id="device_tab",
        user_id="chef",
        mutations=[
            OfflineMutation(
                mutation_id="m_tog",
                list_id=l.id,
                item_id=item.id,
                action="TOGGLE_PURCHASE",
                client_timestamp="2026-09-14T12:10:00Z",
                payload={"is_purchased": True},
            )
        ],
    )

    result = sync_svc.process_offline_sync(request)
    assert result.applied_count == 1

    updated = shopping_svc.get_item(l.id, item.id)
    assert updated.is_purchased is True
    assert updated.purchased_by == "chef"


def test_offline_sync_delete_mutation():
    """
    Test queued offline DELETE mutation deletes the item from the subcollection.
    """
    shopping_svc = ShoppingService()
    sync_svc = SyncService()

    l = shopping_svc.create_list(ShoppingListCreate(title="Shop", owner_id="buyer"))
    item = shopping_svc.add_item(l.id, ItemCreate(name="Cookies", added_by="buyer"))

    request = OfflineSyncRequest(
        client_id="device_web",
        user_id="buyer",
        mutations=[
            OfflineMutation(
                mutation_id="m_del",
                list_id=l.id,
                item_id=item.id,
                action="DELETE",
                client_timestamp="2026-09-14T12:15:00Z",
            )
        ],
    )

    result = sync_svc.process_offline_sync(request)
    assert result.applied_count == 1
    assert shopping_svc.get_item(l.id, item.id) is None


def test_offline_sync_conflict_revision_check():
    """
    Test REVISION_CHECK conflict strategy rejects mutations where expected_revision is stale.
    """
    shopping_svc = ShoppingService()
    sync_svc = SyncService()

    l = shopping_svc.create_list(ShoppingListCreate(title="Revision Test", owner_id="tester"))
    item = shopping_svc.add_item(l.id, ItemCreate(name="Juice", added_by="tester"))

    # Remote server updates item first, incrementing its revision
    shopping_svc.update_item(l.id, item.id, ItemUpdate(name="Orange Juice"))
    latest_item = shopping_svc.get_item(l.id, item.id)
    assert latest_item.revision > 1

    # Temporarily set strategy to REVISION_CHECK
    original_strat = settings.SYNC_CONFLICT_STRATEGY
    settings.SYNC_CONFLICT_STRATEGY = "REVISION_CHECK"

    try:
        # Offline client sends mutation with old expected_revision = 1
        request = OfflineSyncRequest(
            client_id="device_slow",
            user_id="tester",
            mutations=[
                OfflineMutation(
                    mutation_id="m_conf",
                    list_id=l.id,
                    item_id=item.id,
                    action="UPDATE",
                    client_timestamp="2026-09-14T12:20:00Z",
                    payload={"name": "Apple Juice"},
                    expected_revision=1,  # Stale revision
                )
            ],
        )

        result = sync_svc.process_offline_sync(request)
        assert result.applied_count == 0
        assert result.conflict_count == 1
        assert result.conflicts[0]["reason"] == "REVISION_CONFLICT"

        # Item should remain Orange Juice
        assert shopping_svc.get_item(l.id, item.id).name == "Orange Juice"
    finally:
        settings.SYNC_CONFLICT_STRATEGY = original_strat


def test_offline_sync_conflict_last_write_wins_stale_timestamp():
    """
    Test LAST_WRITE_WINS rejects client mutation if client timestamp is older than remote updated_at.
    """
    shopping_svc = ShoppingService()
    sync_svc = SyncService()

    l = shopping_svc.create_list(ShoppingListCreate(title="LWW Test", owner_id="tester"))
    item = shopping_svc.add_item(l.id, ItemCreate(name="Coffee", added_by="tester"))

    original_strat = settings.SYNC_CONFLICT_STRATEGY
    settings.SYNC_CONFLICT_STRATEGY = "LAST_WRITE_WINS"

    try:
        # Client timestamp is in the past compared to item.updated_at
        request = OfflineSyncRequest(
            client_id="device_clock_drift",
            user_id="tester",
            mutations=[
                OfflineMutation(
                    mutation_id="m_stale",
                    list_id=l.id,
                    item_id=item.id,
                    action="UPDATE",
                    client_timestamp="2020-01-01T00:00:00Z",  # Very old
                    payload={"name": "Cold Brew"},
                )
            ],
        )

        result = sync_svc.process_offline_sync(request)
        assert result.conflict_count == 1
        assert result.conflicts[0]["reason"] == "STALE_TIMESTAMP_OVERWRITTEN"
        assert shopping_svc.get_item(l.id, item.id).name == "Coffee"
    finally:
        settings.SYNC_CONFLICT_STRATEGY = original_strat
