"""Rooms (Section): admin-created, renamed + given a number spec by any
class staff, plus SectionCoTeacher — recording an extra staff member who
runs a room (folds that room's numbers into their dashboard watch-list
seed). Access to the class itself is the ClassMembership, not these rows.
"""

from server.extensions import db
from server.models.section import Section, SectionCoTeacher
from server.models.user import User
from server.tests.conftest import add_member, login_as, make_class


def _make_room():
    staff = User(display_name="Primary Staff", role="student", email="primary@berkeley.edu")
    db.session.add(staff)
    db.session.flush()
    klass = make_class("C")
    add_member(staff, klass, "staff")
    section = Section(class_id=klass.id, name="S", ta_user_id=staff.id)
    db.session.add(section)
    db.session.commit()
    return klass, section, staff


def test_admin_can_create_a_room(app, client, db):
    admin = User(display_name="Admin", role="admin")
    plain = User(display_name="Plain", role="student")
    klass = make_class("CS 61A")
    db.session.add_all([admin, plain])
    db.session.commit()

    login_as(client, plain)
    assert client.post("/api/sections", json={"class_id": klass.id, "name": "New"}).status_code == 403

    login_as(client, admin)
    resp = client.post("/api/sections", json={"class_id": klass.id, "name": "New"})
    assert resp.status_code == 201
    assert resp.get_json()["section"]["name"] == "New"
    assert resp.get_json()["section"]["ta_id"] is None


def test_section_list_exposes_room_details(app, client, db):
    klass, section, _staff = _make_room()
    admin = User(display_name="Admin", role="admin")
    db.session.add(admin)
    db.session.commit()

    login_as(client, admin)
    row = next(s for s in client.get("/api/sections").get_json()["sections"] if s["id"] == section.id)
    assert row["ta_email"] == "primary@berkeley.edu"
    assert row["assigned_numbers"] == ""


def test_class_staff_can_rename_room_and_set_numbers(app, client, db):
    klass, section, staff = _make_room()
    outsider = User(display_name="Outsider", role="student")
    db.session.add(outsider)
    db.session.commit()

    login_as(client, outsider)
    assert client.put(f"/api/sections/{section.id}/details", json={"name": "Hijacked"}).status_code == 403

    login_as(client, staff)
    resp = client.put(
        f"/api/sections/{section.id}/details", json={"name": "Renamed", "assigned_numbers": "3,1-2,10"}
    )
    assert resp.status_code == 200
    assert resp.get_json()["section"]["name"] == "Renamed"
    assert resp.get_json()["section"]["assigned_numbers"] == "1-3,10"


def test_add_co_teacher_requires_class_staff(app, client, db):
    klass, section, staff = _make_room()
    student = User(display_name="Student", role="student", email="student@berkeley.edu")
    co = User(display_name="Co", role="student", email="co@berkeley.edu")
    db.session.add_all([student, co])
    db.session.flush()
    add_member(co, klass, "staff")
    db.session.commit()

    login_as(client, staff)
    # unknown / not-class-staff emails are rejected
    assert client.post(f"/api/sections/{section.id}/co-teachers", json={"email": "nobody@berkeley.edu"}).status_code == 404
    assert client.post(f"/api/sections/{section.id}/co-teachers", json={"email": "student@berkeley.edu"}).status_code == 404

    # a class-staff email is accepted
    resp = client.post(f"/api/sections/{section.id}/co-teachers", json={"email": "CO@berkeley.edu"})
    assert resp.status_code == 201
    assert [c["id"] for c in resp.get_json()["co_teachers"]] == [co.id]


def test_unrelated_user_cannot_add_a_co_teacher(app, client, db):
    _klass, section, _staff = _make_room()
    outsider = User(display_name="Outsider", role="student")
    db.session.add(outsider)
    db.session.commit()

    login_as(client, outsider)
    assert client.post(f"/api/sections/{section.id}/co-teachers", json={"email": "x@berkeley.edu"}).status_code == 403


def test_remove_co_teacher(app, client, db):
    klass, section, staff = _make_room()
    co = User(display_name="Co", role="student")
    db.session.add(co)
    db.session.flush()
    add_member(co, klass, "staff")
    db.session.add(SectionCoTeacher(section_id=section.id, user_id=co.id))
    db.session.commit()

    login_as(client, staff)
    assert client.delete(f"/api/sections/{section.id}/co-teachers/{co.id}").status_code == 200
    assert SectionCoTeacher.query.filter_by(section_id=section.id).count() == 0
