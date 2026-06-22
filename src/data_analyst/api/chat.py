from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/chat")
async def chat() -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={
            "detail": {
                "code": "NOT_IMPLEMENTED",
                "message": "Chat endpoint not yet implemented",
            }
        },
    )
