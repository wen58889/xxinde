from fastapi import APIRouter
from app.auth import create_access_token
from app.schemas import TokenOut

router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.post("/token", response_model=TokenOut)
async def get_token():
    """Generate a JWT token for API access."""
    token = create_access_token({"sub": "admin"})
    return {"access_token": token}
