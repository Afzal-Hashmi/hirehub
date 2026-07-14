"""In-app notifications + WebSocket for real-time push."""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import OrgContext, get_current_user, get_org_context
from app.database import get_db
from app.models.notification import Notification
from app.models.user import User

router = APIRouter(prefix="/notifications", tags=["notifications"])

# Simple in-memory WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(user_id, []).append(ws)

    def disconnect(self, user_id: str, ws: WebSocket):
        if user_id in self._connections:
            self._connections[user_id].discard(ws)

    async def send_to_user(self, user_id: str, data: dict):
        for ws in list(self._connections.get(user_id, [])):
            try:
                await ws.send_json(data)
            except Exception:
                self._connections[user_id].discard(ws)


manager = ConnectionManager()


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """Real-time notification stream. Frontend connects here after auth."""
    await manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)


@router.get("")
async def list_notifications(
    unread_only: bool = False,
    page: int = 1,
    limit: int = 20,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    query = select(Notification).where(
        Notification.user_id == ctx.user.id,
        Notification.organization_id == ctx.org_id,
    )
    if unread_only:
        query = query.where(Notification.is_read == False)

    result = await db.execute(query.order_by(Notification.created_at.desc()).offset((page - 1) * limit).limit(limit))
    notifications = result.scalars().all()

    return [
        {
            "id": str(n.id),
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "action_url": n.action_url,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifications
    ]


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: uuid.UUID,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(Notification)
        .where(Notification.id == notification_id, Notification.user_id == ctx.user.id)
        .values(is_read=True, read_at=datetime.now(UTC))
    )
    await db.commit()
    return {"status": "read"}


@router.post("/read-all")
async def mark_all_read(ctx: OrgContext = Depends(get_org_context), db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == ctx.user.id,
            Notification.organization_id == ctx.org_id,
            Notification.is_read == False,
        )
        .values(is_read=True, read_at=datetime.now(UTC))
    )
    await db.commit()
    return {"status": "all read"}
