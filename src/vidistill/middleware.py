import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


COOKIE_NAME = "visitor_id"
COOKIE_MAX_AGE = 63_072_000  # 2 years


class VisitorCookieMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        visitor_id = request.cookies.get(COOKIE_NAME)
        is_new = False
        if not visitor_id:
            visitor_id = secrets.token_urlsafe(16)
            is_new = True
        request.state.visitor_id = visitor_id
        response = await call_next(request)
        if is_new:
            response.set_cookie(
                key=COOKIE_NAME,
                value=visitor_id,
                max_age=COOKIE_MAX_AGE,
                httponly=True,
                samesite="lax",
                path="/",
            )
        return response
