from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from vidistill.middleware import VisitorCookieMiddleware


def _app():
    app = FastAPI()
    app.add_middleware(VisitorCookieMiddleware)

    @app.get("/whoami")
    def whoami(request: Request):
        return {"visitor_id": request.state.visitor_id}

    return app


def test_middleware_sets_cookie_when_absent():
    client = TestClient(_app())
    r = client.get("/whoami")
    assert r.status_code == 200
    assert "visitor_id" in r.cookies
    assert len(r.cookies["visitor_id"]) >= 16
    assert r.json()["visitor_id"] == r.cookies["visitor_id"]


def test_middleware_passes_through_existing_cookie():
    client = TestClient(_app())
    r = client.get("/whoami", cookies={"visitor_id": "existing-id-xyz"})
    assert r.json()["visitor_id"] == "existing-id-xyz"
    # No new cookie set in response
    assert "visitor_id" not in r.cookies or r.cookies["visitor_id"] == "existing-id-xyz"


def test_middleware_cookie_attributes_httponly_lax():
    client = TestClient(_app())
    r = client.get("/whoami")
    set_cookie = r.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie.lower() or "samesite=lax" in set_cookie.lower()
    assert "Max-Age=63072000" in set_cookie
