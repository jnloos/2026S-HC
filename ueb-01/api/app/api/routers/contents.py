"""HTTP route for previewing content snippets in a browser.

The snippets are partial HTML (the Arduino later wraps them in its own frame).
For dev/preview this route serves a minimal HTML page that embeds the snippet,
so you can open ``/contents/1`` in a browser and see it rendered.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db import get_session
from app.services import contents as content_service

router = APIRouter(prefix="/contents", tags=["contents"])

_PREVIEW_PAGE = """\
<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>Content #{id} — {name}</title>
  <style>
    html, body {{ margin: 0; padding: 0; }}
    body {{
      background: #f4f4f5;
      font-family: system-ui, -apple-system, sans-serif;
      min-height: 100vh;
      box-sizing: border-box;
      padding: 32px;
      display: flex;
      flex-direction: column;
      align-items: center;
    }}
    .preview-meta {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 13px;
      color: #555;
      background: #fff;
      border: 1px solid #e5e5e5;
      padding: 8px 14px;
      border-radius: 8px;
      margin-bottom: 24px;
    }}
    .preview-shell {{ width: 100%; max-width: 960px; }}
    .preview-description {{
      font-size: 14px;
      color: #444;
      background: #fffbe6;
      border-left: 4px solid #f0c33c;
      padding: 12px 16px;
      border-radius: 4px;
      margin-bottom: 24px;
    }}
  </style>
</head>
<body>
  <div class="preview-meta">content #{id} · pool #{pool_id} · {name}</div>
  <div class="preview-shell">
    {description_block}
    {snippet}
  </div>
</body>
</html>
"""


@router.get("/{content_id}", response_class=HTMLResponse)
async def preview_content(
    content_id: int, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    """Render the content's HTML snippet inside a minimal preview page."""
    content = await content_service.get_content(session, content_id)
    if content is None:
        raise HTTPException(status_code=404, detail="content not found")

    snippet = await content_service.read_html(content)
    description_block = (
        f'<div class="preview-description">{content.description}</div>'
        if content.description
        else ""
    )
    page = _PREVIEW_PAGE.format(
        id=content.id,
        pool_id=content.pool_id,
        name=content.name,
        description_block=description_block,
        snippet=snippet,
    )
    return HTMLResponse(page)
