"""Ask session endpoints for interactive Q&A with analysis results."""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

# Max seconds to wait for the next streaming chunk before giving up
_STREAM_CHUNK_TIMEOUT = 60

from bundle_analyzer.api.deps import get_session
from bundle_analyzer.api.schemas import InterviewRequest, InterviewResponse
from bundle_analyzer.api.session import BundleSession

router = APIRouter(prefix="/bundles/{bundle_id}/interview", tags=["interview"])


@router.post("", response_model=dict)
async def create_interview_session(
    session: BundleSession = Depends(get_session),
) -> dict[str, str]:
    """Create a new ask session for a completed analysis.

    Args:
        session: The bundle session (must have completed analysis).

    Returns:
        Dict containing the new ask session_id.

    Raises:
        HTTPException: 404 if analysis is not complete.
    """
    if session.analysis is None:
        raise HTTPException(
            status_code=404,
            detail="Analysis must complete before starting an ask session. "
            f"Current status: {session.status}",
        )

    from bundle_analyzer.ai.client import BundleAnalyzerClient
    from bundle_analyzer.ai.interview import InterviewSession

    try:
        client = BundleAnalyzerClient()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"AI client not available: {exc}",
        ) from exc

    interview_id = uuid.uuid4().hex[:8]
    interview = InterviewSession(
        analysis_result=session.analysis,
        client=client,
    )
    session.interview_sessions[interview_id] = interview

    logger.info(
        "Created ask session {} for bundle {}",
        interview_id,
        session.id,
    )

    return {"session_id": interview_id}


@router.post("/{session_id}/ask", response_model=InterviewResponse)
async def ask_question(
    session_id: str,
    request: InterviewRequest,
    session: BundleSession = Depends(get_session),
) -> InterviewResponse:
    """Ask a question in an existing ask session.

    Args:
        session_id: The ask session identifier.
        request: The question to ask.
        session: The parent bundle session.

    Returns:
        InterviewResponse with the answer and conversation history.

    Raises:
        HTTPException: 404 if ask session not found.
    """
    interview = session.interview_sessions.get(session_id)
    if interview is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ask session {session_id} not found",
        )

    try:
        answer = await interview.ask(request.question)
    except Exception as exc:
        logger.error("Interview AI call failed: {}", exc)
        raise HTTPException(
            status_code=504,
            detail="AI provider timed out. Please try again.",
        ) from exc

    return InterviewResponse(
        answer=answer,
        history=interview.history,
    )


@router.post("/{session_id}/ask/stream")
async def ask_question_stream(
    session_id: str,
    request: InterviewRequest,
    session: BundleSession = Depends(get_session),
) -> StreamingResponse:
    """Stream an answer token-by-token via Server-Sent Events.

    Args:
        session_id: The ask session identifier.
        request: The question to ask.
        session: The parent bundle session.

    Returns:
        StreamingResponse with SSE text/event-stream content.
    """
    interview = session.interview_sessions.get(session_id)
    if interview is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ask session {session_id} not found",
        )

    async def event_generator():
        try:
            stream_iter = interview.ask_stream(request.question).__aiter__()
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        stream_iter.__anext__(),
                        timeout=_STREAM_CHUNK_TIMEOUT,
                    )
                    data = json.dumps({"token": chunk})
                    yield f"data: {data}\n\n"
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    logger.warning("Stream chunk timed out after {}s", _STREAM_CHUNK_TIMEOUT)
                    data = json.dumps({"token": "\n\n*[Response timed out]*"})
                    yield f"data: {data}\n\n"
                    break
            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.error("Stream error: {}", exc)
            data = json.dumps({"error": str(exc)})
            yield f"data: {data}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{session_id}/history", response_model=list[dict])
async def get_interview_history(
    session_id: str,
    session: BundleSession = Depends(get_session),
) -> list[dict[str, str]]:
    """Return the conversation history for an ask session.

    Args:
        session_id: The ask session identifier.
        session: The parent bundle session.

    Returns:
        List of message dicts with 'role' and 'content' keys.

    Raises:
        HTTPException: 404 if ask session not found.
    """
    interview = session.interview_sessions.get(session_id)
    if interview is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ask session {session_id} not found",
        )

    return interview.history
