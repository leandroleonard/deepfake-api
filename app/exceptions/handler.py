from fastapi import Request
from fastapi.responses import JSONResponse
from app.exceptions.errors import DeepFakeApiError 

async def deepfake_exception_handler(request: Request, exc: DeepFakeApiError):
    return JSONResponse(
        status_code=exc.status,
        content={
            "status": exc.status,
            "message": f"{exc.message} [{exc.name}]" if exc.name else exc.message,
            "data": None,
        },
    )