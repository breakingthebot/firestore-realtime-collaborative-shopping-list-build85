"""
Firestore client provider.
Provides singleton instance of MemoryFirestore for local and testing execution.
"""

from typing import Any
from src.engine.memory_firestore import MemoryFirestore

_firestore_instance: MemoryFirestore | None = None


def get_firestore_engine() -> MemoryFirestore:
    """
    Retrieve the active Firestore database engine singleton.
    """
    global _firestore_instance
    if _firestore_instance is None:
        _firestore_instance = MemoryFirestore()
    return _firestore_instance


def reset_firestore_engine() -> None:
    """
    Reset and purge the active Firestore engine state (used during test teardowns).
    """
    global _firestore_instance
    if _firestore_instance is not None:
        _firestore_instance.truncate()
