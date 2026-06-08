"""HTTP routes for pools — the three Digital Signage variants.

- ``GET /pools/{id}`` — Variant 1 (edge-only): the Arduino fetches the whole
  pool and decides locally (via the on-device LLM brick).
- ``POST /pools/{id}/choose-by-context`` — Variant 2 (hybrid): the Arduino has
  already done vision locally and sends an open-shaped context dict; Claude
  picks the screen.
- ``POST /pools/{id}/choose-by-img`` — Variant 3 (cloud-only): the Arduino
  uploads the raw camera frame (and optionally a context dict); Claude does
  both vision and selection.
"""
import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, RootModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db import get_session
from app.services import contents as content_service
from app.services import pools as pool_service
from app.services import selection as selection_service
from app.services.selection import SelectionError

router = APIRouter(prefix="/pools", tags=["pools"])


class ContentOut(BaseModel):
    id: int
    name: str
    description: str
    html: str


class PoolOut(BaseModel):
    id: int
    name: str
    description: str
    contents: list[ContentOut]


class ChoiceOut(BaseModel):
    pool_id: int
    chosen_id: int
    name: str
    description: str
    html: str
    reasoning: str


class ChooseByContextIn(RootModel[dict[str, Any]]):
    """Open-shaped context envelope — any JSON object goes.

    Typical shape: ``{"audience": {"group": "young_adult"}, "weather": "rain"}``,
    but unknown keys are intentionally accepted so the client can add new
    signals without an API change.
    """


@router.get("/{pool_id}", response_model=PoolOut)
async def get_pool(pool_id: int, session: AsyncSession = Depends(get_session)) -> PoolOut:
    """Variant 1: return the full pool with all contents inline (HTML included)."""
    pool = await pool_service.get_pool(session, pool_id)
    if pool is None:
        raise HTTPException(status_code=404, detail="pool not found")

    items = await content_service.list_for_pool(session, pool_id)
    contents = [
        ContentOut(
            id=c.id,
            name=c.name,
            description=c.description,
            html=await content_service.read_html(c),
        )
        for c in items
    ]
    return PoolOut(id=pool.id, name=pool.name, description=pool.description, contents=contents)


async def _load_pool_items(
    pool_id: int, session: AsyncSession
) -> list:
    """Fetch a pool's contents for the choose endpoints, or raise the HTTP error.

    404 if the pool doesn't exist, 409 if it has no contents to choose from.
    Shared by both ``choose-by-context`` and ``choose-by-img``.
    """
    pool = await pool_service.get_pool(session, pool_id)
    if pool is None:
        raise HTTPException(status_code=404, detail="pool not found")
    items = await content_service.list_for_pool(session, pool_id)
    if not items:
        raise HTTPException(status_code=409, detail="pool is empty")
    return items


async def _selection_to_response(
    pool_id: int,
    result: selection_service.SelectionResult,
    session: AsyncSession,
) -> ChoiceOut:
    content = await content_service.get_content(session, result.chosen_id)
    if content is None or content.pool_id != pool_id:
        # Shouldn't happen — selection service already validated the id against
        # the pool we passed it — but treat it as a server error if it does.
        raise HTTPException(status_code=500, detail="chosen content vanished")
    html = await content_service.read_html(content)
    return ChoiceOut(
        pool_id=pool_id,
        chosen_id=content.id,
        name=content.name,
        description=content.description,
        html=html,
        reasoning=result.reasoning,
    )


@router.post("/{pool_id}/choose-by-context", response_model=ChoiceOut)
async def choose_by_context(
    pool_id: int,
    payload: ChooseByContextIn,
    session: AsyncSession = Depends(get_session),
) -> ChoiceOut:
    """Variant 2: pick a content based on an open-shaped context dict."""
    items = await _load_pool_items(pool_id, session)

    try:
        result = await selection_service.choose_by_context(items, context=payload.root)
    except SelectionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return await _selection_to_response(pool_id, result, session)


@router.post("/{pool_id}/choose-by-img", response_model=ChoiceOut)
async def choose_by_img(
    pool_id: int,
    image: UploadFile = File(...),
    context: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> ChoiceOut:
    """Variant 3: pick a content based on what Claude Vision sees in the image.

    ``context`` is an optional JSON-encoded string carrying additional signals
    (audience hints, weather, etc.) — mirrors V2's open-shaped envelope.
    """
    items = await _load_pool_items(pool_id, session)

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="image is empty")

    parsed_context: dict | None = None
    if context is not None:
        try:
            parsed_context = json.loads(context)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail="context must be valid JSON") from e
        if not isinstance(parsed_context, dict):
            raise HTTPException(status_code=400, detail="context must be a JSON object")

    try:
        result = await selection_service.choose_by_image(
            items,
            image_bytes=image_bytes,
            mime_type=image.content_type or "image/jpeg",
            context=parsed_context,
        )
    except SelectionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return await _selection_to_response(pool_id, result, session)
