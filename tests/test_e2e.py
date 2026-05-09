import sys, os, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import requests
import pytest

API = "http://localhost:8001"
BACKEND_DIR  = os.path.join(os.path.dirname(__file__), "..", "backend")
FRONTEND_PATH = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")

_server_proc = None


def start_server():
    global _server_proc
    env = os.environ.copy()
    env["PYTHONPATH"] = BACKEND_DIR
    _server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--port", "8001", "--host", "0.0.0.0"],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return _server_proc


def wait_for_health(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{API}/health", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def wait_for_pipeline(timeout=900):
    """Wait until /status.status == 'ready'. Unlabelled detection adds ~3 min."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{API}/status", timeout=5)
            if r.status_code == 200 and r.json().get("status") == "ready":
                return True
        except Exception:
            pass
        time.sleep(5)
    return False


def stop_server():
    global _server_proc
    if _server_proc:
        _server_proc.terminate()
        try:
            _server_proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _server_proc.kill()
        _server_proc = None


@pytest.fixture(scope="module", autouse=True)
def server():
    start_server()
    if not wait_for_health(timeout=30):
        out, err = _server_proc.stdout.read(4096), _server_proc.stderr.read(4096)
        stop_server()
        pytest.fail(f"Server /health did not respond in 30s.\nSTDERR: {err}")
    print("\nServer is up — waiting for pipeline (up to 900s)...")
    if not wait_for_pipeline(timeout=900):
        stop_server()
        pytest.fail("Pipeline did not complete within 900s")
    print("Pipeline ready.")
    yield
    stop_server()


def test_health():
    r = requests.get(f"{API}/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_status_alert_count():
    r = requests.get(f"{API}/status")
    assert r.status_code == 200
    data = r.json()
    assert data["alert_count"] > 0, "No alerts detected"
    assert data["status"] == "ready"


def test_status_has_labelled_and_unlabelled_counts():
    r = requests.get(f"{API}/status")
    assert r.status_code == 200
    data = r.json()
    assert "labelled_count" in data,   "Missing labelled_count in /status"
    assert "unlabelled_count" in data, "Missing unlabelled_count in /status"
    assert "overlap_count" in data,    "Missing overlap_count in /status"
    assert data["labelled_count"] > 0,   "No labelled alerts"
    assert data["unlabelled_count"] > 0, "No unlabelled alerts"


def test_list_alerts():
    r = requests.get(f"{API}/alerts")
    assert r.status_code == 200
    alerts = r.json()
    assert isinstance(alerts, list) and len(alerts) > 0
    for a in alerts:
        for key in ("id", "name", "severity", "confidence", "source"):
            assert key in a, f"Missing key {key}"


def test_filter_by_source_unlabelled():
    r = requests.get(f"{API}/alerts?source=unlabelled")
    assert r.status_code == 200
    alerts = r.json()
    assert len(alerts) > 0, "No unlabelled alerts returned"
    for a in alerts:
        assert a["source"] == "unlabelled", f"Alert {a['id']} has wrong source"


def test_filter_by_source_labelled():
    r = requests.get(f"{API}/alerts?source=labelled")
    assert r.status_code == 200
    alerts = r.json()
    assert len(alerts) > 0, "No labelled alerts returned"
    for a in alerts:
        assert a["source"] == "labelled", f"Alert {a['id']} has wrong source"


def test_get_alert_detail():
    first_id = requests.get(f"{API}/alerts").json()[0]["id"]
    r = requests.get(f"{API}/alerts/{first_id}")
    assert r.status_code == 200
    detail = r.json()
    assert len(detail["nodes"]) > 0
    assert len(detail["edges"]) > 0
    assert "source" in detail
    assert "signalsTriggered" in detail


def test_post_decision():
    first_id = requests.get(f"{API}/alerts").json()[0]["id"]
    r = requests.post(
        f"{API}/alerts/{first_id}/decision",
        json={"decision": "confirm", "reason": "test"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "saved"


def test_filter_by_severity():
    r = requests.get(f"{API}/alerts?severity=HIGH")
    assert r.status_code == 200
    for a in r.json():
        assert a["severity"] == "HIGH"


def test_not_found():
    r = requests.get(f"{API}/alerts/nonexistent_id_xyz")
    assert r.status_code == 404


def test_frontend_exists():
    assert os.path.exists(FRONTEND_PATH)
    content = open(FRONTEND_PATH, encoding="utf-8").read()
    assert "cytoscape" in content.lower()
    assert "API_BASE" in content
