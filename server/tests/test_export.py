"""The downloadable runnable HTML copy of a group's work
(server/services/export_html.py, GET /api/w/<code>/g/<id>/export)."""

from server.extensions import db
from server.models.worksheet import Question, Worksheet
from server.tests.conftest import make_class, new_browser, publish


def _published_worksheet():
    klass = make_class("CS 61A")
    worksheet = Worksheet(class_id=klass.id, slug="disc-1", title="Discussion 1")
    db.session.add(worksheet)
    db.session.flush()
    db.session.add(
        Question(
            worksheet_id=worksheet.id,
            order_index=0,
            title="Square",
            prompt="Write `square`.",
            starter_code="def square(x):\n    return 0\n",
            grading_mode="doctest",
        )
    )
    code = publish(worksheet)
    db.session.commit()
    return worksheet, code


def test_member_downloads_a_self_contained_html(app, client):
    worksheet, code = _published_worksheet()
    group_id = client.post(f"/api/w/{code}/join", json={"name": "Sam", "number": 1}).get_json()["group_id"]

    resp = client.get(f"/api/w/{code}/g/{group_id}/export")
    assert resp.status_code == 200
    assert "text/html" in resp.content_type
    assert "attachment" in resp.headers["Content-Disposition"]
    body = resp.get_data(as_text=True)
    assert "<title>" in body
    assert "def grade(" in body  # the harness is inlined
    assert "Discussion 1" in body


def test_non_member_cannot_export(app, client):
    worksheet, code = _published_worksheet()
    group_id = client.post(f"/api/w/{code}/join", json={"name": "Sam", "number": 1}).get_json()["group_id"]

    new_browser(client)
    client.post(f"/api/w/{code}/join", json={"name": "Other", "number": 2})
    assert client.get(f"/api/w/{code}/g/{group_id}/export").status_code == 403
