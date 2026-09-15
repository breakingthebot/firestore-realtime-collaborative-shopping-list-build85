# Build 85 — Firestore Real-Time Collaborative Shopping List

> **Tier**: Intermediate | **Category**: Databases - NoSQL | **Technology**: Google Cloud Firestore & FastAPI

A production-grade, real-time collaborative shopping list service demonstrating Google Cloud Firestore's **hierarchical document database architecture**. Leverages root collections and subcollections (`/shopping_lists/{list_id}/items/{item_id}` and `/shopping_lists/{list_id}/activity/{activity_id}`), live snapshot listeners with WebSocket broadcasting, multi-user offline mutation batch ingestion, and dual conflict resolution strategies (**Last-Write-Wins** and **Optimistic Revision Checking**).

---

## 1. Firestore Hierarchical Subcollection Architecture

In Google Cloud Firestore, documents and collections alternate in a strict hierarchical tree. Rather than denormalizing items into embedded arrays (which hit Firestore's 1 MB document size limit and cause write contention) or flat root tables (which lack hierarchical security isolation), shopping list items and activity logs are organized into dedicated **subcollections**:

```
/shopping_lists (Root Collection)
  └── {list_id} (Shopping List Document)
        ├── title, owner_id, collaborator_ids, revision, item_count, completed_count
        ├── /items (Subcollection)
        │     └── {item_id} (Item Document)
        │           ├── name, category, quantity, unit, is_purchased, revision
        │           └── purchased_by, purchased_at, added_by, updated_at
        └── /activity (Subcollection)
              └── {activity_id} (Audit Log Document)
                    ├── action, user_id, description, timestamp
```

### Key Architectural Advantages
1. **Zero Write Contention on Document Updates**: Adding, updating, or checking off an item mutates only that specific item document in the `/items` subcollection, completely avoiding Firestore's 1 write/sec per document limit on the parent list.
2. **Subcollection Query Isolation**: Clients can stream real-time updates for a single list's items without scanning or subscribing to other users' shopping lists.
3. **Atomic Aggregation Counters**: List-level metadata tracks `item_count` and `completed_count` updated atomically during subcollection item state transitions.
4. **Audit Trail Subcollection**: Every list operation automatically appends an immutable record to `/activity` for collaborative transparency.

---

## 2. Real-Time Snapshot Listeners & WebSocket Broadcasting

Firestore provides native real-time listeners (`on_snapshot`) that push updates as soon as document trees change. This project implements full real-time collaboration:

- **Initial State Snapshot**: Upon connecting to `/api/ws/lists/{list_id}`, clients instantly receive a `SNAPSHOT_FULL` message containing the list document and all current active items.
- **Incremental Change Deltas**: Whenever any user adds, updates, checks off, or deletes an item via REST API or offline sync, an incremental delta event (`ITEM_ADDED`, `ITEM_UPDATED`, `ITEM_PURCHASED`, `ITEM_DELETED`) is broadcast in sub-millisecond time to all connected WebSocket subscribers.
- **Keep-Alive Heartbeats**: Periodic server-side ping frames prevent proxy timeouts on mobile and edge connections.

---

## 3. Multi-User Offline Sync & Conflict Resolution

Mobile and edge clients frequently encounter network loss while shopping in stores. The service provides an `/api/sync/offline-batch` endpoint supporting queued offline mutations:

```
+-------------------+      Queue Mutations       +-----------------------------+
|  Mobile Client    | -------------------------> |   Offline Batch Ingestion   |
|  (Store/Basement) |                            |   /api/sync/offline-batch   |
+-------------------+                            +-----------------------------+
                                                                |
                                             +------------------+------------------+
                                             |                                     |
                                   [LAST_WRITE_WINS]                       [REVISION_CHECK]
                                             |                                     |
                                  Evaluates client timestamp              Validates client expected
                                  vs server updated_at.                   revision against live
                                  Accepts newer; rejects stale.           document revision number.
```

1. **Last-Write-Wins (LWW)**: Evaluates ISO-8601 timestamps. If a client's mutation timestamp is older than the server's `updated_at`, the write is safely rejected as `STALE_TIMESTAMP_OVERWRITTEN`.
2. **Optimistic Revision Check**: Each document maintains an integer `revision`. If the incoming mutation's `expected_revision` is lower than the server's current revision, a `REVISION_CONFLICT` is generated.
3. **Batch Atomicity & Reporting**: Returns a comprehensive `SyncResult` detailing `applied_count`, `conflict_count`, and granular conflict reasons for client reconciliation.

---

## 4. Data Handling & Security Posture

- **Data Privacy**: No private customer credentials, payment information, or unnecessary PII are logged or stored.
- **Access Isolation**: Lists enforce access validation ensuring only the list owner or registered collaborators can view, modify, or sync list documents.
- **Environment Isolation**: GCP credentials, project ID, and sync strategies are configured strictly through `.env`.
- **Ephemeral State Reset**: Full in-memory and emulator database reset available via `/api/system/reset` for test reproducibility.

---

## 5. Dual Execution Engine (Live GCP vs Embedded)

- **Embedded Replica (`MemoryFirestore`)**: Pure-Python, thread-safe in-memory replica implementing hierarchical collections, subcollections, compound query filters, real-time snapshot listeners, and atomic counters. Runs the entire 39-test suite in ~0.35s with zero external cloud dependencies.
- **Live Google Cloud Firestore**: Connects seamlessly to Google Cloud Firestore or the local `gcloud beta emulators firestore` when `USE_EMBEDDED_ENGINE=false` and `GCP_PROJECT_ID` is supplied.

---

## 6. Quickstart & Installation

```bash
# 1. Navigate to project directory
cd Build_85

# 2. Activate Python virtual environment
.\venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch FastAPI server
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

Interactive OpenAPI documentation is available at:
`http://127.0.0.1:8000/docs`

---

## 7. API Endpoints Directory

| Method | Endpoint | Description | Firestore Hierarchy Mechanism |
|---|---|---|---|
| `GET` | `/` | Root discovery | Collection schema, WebSocket details, telemetry |
| `POST` | `/api/lists` | Create shopping list | Document write to `/shopping_lists/{list_id}` |
| `GET` | `/api/lists` | Query shopping lists | Collection scan filtered by `owner_id` or collaborator |
| `GET` | `/api/lists/{list_id}` | Get list metadata | Document point lookup |
| `PATCH` | `/api/lists/{list_id}` | Update list title | Atomic document update |
| `DELETE` | `/api/lists/{list_id}` | Delete list | Cascading deletion of list & all subcollections |
| `POST` | `/api/lists/{list_id}/collaborators` | Invite collaborator | Atomic array union on `collaborator_ids` |
| `POST` | `/api/lists/{list_id}/items` | Add item | Document write to `/shopping_lists/{list_id}/items/{id}` |
| `GET` | `/api/lists/{list_id}/items` | List items | Subcollection query with category & status filters |
| `GET` | `/api/lists/{list_id}/items/{item_id}` | Get single item | Subcollection point lookup |
| `PATCH` | `/api/lists/{list_id}/items/{item_id}` | Update item | Subcollection document update |
| `POST` | `/api/lists/{list_id}/items/{item_id}/purchase` | Toggle purchased | Check off item + atomic counter updates |
| `DELETE` | `/api/lists/{list_id}/items/{item_id}` | Delete item | Subcollection document delete + counter updates |
| `GET` | `/api/lists/{list_id}/activity` | Activity audit log | Query `/shopping_lists/{list_id}/activity` |
| `POST` | `/api/sync/offline-batch` | Offline sync batch | Batch processor with LWW and revision conflict checks |
| `WS` | `/api/ws/lists/{list_id}` | Real-time WebSocket | Initial snapshot + incremental mutation deltas |
| `GET` | `/api/system/stats` | Telemetry & stats | Firestore document counts, reads, writes, broadcasts |
| `POST` | `/api/system/reset` | Purge database | Clears all collections and resets telemetry counters |

---

## 8. Automated Verification

Execute the complete 39-test automated test suite:

```bash
pytest -v
```

Output:
```
======================= 39 passed in 0.35s ========================
```

---

## 9. Manual Verification Steps

Run these commands in an independent terminal while the server is running on `http://127.0.0.1:8000`:

### Step 1: Verify Root Discovery & Schema Definition
```powershell
curl -s http://127.0.0.1:8000/
```

### Step 2: Create a Collaborative Shopping List
```powershell
curl -s -X POST http://127.0.0.1:8000/api/lists `
  -H "Content-Type: application/json" `
  -d '{"title": "Weekend Family Groceries", "owner_id": "usr_alice"}'
```

### Step 3: Add Items to List Subcollection
```powershell
# Replace <LIST_ID> with the id returned from Step 2:
curl -s -X POST http://127.0.0.1:8000/api/lists/<LIST_ID>/items `
  -H "Content-Type: application/json" `
  -d '{"name": "Organic Whole Milk", "category": "Dairy", "quantity": 2, "unit": "gallons", "added_by": "usr_alice"}'

curl -s -X POST http://127.0.0.1:8000/api/lists/<LIST_ID>/items `
  -H "Content-Type: application/json" `
  -d '{"name": "Honeycrisp Apples", "category": "Produce", "quantity": 6, "unit": "pcs", "added_by": "usr_alice"}'
```

### Step 4: Toggle Item Purchased (Check Off)
```powershell
# Replace <LIST_ID> and <ITEM_ID>:
curl -s -X POST http://127.0.0.1:8000/api/lists/<LIST_ID>/items/<ITEM_ID>/purchase `
  -H "Content-Type: application/json" `
  -d '{"is_purchased": true, "user_id": "usr_bob"}'
```

### Step 5: Test Offline Batch Mutation Ingestion
```powershell
curl -s -X POST http://127.0.0.1:8000/api/sync/offline-batch `
  -H "Content-Type: application/json" `
  -d '{
    "client_id": "device_mobile_android",
    "user_id": "usr_alice",
    "mutations": [
      {
        "mutation_id": "mut_offline_1",
        "list_id": "<LIST_ID>",
        "action": "ADD",
        "client_timestamp": "2026-09-15T16:00:00Z",
        "payload": {
          "name": "Sourdough Bread",
          "category": "Bakery",
          "quantity": 1,
          "unit": "loaf"
        }
      }
    ]
  }'
```

### Step 6: Query Activity Audit Log
```powershell
curl -s http://127.0.0.1:8000/api/lists/<LIST_ID>/activity
```

### Step 7: Inspect Firestore Telemetry Metrics
```powershell
curl -s http://127.0.0.1:8000/api/system/stats
```

---

## License
MIT License. Copyright (c) 2026.
