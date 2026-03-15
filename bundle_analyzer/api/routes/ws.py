"""WebSocket endpoint for streaming analysis progress."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from bundle_analyzer.api.deps import get_store

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{bundle_id}/progress")
async def progress_websocket(
    websocket: WebSocket,
    bundle_id: str,
) -> None:
    """Stream analysis progress messages to the client via WebSocket.

    Sends ProgressMessage-shaped JSON objects from the session's
    progress_queue. Closes when the analysis is complete or errors,
    or when the client disconnects.

    Args:
        websocket: The WebSocket connection.
        bundle_id: The bundle session id to stream progress for.
    """
    await websocket.accept()

    store = get_store()
    session = store.get(bundle_id)

    if session is None:
        await websocket.send_json({"error": f"Bundle {bundle_id} not found"})
        await websocket.close(code=4004)
        return

    logger.info("WebSocket connected for bundle {} progress", bundle_id)

    # Send current state so late-connecting clients catch up
    await websocket.send_json({
        "stage": session.current_stage,
        "pct": session.progress,
        "message": session.message,
    })

    # If already complete/error, close immediately
    if session.status in ("complete", "error"):
        await websocket.close()
        return

    try:
        while True:
            try:
                # Wait for progress messages with a timeout
                msg = await asyncio.wait_for(
                    session.progress_queue.get(),
                    timeout=30.0,
                )
                await websocket.send_json(msg)

                # If we reached completion or error, send and close
                if msg.get("stage") in ("complete", "error"):
                    logger.info(
                        "Progress stream ending for bundle {}: {}",
                        bundle_id,
                        msg.get("stage"),
                    )
                    break

            except TimeoutError:
                # Send a heartbeat to keep the connection alive
                await websocket.send_json({
                    "stage": "heartbeat",
                    "pct": session.progress,
                    "message": session.message,
                })

                # If the session ended while we were waiting, break
                if session.status in ("complete", "error"):
                    await websocket.send_json({
                        "stage": session.status,
                        "pct": session.progress,
                        "message": session.error or session.message,
                    })
                    break

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for bundle {}", bundle_id)
    except Exception as exc:
        logger.error("WebSocket error for bundle {}: {}", bundle_id, exc)
        try:
            await websocket.send_json({"error": str(exc)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
