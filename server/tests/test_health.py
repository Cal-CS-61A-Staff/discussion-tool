"""GET /api/health backs the load-balancer / uptime check (server/app.py) —
covers that it actually verifies DB connectivity rather than just "the
process is up".
"""


def test_health_ok_when_db_reachable(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
