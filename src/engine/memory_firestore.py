"""
Thread-safe in-memory replica of Google Cloud Firestore.
Supports hierarchical collections/subcollections, document snapshots,
real-time listener callbacks, query filtering, and optimistic revisions.
"""

import uuid
import threading
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Callable


class MemoryFirestore:
    """
    Hierarchical document database replica providing Google Cloud Firestore semantics.
    """

    def __init__(self) -> None:
        """
        Initialize document store, snapshot listeners, and concurrency lock.
        """
        self._lock: threading.RLock = threading.RLock()

        # Path -> Document data dictionary: e.g. "shopping_lists/l1/items/i1" -> dict
        self._docs: Dict[str, Dict[str, Any]] = {}

        # Listener registry: listener_id -> (target_path, callback_func)
        self._listeners: Dict[str, Tuple[str, Callable[[str, str, Dict[str, Any]], None]]] = {}

        # Telemetry metrics
        self.total_reads: int = 0
        self.total_writes: int = 0
        self.total_deletes: int = 0
        self.total_broadcasts: int = 0

    def _now_iso(self) -> str:
        """
        Generate current UTC timestamp in ISO 8601 format.
        """
        return datetime.now(timezone.utc).isoformat()

    def _normalize_path(self, path: str) -> str:
        """
        Strip leading and trailing slashes for standard path comparison.
        """
        return path.strip("/")

    def _notify_listeners(self, doc_path: str, change_type: str, data: Dict[str, Any]) -> None:
        """
        Notify all registered snapshot listeners interested in this document or its parent collection.
        change_type: "ADDED", "MODIFIED", "REMOVED"
        """
        norm_doc = self._normalize_path(doc_path)
        parts = norm_doc.split("/")
        parent_coll = "/".join(parts[:-1]) if len(parts) > 1 else ""

        for listener_id, (target_path, callback) in list(self._listeners.items()):
            target_norm = self._normalize_path(target_path)
            # Match if listener is registered on exact document or on parent collection
            if target_norm == norm_doc or target_norm == parent_coll:
                try:
                    self.total_broadcasts += 1
                    callback(norm_doc, change_type, dict(data))
                except Exception:
                    # Guard against client callback exceptions
                    pass

    def get_document(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a document by its exact path (e.g. "shopping_lists/list_1").
        """
        norm_path = self._normalize_path(path)
        with self._lock:
            self.total_reads += 1
            doc = self._docs.get(norm_path)
            if doc is None:
                return None
            return dict(doc)

    def set_document(
        self,
        path: str,
        data: Dict[str, Any],
        merge: bool = False,
    ) -> Dict[str, Any]:
        """
        Create or overwrite a document at the specified path.
        """
        norm_path = self._normalize_path(path)
        now = self._now_iso()

        with self._lock:
            self.total_writes += 1
            existing = self._docs.get(norm_path)
            change_type = "MODIFIED" if existing else "ADDED"

            if existing and merge:
                stored = dict(existing)
                stored.update(data)
                stored["revision"] = existing.get("revision", 1) + 1
            else:
                stored = dict(data)
                stored["revision"] = existing.get("revision", 0) + 1 if existing else 1
                if "created_at" not in stored:
                    stored["created_at"] = now

            stored["updated_at"] = now
            self._docs[norm_path] = stored

            # Notify listeners
            self._notify_listeners(norm_path, change_type, stored)
            return dict(stored)

    def update_document(
        self,
        path: str,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Update specific fields of an existing document.
        Returns None if document does not exist.
        """
        norm_path = self._normalize_path(path)
        now = self._now_iso()

        with self._lock:
            existing = self._docs.get(norm_path)
            if existing is None:
                return None

            self.total_writes += 1
            stored = dict(existing)
            stored.update(updates)
            stored["revision"] = existing.get("revision", 1) + 1
            stored["updated_at"] = now
            self._docs[norm_path] = stored

            self._notify_listeners(norm_path, "MODIFIED", stored)
            return dict(stored)

    def delete_document(self, path: str) -> bool:
        """
        Delete a document and any subcollections recursively.
        """
        norm_path = self._normalize_path(path)
        prefix = f"{norm_path}/"

        with self._lock:
            existing = self._docs.get(norm_path)
            if existing is None:
                return False

            self.total_deletes += 1
            old_data = dict(existing)
            del self._docs[norm_path]

            # Cascade delete all child subcollection documents
            child_keys = [k for k in self._docs if k.startswith(prefix)]
            for child_k in child_keys:
                del self._docs[child_k]

            self._notify_listeners(norm_path, "REMOVED", old_data)
            return True

    def list_collection(
        self,
        collection_path: str,
        filters: Optional[List[Tuple[str, str, Any]]] = None,
        order_by_field: Optional[str] = None,
        descending: bool = False,
        limit: Optional[int] = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query direct child documents in a collection or subcollection path.
        filters: list of (field, operator, value), e.g. [("category", "==", "Produce")]
        """
        norm_coll = self._normalize_path(collection_path)
        expected_depth = len(norm_coll.split("/")) + 1
        results: List[Dict[str, Any]] = []

        with self._lock:
            self.total_reads += 1
            for path, doc in self._docs.items():
                # Check if document is an immediate child of the collection
                if not path.startswith(f"{norm_coll}/"):
                    continue

                parts = path.split("/")
                if len(parts) != expected_depth:
                    continue

                # Apply query filters
                matches = True
                if filters:
                    for field, op, val in filters:
                        doc_val = doc.get(field)
                        if op == "==" and doc_val != val:
                            matches = False
                            break
                        elif op == "!=" and doc_val == val:
                            matches = False
                            break
                        elif op == "<" and not (doc_val < val):
                            matches = False
                            break
                        elif op == "<=" and not (doc_val <= val):
                            matches = False
                            break
                        elif op == ">" and not (doc_val > val):
                            matches = False
                            break
                        elif op == ">=" and not (doc_val >= val):
                            matches = False
                            break
                        elif op == "in" and doc_val not in val:
                            matches = False
                            break
                        elif op == "array_contains" and (
                            not isinstance(doc_val, list) or val not in doc_val
                        ):
                            matches = False
                            break

                if matches:
                    results.append(dict(doc))

            # Apply order_by if specified
            if order_by_field:
                results.sort(
                    key=lambda x: str(x.get(order_by_field, "")),
                    reverse=descending,
                )

            # Apply limit if specified
            if limit is not None and limit > 0:
                results = results[:limit]

            return results

    def add_snapshot_listener(
        self,
        path: str,
        callback: Callable[[str, str, Dict[str, Any]], None],
    ) -> str:
        """
        Register a real-time snapshot listener on a document or collection path.
        Returns unique listener_id string.
        """
        listener_id = f"lis_{uuid.uuid4().hex[:12]}"
        with self._lock:
            self._listeners[listener_id] = (self._normalize_path(path), callback)
            return listener_id

    def remove_snapshot_listener(self, listener_id: str) -> bool:
        """
        Unregister an active snapshot listener.
        """
        with self._lock:
            if listener_id in self._listeners:
                del self._listeners[listener_id]
                return True
            return False

    def get_stats(self) -> Dict[str, Any]:
        """
        Return telemetry metrics and active document counts.
        """
        with self._lock:
            return {
                "total_documents": len(self._docs),
                "active_listeners": len(self._listeners),
                "total_reads": self.total_reads,
                "total_writes": self.total_writes,
                "total_deletes": self.total_deletes,
                "total_broadcasts": self.total_broadcasts,
            }

    def truncate(self) -> None:
        """
        Clear all documents and reset telemetry (used in test teardowns).
        """
        with self._lock:
            self._docs.clear()
            self._listeners.clear()
            self.total_reads = 0
            self.total_writes = 0
            self.total_deletes = 0
            self.total_broadcasts = 0
