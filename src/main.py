"""
FastAPI application entrypoint for Build 85: Real-Time Collaborative Shopping List.
Demonstrates Google Cloud Firestore hierarchical collections, subcollections,
live snapshot listeners, and multi-user offline synchronization.
"""

from contextlib import asynccontextmanager
from typing import Dict, Any, AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.engine.firestore_client import get_firestore_engine
from src.api.routes_lists import router as lists_router
from src.api.routes_items import router as items_router
from src.api.routes_sync import router as sync_router
from src.api.routes_realtime import router as realtime_router
from src.api.routes_system import router as system_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan context manager for startup and shutdown hooks.
    """
    engine = get_firestore_engine()
    yield
    # Cleanup on shutdown


app = FastAPI(
    title="Build 85: Real-Time Collaborative Shopping List",
    description="Google Cloud Firestore hierarchical document database with subcollections, live snapshot listeners, and offline synchronization.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount REST and WebSocket sub-routers
app.include_router(lists_router)
app.include_router(items_router)
app.include_router(sync_router)
app.include_router(realtime_router)
app.include_router(system_router)


@app.get("/", tags=["Discovery"])
def root_discovery() -> Dict[str, Any]:
    """
    Root discovery endpoint providing architecture details and schema reference.
    """
    engine = get_firestore_engine()
    stats = engine.get_stats()

    return {
        "service": "Build 85: Real-Time Collaborative Shopping List",
        "technology": "Google Cloud Firestore & FastAPI",
        "database_type": "NoSQL Hierarchical Document Database",
        "collections_schema": {
            "root_collection": f"/{settings.COLLECTION_LISTS}/{{list_id}}",
            "items_subcollection": f"/{settings.COLLECTION_LISTS}/{{list_id}}/{settings.SUBCOLLECTION_ITEMS}/{{item_id}}",
            "activity_subcollection": f"/{settings.COLLECTION_LISTS}/{{list_id}}/{settings.SUBCOLLECTION_ACTIVITY}/{{activity_id}}",
        },
        "realtime_listeners": {
            "websocket_endpoint": "/api/ws/lists/{list_id}",
            "snapshot_behavior": "Full snapshot on connect + incremental deltas on document changes",
        },
        "offline_support": {
            "sync_endpoint": "/api/sync/offline-batch",
            "conflict_strategy": settings.SYNC_CONFLICT_STRATEGY,
        },
        "telemetry": stats,
        "docs_url": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
