"""
server.oauth_compat 회귀 테스트.

MCP 2025-06-18 OAuth 프로브 5개 경로(GET 4 + POST /register)가 평문이 아닌
JSON 404 (`{}`, content-type application/json) 로 응답하는지 확인. SDK 의
JSON 파싱 회귀 (`SDK auth failed: HTTP 404: Invalid OAuth error response`) 차단.

추가로 Mount('/') 가 같이 있는 실제 라우팅 구성에서 (a) probe 경로는 JSON 404,
(b) 마운트된 일반 경로는 그대로 통과하는지 — 라우트 precedence 회귀를 차단한다.

pytest 또는 standalone 실행 모두 가능:
    pytest tests/test_oauth_compat.py
    uv run python tests/test_oauth_compat.py   # 또는 python -m tests.test_oauth_compat
"""

import os
import sys

# standalone(`python tests/test_oauth_compat.py`) 실행 시 server 모듈 import 가능하게.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route
from starlette.testclient import TestClient

from server.oauth_compat import make_oauth_probe_routes


def _probe_only_client():
    return TestClient(Starlette(routes=make_oauth_probe_routes()))


def _with_mount_client():
    """probe 라우트 + Mount('/') 가 공존하는 실제 app 구성과 동일."""
    async def _ok(request):
        return PlainTextResponse("ok")

    mounted = Starlette(routes=[Route("/sse", _ok), Route("/messages", _ok)])
    routes = make_oauth_probe_routes() + [Mount("/", app=mounted)]
    return TestClient(Starlette(routes=routes))


_GET_PATHS = (
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-protected-resource/sse",
    "/.well-known/oauth-protected-resource/messages",
    "/.well-known/oauth-authorization-server",
    "/.well-known/openid-configuration",
)


def test_oauth_metadata_get_paths_return_json_404():
    client = _probe_only_client()
    for path in _GET_PATHS:
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.headers["content-type"].startswith("application/json"), path
        assert response.json() == {}, path


def test_register_post_returns_json_404():
    response = _probe_only_client().post("/register", json={})
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {}


def test_probe_routes_precede_mount_and_mount_still_serves_others():
    """probe 라우트가 Mount('/') 앞에 있어 (a) probe 는 JSON 404, (b) /sse·/messages
    같이 mount 경유 경로는 정상 동작해야 함."""
    client = _with_mount_client()

    # (a) probe — Mount catch-all 에 흡수되지 않고 JSON 404
    for path in _GET_PATHS:
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.headers["content-type"].startswith("application/json"), path

    # (b) mount — 정상 통과 (SSE 핸들러 stub 200)
    for path in ("/sse", "/messages"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.text == "ok", path


if __name__ == "__main__":
    test_oauth_metadata_get_paths_return_json_404()
    test_register_post_returns_json_404()
    test_probe_routes_precede_mount_and_mount_still_serves_others()
    print("OAuth probe regression tests passed.")
