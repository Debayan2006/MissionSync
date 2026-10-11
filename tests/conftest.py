"""Isolated SQLite-backed API fixtures; no external services or credentials."""

import pytest
from fastapi.testclient import TestClient
import re

from tests.api_catalogue import API_CATALOGUE


EXERCISED_ENDPOINTS = set()


class CataloguedClient(TestClient):
    def request(self, method, url, *args, **kwargs):
        response = super().request(method, url, *args, **kwargs)
        path = str(url).split("?", 1)[0]
        # Specific routes precede parameter routes, as in FastAPI route matching.
        for endpoint in sorted(API_CATALOGUE, key=lambda item: ("{" in item, -len(item))):
            pattern = re.sub(r"\{[^}]+\}", "[^/]+", "/api/v1" + endpoint)
            if method.upper() in API_CATALOGUE[endpoint] and re.fullmatch(pattern, path):
                EXERCISED_ENDPOINTS.add((method.upper(), endpoint))
                break
        return response


def pytest_addoption(parser):
    parser.addoption("--backend-api-coverage", action="store_true", help="Require every PRD API method to be exercised by the complete integration suite.")


def pytest_sessionfinish(session, exitstatus):
    if not session.config.getoption("--backend-api-coverage"):
        return
    expected = {(method, endpoint) for endpoint, methods in API_CATALOGUE.items() for method in methods}
    missing = expected - EXERCISED_ENDPOINTS
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter:
        reporter.write_line(f"PRD API method coverage: {len(EXERCISED_ENDPOINTS & expected)}/{len(expected)}")
        for method, endpoint in sorted(missing):
            reporter.write_line(f"Unexercised: {method} /api/v1{endpoint}")
    if missing and exitstatus == 0:
        session.exitstatus = 1


class RoleHeaders(dict):
    def __repr__(self):
        return "<local demo authorization header>"


@pytest.fixture
def client(tmp_path):
    from backend.app import create_app

    app = create_app(database_path=str(tmp_path / "missionsync-test.sqlite3"))
    with CataloguedClient(app) as test_client:
        test_client.test_database_path = tmp_path / "missionsync-test.sqlite3"
        yield test_client


@pytest.fixture
def roles(client):
    tokens = {}
    for role in ("viewer", "analyst", "commander", "administrator"):
        response = client.post("/api/v1/auth/demo", json={"role": role})
        assert response.status_code == 200, response.text
        token = response.json()["token"]
        tokens[role] = RoleHeaders(Authorization=f"Bearer {token}")
    return tokens


@pytest.fixture
def seeded(client, roles):
    response = client.post(
        "/api/v1/simulator/scenarios/kolkata-flood/load",
        json={"confirmed": True},
        headers=roles["analyst"],
    )
    assert response.status_code in (200, 201), response.text
    return response.json()
