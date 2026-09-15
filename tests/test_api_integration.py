"""
End-to-end HTTP and WebSocket API integration tests for Build 85.
"""


def test_root_discovery_endpoint(client):
    """
    Test root discovery endpoint returns Firestore hierarchical schema and telemetry.
    """
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["service"] == "Build 85: Real-Time Collaborative Shopping List"
    assert data["technology"] == "Google Cloud Firestore & FastAPI"
    assert "collections_schema" in data
    assert "realtime_listeners" in data


def test_shopping_list_api_crud(client):
    """
    Test creating, reading, updating, and deleting a shopping list via REST API.
    """
    # Create list
    create_res = client.post(
        "/api/lists",
        json={"title": "Weekend Feast", "owner_id": "chef_mario"},
    )
    assert create_res.status_code == 201
    l = create_res.json()
    list_id = l["id"]
    assert l["title"] == "Weekend Feast"
    assert "chef_mario" in l["collaborator_ids"]

    # Get list
    get_res = client.get(f"/api/lists/{list_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == list_id

    # List user lists
    user_lists = client.get("/api/lists?user_id=chef_mario").json()
    assert len(user_lists) == 1

    # Update list title
    patch_res = client.patch(f"/api/lists/{list_id}", json={"title": "Sunday Dinner"})
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == "Sunday Dinner"

    # Delete list
    del_res = client.delete(f"/api/lists/{list_id}")
    assert del_res.status_code == 204

    # Confirm 404
    assert client.get(f"/api/lists/{list_id}").status_code == 404


def test_collaborator_invite_api(client):
    """
    Test inviting collaborator via API.
    """
    create_res = client.post("/api/lists", json={"title": "Team Pantry", "owner_id": "lead"})
    list_id = create_res.json()["id"]

    invite_res = client.post(
        f"/api/lists/{list_id}/collaborators",
        json={"user_id": "intern"},
    )
    assert invite_res.status_code == 200
    assert "intern" in invite_res.json()["collaborator_ids"]


def test_items_api_crud(client):
    """
    Test adding, getting, updating, and deleting items in subcollection.
    """
    l_res = client.post("/api/lists", json={"title": "Grocery Run", "owner_id": "shopper1"})
    list_id = l_res.json()["id"]

    # Add item
    add_res = client.post(
        f"/api/lists/{list_id}/items",
        json={"name": "Avocados", "category": "Produce", "quantity": 4, "unit": "pcs", "added_by": "shopper1"},
    )
    assert add_res.status_code == 201
    item = add_res.json()
    item_id = item["id"]
    assert item["name"] == "Avocados"
    assert item["is_purchased"] is False

    # Get item
    get_item = client.get(f"/api/lists/{list_id}/items/{item_id}")
    assert get_item.status_code == 200
    assert get_item.json()["name"] == "Avocados"

    # Update item
    patch_item = client.patch(
        f"/api/lists/{list_id}/items/{item_id}",
        json={"quantity": 6.0},
    )
    assert patch_item.status_code == 200
    assert patch_item.json()["quantity"] == 6.0

    # Delete item
    del_item = client.delete(f"/api/lists/{list_id}/items/{item_id}")
    assert del_item.status_code == 204
    assert client.get(f"/api/lists/{list_id}/items/{item_id}").status_code == 404


def test_items_api_toggle_purchased(client):
    """
    Test checking off an item via API with user attribution.
    """
    l_res = client.post("/api/lists", json={"title": "Party", "owner_id": "host"})
    list_id = l_res.json()["id"]

    add_res = client.post(
        f"/api/lists/{list_id}/items",
        json={"name": "Soda", "category": "Beverages", "quantity": 2, "added_by": "host"},
    )
    item_id = add_res.json()["id"]

    toggle_res = client.post(
        f"/api/lists/{list_id}/items/{item_id}/toggle",
        json={"is_purchased": True, "user_id": "guest_bob"},
    )
    assert toggle_res.status_code == 200
    toggled = toggle_res.json()
    assert toggled["is_purchased"] is True
    assert toggled["purchased_by"] == "guest_bob"
    assert toggled["purchased_at"] is not None

    # Check list summary aggregates
    list_summary = client.get(f"/api/lists/{list_id}").json()
    assert list_summary["completed_count"] == 1


def test_items_api_filtering(client):
    """
    Test filtering items by category and purchased state.
    """
    l_res = client.post("/api/lists", json={"title": "Market", "owner_id": "buyer"})
    list_id = l_res.json()["id"]

    client.post(f"/api/lists/{list_id}/items", json={"name": "Kale", "category": "Produce", "added_by": "buyer"})
    client.post(f"/api/lists/{list_id}/items", json={"name": "Steak", "category": "Meat", "added_by": "buyer"})

    # Filter produce
    items = client.get(f"/api/lists/{list_id}/items?category=Produce").json()
    assert len(items) == 1
    assert items[0]["name"] == "Kale"


def test_activity_api_endpoint(client):
    """
    Test retrieving activity log entries for a shopping list.
    """
    l_res = client.post("/api/lists", json={"title": "Camp Food", "owner_id": "camper"})
    list_id = l_res.json()["id"]
    client.post(f"/api/lists/{list_id}/items", json={"name": "Granola", "added_by": "camper"})

    act_res = client.get(f"/api/lists/{list_id}/activity")
    assert act_res.status_code == 200
    entries = act_res.json()
    assert len(entries) >= 2


def test_offline_sync_api_endpoint(client):
    """
    Test submitting an offline mutation batch via the sync endpoint.
    """
    l_res = client.post("/api/lists", json={"title": "Offline Test", "owner_id": "commuter"})
    list_id = l_res.json()["id"]

    sync_payload = {
        "client_id": "subway_phone",
        "user_id": "commuter",
        "mutations": [
            {
                "mutation_id": "mut_1",
                "list_id": list_id,
                "action": "ADD",
                "client_timestamp": "2026-09-14T15:00:00Z",
                "payload": {"name": "Subway Sandwich", "category": "Deli", "quantity": 1},
            }
        ],
    }

    res = client.post("/api/sync/offline-batch", json=sync_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["applied_count"] == 1
    assert data["conflict_count"] == 0

    # Verify item was added to the list
    items = client.get(f"/api/lists/{list_id}/items").json()
    assert len(items) == 1
    assert items[0]["name"] == "Subway Sandwich"


def test_sync_status_api_endpoint(client):
    """
    Test inspecting offline sync status and strategy.
    """
    res = client.get("/api/sync/status")
    assert res.status_code == 200
    assert "conflict_strategy" in res.json()
    assert res.json()["offline_support_enabled"] is True


def test_system_health_and_stats(client):
    """
    Test system health check and telemetry stats.
    """
    health = client.get("/api/system/health")
    assert health.status_code == 200
    assert health.json()["status"] == "HEALTHY"

    stats = client.get("/api/system/stats")
    assert stats.status_code == 200
    assert "total_documents" in stats.json()
    assert "total_writes" in stats.json()


def test_system_reset_api(client):
    """
    Test system reset endpoint clears all data.
    """
    client.post("/api/lists", json={"title": "To be wiped", "owner_id": "test"})
    assert client.get("/api/system/stats").json()["total_documents"] >= 1

    reset_res = client.post("/api/system/reset")
    assert reset_res.status_code == 200

    assert client.get("/api/system/stats").json()["total_documents"] == 0


def test_validation_error_422(client):
    """
    Test invalid payload triggers HTTP 422 Unprocessable Entity.
    """
    res = client.post("/api/lists", json={"missing_title": True})
    assert res.status_code == 422


def test_websocket_realtime_snapshot_listener(client):
    """
    Test connecting to WebSocket snapshot listener receives initial snapshot
    and live push updates when an item is added.
    """
    l_res = client.post("/api/lists", json={"title": "Live List", "owner_id": "streamer"})
    list_id = l_res.json()["id"]

    # Connect WebSocket client
    with client.websocket_connect(f"/api/ws/lists/{list_id}") as websocket:
        # 1. First frame received should be SNAPSHOT_INIT
        init_msg = websocket.receive_json()
        assert init_msg["event"] == "SNAPSHOT_INIT"
        assert init_msg["list"]["id"] == list_id
        assert len(init_msg["items"]) == 0

        # 2. Add an item through REST API while WebSocket is connected
        client.post(
            f"/api/lists/{list_id}/items",
            json={"name": "Realtime Bananas", "category": "Produce", "quantity": 6, "added_by": "streamer"},
        )

        # 3. WebSocket should receive SNAPSHOT_UPDATE frame immediately
        update_msg = websocket.receive_json()
        assert update_msg["event"] == "SNAPSHOT_UPDATE"
        assert update_msg["change_type"] == "ADDED"
        assert update_msg["data"]["name"] == "Realtime Bananas"

        # 4. Ping-pong test
        websocket.send_text("ping")
        pong_msg = websocket.receive_json()
        assert pong_msg["event"] == "pong"
