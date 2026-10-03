"""CORS: only the configured frontend origins may call the API from a browser.

The API used to answer `*` with credentials enabled, which let any website read its responses.
The allowed origins now come from `CORS_ORIGINS` (and an optional `CORS_ORIGIN_REGEX`).
"""

import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.core.config import AppConfig, settings

VERCEL = "https://yatra-ai.vercel.app"
EVIL = "https://evil.example"


def make_client(monkeypatch: pytest.MonkeyPatch, origins: str, regex: str | None = None):
    monkeypatch.setattr(settings.app, "cors_origins", origins)
    monkeypatch.setattr(settings.app, "cors_origin_regex", regex)
    return TestClient(create_app())


def preflight(client: TestClient, origin: str):
    return client.options(
        "/api/plan",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


class TestOriginList:
    def test_defaults_cover_local_development(self):
        assert AppConfig().cors_origin_list == ["http://localhost:3000", "http://127.0.0.1:3000"]

    def test_list_is_trimmed_and_drops_trailing_slashes_and_blanks(self):
        config = AppConfig(cors_origins=f" {VERCEL}/ , ,http://localhost:3000")
        assert config.cors_origin_list == [VERCEL, "http://localhost:3000"]


class TestBrowserAccess:
    def test_a_configured_origin_is_allowed(self, monkeypatch):
        client = make_client(monkeypatch, VERCEL)

        response = preflight(client, VERCEL)

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == VERCEL

    def test_an_unknown_origin_is_refused(self, monkeypatch):
        client = make_client(monkeypatch, VERCEL)

        response = preflight(client, EVIL)

        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers

    def test_an_unknown_origin_gets_no_header_on_a_plain_request(self, monkeypatch):
        client = make_client(monkeypatch, VERCEL)

        response = client.get("/health", headers={"Origin": EVIL})

        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers

    def test_credentials_are_never_allowed(self, monkeypatch):
        client = make_client(monkeypatch, VERCEL)

        response = preflight(client, VERCEL)

        assert "access-control-allow-credentials" not in response.headers

    def test_only_the_methods_the_frontend_uses_are_allowed(self, monkeypatch):
        client = make_client(monkeypatch, VERCEL)

        allowed = preflight(client, VERCEL).headers["access-control-allow-methods"]

        assert "DELETE" not in allowed
        assert {"GET", "POST", "PUT"} <= set(allowed.split(", "))


class TestOriginRegex:
    PATTERN = r"https://yatra-ai-[a-z0-9-]+\.vercel\.app"

    def test_a_matching_preview_origin_is_allowed(self, monkeypatch):
        client = make_client(monkeypatch, "http://localhost:3000", self.PATTERN)
        preview = "https://yatra-ai-git-fix-abc123.vercel.app"

        response = preflight(client, preview)

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == preview

    def test_a_look_alike_origin_is_refused(self, monkeypatch):
        client = make_client(monkeypatch, "http://localhost:3000", self.PATTERN)

        response = preflight(client, "https://yatra-ai-x.vercel.app.evil.example")

        assert response.status_code == 400
