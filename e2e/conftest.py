"""Browser checks against running local services; no browser download required."""
import os
from pathlib import Path
import httpx
import pytest
from playwright.sync_api import sync_playwright

BASE = os.environ.get('MISSION_SYNC_WEB_URL', 'http://127.0.0.1:5173')
API = os.environ.get('MISSION_SYNC_API_URL', 'http://127.0.0.1:8000/api/v1')

@pytest.fixture
def api():
    with httpx.Client(base_url=API, timeout=30) as client:
        ready = client.get('/ready')
        assert ready.status_code == 200, ready.text
        login = client.post('/auth/demo', json={'role': 'administrator'})
        assert login.status_code == 200, login.text
        client.headers['Authorization'] = f"Bearer {login.json()['token']}"
        scenarios = client.get('/simulator/scenarios').json()
        scenario = (scenarios['items'] if isinstance(scenarios, dict) else scenarios)[0]
        reset = client.post(f"/simulator/scenarios/{scenario['id']}/load", json={'confirmed': True})
        assert reset.status_code == 200, reset.text
        restored = client.post('/simulator/reset', json={'scenario_id': scenario['id'], 'confirmed': True})
        assert restored.status_code == 200, restored.text
        yield client

@pytest.fixture
def page(api, request):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'), headless=True, args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        context.add_init_script("if (!localStorage.getItem('missionsync.role')) localStorage.setItem('missionsync.role','administrator');")
        page = context.new_page()
        page.set_default_timeout(10000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        yield page
        if getattr(request.node, 'rep_call', None) and request.node.rep_call.failed:
            output = Path('.local/browser-failures')
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output / f'{request.node.name}.png'), full_page=True)
        context.close()
        browser.close()
        assert not errors, f'Unhandled browser errors: {errors}'

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f'rep_{report.when}', report)
