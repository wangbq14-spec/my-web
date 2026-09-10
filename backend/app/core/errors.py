from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class APIError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code, self.message, self.status_code = code, message, status_code


def _payload(request: Request, code: str, message: str, detail=None) -> dict:
    payload = {"error": {"code": code, "message": message, "request_id": getattr(request.state, "request_id", None)}}
    if detail is not None:
        payload["detail"] = detail
    return payload


async def api_error_handler(request: Request, exc: APIError):
    return JSONResponse(_payload(request, exc.code, exc.message), status_code=exc.status_code)


async def http_error_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    message = detail if isinstance(detail, str) else str(detail)
    return JSONResponse(_payload(request, f"HTTP_{exc.status_code}", message, detail), status_code=exc.status_code)
