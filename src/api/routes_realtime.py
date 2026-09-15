"""
WebSocket real-time snapshot listener endpoint for live multi-user collaborative updates.
"""

import json
import asyncio
from typing import Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.config import settings
from src.engine.firestore_client import get_firestore_engine
from src.services.shopping_service import ShoppingService

router = APIRouter(tags=["Real-Time Listeners"])
shopping_service = ShoppingService()


@router.websocket("/api/ws/lists/{list_id}")
async def websocket_list_listener(websocket: WebSocket, list_id: str):
    """
    WebSocket endpoint establishing a live Firestore snapshot listener for a shopping list.
    Streams real-time updates to all connected collaborators.
    """
    await websocket.accept()
    engine = get_firestore_engine()
    loop = asyncio.get_running_loop()

    # Callback invoked by MemoryFirestore when document changes
    def snapshot_callback(doc_path: str, change_type: str, data: Dict[str, Any]) -> None:
        message = {
            "event": "SNAPSHOT_UPDATE",
            "list_id": list_id,
            "change_type": change_type,
            "path": doc_path,
            "data": data,
        }
        # Schedule sending message on asyncio event loop
        asyncio.run_coroutine_threadsafe(
            websocket.send_text(json.dumps(message)),
            loop,
        )

    # Register listener on list subcollection
    items_path = f"{settings.COLLECTION_LISTS}/{list_id}/{settings.SUBCOLLECTION_ITEMS}"
    listener_id = engine.add_snapshot_listener(items_path, snapshot_callback)

    try:
        # Send initial snapshot to client upon connection
        current_list = shopping_service.get_list(list_id)
        current_items = shopping_service.list_items(list_id)

        init_frame = {
            "event": "SNAPSHOT_INIT",
            "list": current_list.model_dump() if current_list else None,
            "items": [it.model_dump() for it in current_items],
        }
        await websocket.send_text(json.dumps(init_frame))

        # Keep connection open and process any incoming ping/messages
        while True:
            client_msg = await websocket.receive_text()
            if client_msg == "ping":
                await websocket.send_text(json.dumps({"event": "pong"}))

    except WebSocketDisconnect:
        pass
    finally:
        # Unsubscribe listener on client disconnect
        engine.remove_snapshot_listener(listener_id)
