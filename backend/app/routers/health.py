from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def get_health(request: Request):
    """Return current gateway and remote inference health status."""
    return await request.app.state.queue_manager.get_current_status()
