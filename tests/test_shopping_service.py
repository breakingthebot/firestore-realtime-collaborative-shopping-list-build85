"""
Unit tests for ShoppingService.
Tests Firestore collections, subcollections, collaborator access, item lifecycles, and activity logs.
"""

from src.models.schema import (
    ShoppingListCreate,
    ShoppingListUpdate,
    CollaboratorInvite,
    ItemCreate,
    ItemUpdate,
    ItemTogglePurchased,
)
from src.services.shopping_service import ShoppingService


def test_create_list_and_get():
    """
    Test creating a shopping list document and fetching it with zero initial item counts.
    """
    service = ShoppingService()
    list_in = ShoppingListCreate(title="Weekly Groceries", owner_id="user_alice")

    created = service.create_list(list_in)
    assert created.title == "Weekly Groceries"
    assert created.owner_id == "user_alice"
    assert "user_alice" in created.collaborator_ids
    assert created.item_count == 0
    assert created.completed_count == 0

    fetched = service.get_list(created.id)
    assert fetched is not None
    assert fetched.id == created.id


def test_list_user_lists_collaborator_access():
    """
    Test querying lists where the user is an owner or invited collaborator.
    """
    service = ShoppingService()
    l1 = service.create_list(ShoppingListCreate(title="Alice List", owner_id="alice"))
    l2 = service.create_list(ShoppingListCreate(title="Bob List", owner_id="bob"))

    # Bob invites Alice
    service.invite_collaborator(l2.id, CollaboratorInvite(user_id="alice"))

    alice_lists = service.list_user_lists("alice")
    assert len(alice_lists) == 2

    bob_lists = service.list_user_lists("bob")
    assert len(bob_lists) == 1


def test_update_and_delete_list():
    """
    Test renaming a list and deleting it with cascade subcollection cleanup.
    """
    service = ShoppingService()
    l = service.create_list(ShoppingListCreate(title="Old Name", owner_id="charlie"))

    updated = service.update_list(l.id, ShoppingListUpdate(title="New Name"))
    assert updated.title == "New Name"

    # Add item before delete
    service.add_item(l.id, ItemCreate(name="Butter", added_by="charlie"))

    # Delete list
    deleted = service.delete_list(l.id)
    assert deleted is True
    assert service.get_list(l.id) is None


def test_invite_collaborator_and_activity_log():
    """
    Test inviting collaborator logs activity in the activity subcollection.
    """
    service = ShoppingService()
    l = service.create_list(ShoppingListCreate(title="Party Supplies", owner_id="host_1"))

    service.invite_collaborator(l.id, CollaboratorInvite(user_id="guest_1"))
    updated = service.get_list(l.id)
    assert "guest_1" in updated.collaborator_ids

    # Check activity log
    activity = service.list_activity(l.id)
    actions = [a.action for a in activity]
    assert "COLLABORATOR_JOINED" in actions
    assert "LIST_CREATED" in actions


def test_add_item_to_subcollection_and_counter_aggregates():
    """
    Test adding items to subcollection dynamically updates list item_count.
    """
    service = ShoppingService()
    l = service.create_list(ShoppingListCreate(title="Hardware", owner_id="builder"))

    item1 = service.add_item(l.id, ItemCreate(name="Nails", category="Hardware", quantity=50, unit="pcs", added_by="builder"))
    item2 = service.add_item(l.id, ItemCreate(name="Hammer", category="Hardware", quantity=1, unit="pcs", added_by="builder"))

    assert item1.name == "Nails"
    assert item2.name == "Hammer"

    list_summary = service.get_list(l.id)
    assert list_summary.item_count == 2
    assert list_summary.completed_count == 0


def test_list_items_with_category_and_purchased_filters():
    """
    Test querying subcollection items with category and completion filters.
    """
    service = ShoppingService()
    l = service.create_list(ShoppingListCreate(title="Supermarket", owner_id="shopper"))

    i1 = service.add_item(l.id, ItemCreate(name="Spinach", category="Produce", quantity=1, added_by="shopper"))
    i2 = service.add_item(l.id, ItemCreate(name="Milk", category="Dairy", quantity=2, added_by="shopper"))
    i3 = service.add_item(l.id, ItemCreate(name="Apples", category="Produce", quantity=5, added_by="shopper"))

    service.toggle_purchased(l.id, i1.id, ItemTogglePurchased(is_purchased=True, user_id="shopper"))

    # Filter Produce
    produce_items = service.list_items(l.id, category="Produce")
    assert len(produce_items) == 2

    # Filter is_purchased=True
    purchased_items = service.list_items(l.id, is_purchased=True)
    assert len(purchased_items) == 1
    assert purchased_items[0].name == "Spinach"


def test_update_item():
    """
    Test updating item attributes in the subcollection.
    """
    service = ShoppingService()
    l = service.create_list(ShoppingListCreate(title="Market", owner_id="buyer"))
    item = service.add_item(l.id, ItemCreate(name="Bread", quantity=1, added_by="buyer"))

    updated = service.update_item(l.id, item.id, ItemUpdate(quantity=3.0, unit="loaves"))
    assert updated.quantity == 3.0
    assert updated.unit == "loaves"


def test_toggle_purchased_status_records_attribution():
    """
    Test checking an item off attributes the purchase to the user and records timestamp.
    """
    service = ShoppingService()
    l = service.create_list(ShoppingListCreate(title="Market", owner_id="buyer"))
    item = service.add_item(l.id, ItemCreate(name="Cheese", added_by="buyer"))

    # Check item off
    toggled = service.toggle_purchased(l.id, item.id, ItemTogglePurchased(is_purchased=True, user_id="shopper_99"))
    assert toggled.is_purchased is True
    assert toggled.purchased_by == "shopper_99"
    assert toggled.purchased_at is not None

    # Verify list aggregates reflect 1 completed
    list_summary = service.get_list(l.id)
    assert list_summary.completed_count == 1

    # Uncheck item
    uncheked = service.toggle_purchased(l.id, item.id, ItemTogglePurchased(is_purchased=False, user_id="shopper_99"))
    assert uncheked.is_purchased is False
    assert uncheked.purchased_by is None


def test_delete_item_decrements_counts():
    """
    Test removing an item from subcollection.
    """
    service = ShoppingService()
    l = service.create_list(ShoppingListCreate(title="Supplies", owner_id="buyer"))
    item = service.add_item(l.id, ItemCreate(name="Pen", added_by="buyer"))

    assert service.get_list(l.id).item_count == 1
    deleted = service.delete_item(l.id, item.id, user_id="buyer")
    assert deleted is True

    assert service.get_list(l.id).item_count == 0
    assert service.get_item(l.id, item.id) is None


def test_activity_log_retrieval():
    """
    Test fetching activity log subcollection entries.
    """
    service = ShoppingService()
    l = service.create_list(ShoppingListCreate(title="Camp Food", owner_id="camper"))
    item = service.add_item(l.id, ItemCreate(name="Trail Mix", added_by="camper"))
    service.toggle_purchased(l.id, item.id, ItemTogglePurchased(is_purchased=True, user_id="camper"))

    activity = service.list_activity(l.id)
    assert len(activity) >= 3
    actions = [a.action for a in activity]
    assert "ITEM_PURCHASED" in actions
    assert "ITEM_ADDED" in actions
