"""Covers admin-created sections, a TA renaming their own section, and
co-authority (SectionCoTeacher) — granting another TA the same access to a
section as its primary TA, revocable by anyone who already has that access.
"""

from server.extensions import db
from server.models.klass import Class
from server.models.section import Section, SectionCoTeacher
from server.models.user import User
from server.tests.conftest import login_as


def _make_section_with_primary_ta():
    ta = User(display_name="Primary TA", role="ta", email="primary@berkeley.edu")
    db.session.add(ta)
    db.session.flush()
    klass = Class(course_name="C")
    db.session.add(klass)
    db.session.flush()
    section = Section(class_id=klass.id, name="S", ta_user_id=ta.id)
    db.session.add(section)
    db.session.commit()
    return section, ta


def test_admin_can_create_a_section(app, client, db):
    admin = User(display_name="Admin", role="admin")
    ta = User(display_name="TA", role="ta")
    klass = Class(course_name="CS 61A")
    db.session.add_all([admin, ta, klass])
    db.session.commit()

    login_as(client, ta)
    resp = client.post("/api/sections", json={"class_id": klass.id, "name": "New Section"})
    assert resp.status_code == 403

    login_as(client, admin)
    resp = client.post("/api/sections", json={"class_id": klass.id, "name": "New Section"})
    assert resp.status_code == 201
    assert resp.get_json()["section"]["name"] == "New Section"
    assert resp.get_json()["section"]["ta_id"] is None


def test_section_and_ta_list_expose_ta_email(app, client, db):
    section, ta = _make_section_with_primary_ta()
    admin = User(display_name="Admin", role="admin")
    db.session.add(admin)
    db.session.commit()

    login_as(client, admin)
    resp = client.get("/api/sections")
    row = next(s for s in resp.get_json()["sections"] if s["id"] == section.id)
    assert row["ta_email"] == "primary@berkeley.edu"

    resp = client.get("/api/tas")
    row = next(t for t in resp.get_json()["tas"] if t["id"] == ta.id)
    assert row["email"] == "primary@berkeley.edu"


def test_ta_can_rename_own_section_but_not_someone_elses(app, client, db):
    section, ta = _make_section_with_primary_ta()
    other_ta = User(display_name="Other TA", role="ta")
    db.session.add(other_ta)
    db.session.commit()

    login_as(client, other_ta)
    resp = client.put(f"/api/sections/{section.id}/details", json={"name": "Hijacked"})
    assert resp.status_code == 403

    login_as(client, ta)
    resp = client.put(f"/api/sections/{section.id}/details", json={"name": "Renamed"})
    assert resp.status_code == 200
    assert resp.get_json()["section"]["name"] == "Renamed"


def test_primary_ta_can_add_a_co_teacher_by_email(app, client, db):
    section, ta = _make_section_with_primary_ta()
    co_ta = User(display_name="Co TA", role="ta", email="co@berkeley.edu")
    db.session.add(co_ta)
    db.session.commit()

    login_as(client, ta)
    resp = client.post(f"/api/sections/{section.id}/co-teachers", json={"email": "CO@berkeley.edu"})
    assert resp.status_code == 201
    co_teachers = resp.get_json()["co_teachers"]
    assert [c["id"] for c in co_teachers] == [co_ta.id]


def test_co_teacher_gets_full_section_access(app, client, db):
    section, ta = _make_section_with_primary_ta()
    co_ta = User(display_name="Co TA", role="ta", email="co@berkeley.edu")
    db.session.add(co_ta)
    db.session.flush()
    db.session.add(SectionCoTeacher(section_id=section.id, user_id=co_ta.id))
    db.session.commit()

    login_as(client, co_ta)
    # Shows up on their own "Discussions" list...
    resp = client.get("/api/sections")
    ids = {s["id"] for s in resp.get_json()["sections"]}
    assert section.id in ids

    # ...and grants the same management access as the primary TA everywhere
    # that already goes through ta_owns_section.
    resp = client.get(f"/api/sections/{section.id}/groups")
    assert resp.status_code == 200


def test_co_teacher_can_grant_further_co_authority(app, client, db):
    section, ta = _make_section_with_primary_ta()
    co_ta = User(display_name="Co TA", role="ta", email="co@berkeley.edu")
    second_co_ta = User(display_name="Second Co TA", role="ta", email="second@berkeley.edu")
    db.session.add_all([co_ta, second_co_ta])
    db.session.flush()
    db.session.add(SectionCoTeacher(section_id=section.id, user_id=co_ta.id))
    db.session.commit()

    login_as(client, co_ta)
    resp = client.post(f"/api/sections/{section.id}/co-teachers", json={"email": "second@berkeley.edu"})
    assert resp.status_code == 201
    assert {c["id"] for c in resp.get_json()["co_teachers"]} == {co_ta.id, second_co_ta.id}


def test_unrelated_ta_cannot_add_a_co_teacher(app, client, db):
    section, _ta = _make_section_with_primary_ta()
    outsider = User(display_name="Outsider", role="ta")
    target = User(display_name="Target", role="ta", email="target@berkeley.edu")
    db.session.add_all([outsider, target])
    db.session.commit()

    login_as(client, outsider)
    resp = client.post(f"/api/sections/{section.id}/co-teachers", json={"email": "target@berkeley.edu"})
    assert resp.status_code == 403


def test_add_co_teacher_rejects_unknown_or_non_ta_email(app, client, db):
    section, ta = _make_section_with_primary_ta()
    student = User(display_name="Student", role="student", email="student@berkeley.edu")
    db.session.add(student)
    db.session.commit()

    login_as(client, ta)
    resp = client.post(f"/api/sections/{section.id}/co-teachers", json={"email": "nobody@berkeley.edu"})
    assert resp.status_code == 404

    resp = client.post(f"/api/sections/{section.id}/co-teachers", json={"email": "student@berkeley.edu"})
    assert resp.status_code == 404


def test_remove_co_teacher_revokes_access(app, client, db):
    section, ta = _make_section_with_primary_ta()
    co_ta = User(display_name="Co TA", role="ta")
    db.session.add(co_ta)
    db.session.flush()
    db.session.add(SectionCoTeacher(section_id=section.id, user_id=co_ta.id))
    db.session.commit()

    login_as(client, ta)
    resp = client.delete(f"/api/sections/{section.id}/co-teachers/{co_ta.id}")
    assert resp.status_code == 200

    login_as(client, co_ta)
    resp = client.get(f"/api/sections/{section.id}/groups")
    assert resp.status_code == 403
