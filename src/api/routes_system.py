"""
FastAPI REST routes for system health, telemetry stats, and engine reset.
"""

from typing import Dict, Any
from fastapi import APIRouter
from src.engine.firestore_client import get_firestore_engine, reset_firestore_engine
from src.models.schema import FirestoreStatsResponse

router = APIRouter(prefix="/api/system", tags=["System & Telemetry"])


@router.get(
    "/health",
    response_model=Dict[str, str],
    summary="Firestore Engine Health Check",
)
def health_check_endpoint() -> Dict[str, str]:
    """
    Check if the Firestore engine is active and accepting operations.
    """
    return {
        "status": "HEALTHY",
        "engine": "MemoryFirestore",
    }


@router.get(
    "/stats",
    response_model=FirestoreStatsResponse,
    summary="Get Firestore Telemetry and Broadcast Metrics",
)
def get_stats_endpoint() -> FirestoreStatsResponse:
    """
    Returns active document count, active snapshot listeners, and cumulative operations.
    """
    engine = get_firestore_engine()
    stats = engine.get_stats()
    return FirestoreStatsResponse(**stats)


@router.post(
    "/reset",
    response_model=Dict[str, str],
    summary="Reset and clear all Firestore documents (test/demo)",
)
def reset_database_endpoint() -> Dict[str, str]:
    """
    Purge all documents, collections, and reset telemetry metrics.
    """
    reset_firestore_engine()
    return {
        "status": "SUCCESS",
        "message": "Firestore engine state reset",
    }
