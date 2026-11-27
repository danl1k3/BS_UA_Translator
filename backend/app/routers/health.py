from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def get_health(request: Request):
    """Return inference reachability and the file queue length."""
    inference = await request.app.state.backend.check_health()
    return {
        "status": inference["status"],
        "queue_size": request.app.state.jobs.size,
        "inference": inference,
    }


@router.get("/quota")
async def get_quota(request: Request):
    """Return today's remaining GPU quota, or null if it cannot be read."""
    return {"quota": await request.app.state.backend.get_quota()}
