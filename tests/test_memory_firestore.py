"""
Unit tests for MemoryFirestore engine.
Tests hierarchical document storage, subcollections, queries, and snapshot listeners.
"""

from src.engine.memory_firestore import MemoryFirestore


def test_set_and_get_document():
    """
    Test setting and retrieving a document by path.
    """
    engine = MemoryFirestore()
    doc = engine.set_document("shopping_lists/list_1", {"title": "Groceries", "owner": "alice"})

    assert doc["title"] == "Groceries"
    assert doc["revision"] == 1
    assert "created_at" in doc
    assert "updated_at" in doc

    fetched = engine.get_document("shopping_lists/list_1")
    assert fetched is not None
    assert fetched["title"] == "Groceries"


def test_update_document_increments_revision():
    """
    Test updating document fields mutates state and bumps revision counter.
    """
    engine = MemoryFirestore()
    engine.set_document("shopping_lists/list_1", {"title": "Groceries", "count": 1})

    updated = engine.update_document("shopping_lists/list_1", {"title": "Updated Groceries", "count": 2})
    assert updated is not None
    assert updated["title"] == "Updated Groceries"
    assert updated["count"] == 2
    assert updated["revision"] == 2

    # Updating non-existent document returns None
    assert engine.update_document("non/existent", {"a": 1}) is None


def test_delete_document_and_cascade_subcollections():
    """
    Test deleting a document cascades and deletes all child subcollections.
    """
    engine = MemoryFirestore()
    engine.set_document("shopping_lists/list_1", {"title": "Main"})
    engine.set_document("shopping_lists/list_1/items/item_1", {"name": "Milk"})
    engine.set_document("shopping_lists/list_1/items/item_2", {"name": "Eggs"})
    engine.set_document("shopping_lists/list_2/items/item_3", {"name": "Bread"})

    assert engine.get_document("shopping_lists/list_1") is not None
    assert engine.get_document("shopping_lists/list_1/items/item_1") is not None

    deleted = engine.delete_document("shopping_lists/list_1")
    assert deleted is True

    # Main document and its items should be gone
    assert engine.get_document("shopping_lists/list_1") is None
    assert engine.get_document("shopping_lists/list_1/items/item_1") is None
    assert engine.get_document("shopping_lists/list_1/items/item_2") is None

    # Other lists remain untouched
    assert engine.get_document("shopping_lists/list_2/items/item_3") is not None


def test_list_collection_with_depth_isolation():
    """
    Test querying a collection only returns direct child documents, not grandchild documents.
    """
    engine = MemoryFirestore()
    engine.set_document("shopping_lists/list_1", {"title": "L1"})
    engine.set_document("shopping_lists/list_2", {"title": "L2"})
    engine.set_document("shopping_lists/list_1/items/item_1", {"name": "Sub item"})

    lists = engine.list_collection("shopping_lists")
    assert len(lists) == 2
    titles = [d["title"] for d in lists]
    assert "L1" in titles
    assert "L2" in titles


def test_list_collection_filters_and_ordering():
    """
    Test filtering by equality, comparison, array_contains, and sorting.
    """
    engine = MemoryFirestore()
    engine.set_document("shopping_lists/l1/items/i1", {"name": "Apples", "category": "Produce", "price": 2.5, "tags": ["fruit", "healthy"]})
    engine.set_document("shopping_lists/l1/items/i2", {"name": "Milk", "category": "Dairy", "price": 3.0, "tags": ["drink"]})
    engine.set_document("shopping_lists/l1/items/i3", {"name": "Bananas", "category": "Produce", "price": 1.2, "tags": ["fruit"]})

    # Filter equality
    produce = engine.list_collection("shopping_lists/l1/items", filters=[("category", "==", "Produce")])
    assert len(produce) == 2

    # Filter array_contains
    fruit = engine.list_collection("shopping_lists/l1/items", filters=[("tags", "array_contains", "fruit")])
    assert len(fruit) == 2

    # Filter comparison and ordering
    sorted_items = engine.list_collection("shopping_lists/l1/items", order_by_field="price", descending=True)
    assert len(sorted_items) == 3
    assert sorted_items[0]["name"] == "Milk"
    assert sorted_items[2]["name"] == "Bananas"


def test_snapshot_listener_on_document():
    """
    Test registering a listener on an individual document triggers callbacks on mutation.
    """
    engine = MemoryFirestore()
    events = []

    def callback(path, change_type, data):
        events.append((path, change_type, data["title"]))

    listener_id = engine.add_snapshot_listener("shopping_lists/l1", callback)

    engine.set_document("shopping_lists/l1", {"title": "Initial"})
    engine.update_document("shopping_lists/l1", {"title": "Updated"})
    engine.delete_document("shopping_lists/l1")

    assert len(events) == 3
    assert events[0] == ("shopping_lists/l1", "ADDED", "Initial")
    assert events[1] == ("shopping_lists/l1", "MODIFIED", "Updated")
    assert events[2] == ("shopping_lists/l1", "REMOVED", "Updated")


def test_snapshot_listener_on_collection():
    """
    Test listener on a parent collection receives events when any child document changes.
    """
    engine = MemoryFirestore()
    received = []

    def on_change(path, change_type, data):
        received.append((change_type, data["name"]))

    engine.add_snapshot_listener("shopping_lists/l1/items", on_change)

    engine.set_document("shopping_lists/l1/items/i1", {"name": "Carrots"})
    engine.set_document("shopping_lists/l1/items/i2", {"name": "Potatoes"})

    assert len(received) == 2
    assert received[0] == ("ADDED", "Carrots")
    assert received[1] == ("ADDED", "Potatoes")


def test_remove_snapshot_listener():
    """
    Test removing listener stops callback execution.
    """
    engine = MemoryFirestore()
    count = [0]

    def on_change(path, change_type, data):
        count[0] += 1

    lid = engine.add_snapshot_listener("shopping_lists/l1", on_change)
    engine.set_document("shopping_lists/l1", {"val": 1})
    assert count[0] == 1

    removed = engine.remove_snapshot_listener(lid)
    assert removed is True

    engine.set_document("shopping_lists/l1", {"val": 2})
    assert count[0] == 1


def test_stats_telemetry():
    """
    Test stats telemetry captures reads, writes, deletes, and broadcasts.
    """
    engine = MemoryFirestore()
    engine.set_document("coll/d1", {"a": 1})
    engine.get_document("coll/d1")
    engine.delete_document("coll/d1")

    stats = engine.get_stats()
    assert stats["total_writes"] == 1
    assert stats["total_reads"] == 1
    assert stats["total_deletes"] == 1
    assert stats["total_documents"] == 0


def test_truncate_clears_all_data():
    """
    Test truncate completely purges storage.
    """
    engine = MemoryFirestore()
    engine.set_document("coll/d1", {"x": 1})
    assert engine.get_stats()["total_documents"] == 1

    engine.truncate()
    assert engine.get_stats()["total_documents"] == 0
    assert engine.get_document("coll/d1") is None
