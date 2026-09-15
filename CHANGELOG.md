# Changelog — Build 85

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-15
### Added
- **Firestore Hierarchical Subcollection Architecture**: Nested document paths for shopping lists (`/shopping_lists/{list_id}`), items (`/shopping_lists/{list_id}/items/{item_id}`), and activity audit trails (`/shopping_lists/{list_id}/activity/{activity_id}`).
- **Real-Time Snapshot Listeners & WebSockets**: Connection endpoint `/api/ws/lists/{list_id}` broadcasting initial full state snapshots on connect and incremental delta mutations (`ITEM_ADDED`, `ITEM_UPDATED`, `ITEM_PURCHASED`, `ITEM_DELETED`) to all connected collaborators.
- **Offline Batch Sync & Conflict Resolution**: Batch ingestion endpoint `/api/sync/offline-batch` supporting multi-action mutation queues (`ADD`, `UPDATE`, `TOGGLE_PURCHASE`, `DELETE`) with configurable conflict strategies (**Last-Write-Wins** and **Optimistic Revision Check**).
- **Collaborator Management & Atomic Arrays**: Collaborator invitation endpoint `/api/lists/{list_id}/collaborators` appending users to list document permissions.
- **Atomic Counters & Cascading Deletions**: List documents maintain atomic `item_count` and `completed_count` aggregates; deleting a list performs cascading deletion across all nested item and activity subcollections.
- **Dual Execution Engine**: Embedded thread-safe pure-Python `MemoryFirestore` replica providing compound queries, subcollection nesting, listener subscriptions, and telemetry metrics alongside GCP Firestore SDK support.
- **Activity Audit Trail**: Automatic audit logging in subcollection `/activity` tracking creation, edits, purchases, deletions, and offline sync events.
- **Automated Test Suite**: 39 comprehensive unit and integration tests across engine, services, WebSocket broadcast, and REST endpoints passing in 0.35s.
