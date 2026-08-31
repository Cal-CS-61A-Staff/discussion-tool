"""Class-level roster management + the course-wide join gate:
server/blueprints/sections.py (list/add/remove class students,
joinable_groups, _enrollment_blocks_join).
"""

from server.config import Config
from server.extensions import db
from server.models.group import Group, GroupMembership
from server.models.klass import Class, ClassEnrollment
from server.models.section import Section
from server.models.user import User
from server.tests.conftest import login_as


def _setup():
    ta = User(display_name="TA", role="ta")
    other_ta = User(display_name="Other", role="ta")
    db.session.add_all([ta, other_ta])
    db.session.flush()

    klass = Class(course_name="C")
    db.session.add(klass)
    db.session.flush()

    section = Section(class_id=klass.id, name="Mon 3pm", ta_user_id=ta.id)
    db.session.add(section)
    db.session.flush()

    group = Group(section_id=section.id, number=1, name="Group 1")
    db.session.add(group)
    db.session.commit()
    return {"ta": ta, "other_ta": other_ta, "klass": klass, "section": section, "group": group}


def test_ta_on_class_can_add_and_remove_students(app, client):
    s = _setup()
    login_as(client, s["ta"])
    cid = s["klass"].id

    resp = client.post(f"/api/classes/{cid}/students", json={"email": "Stu@Berkeley.edu", "name": "Stu"})
    assert resp.status_code == 200
    assert ClassEnrollment.query.filter_by(class_id=cid, student_email="stu@berkeley.edu").count() == 1
    # Named add also creates a placeholder account.
    assert User.query.filter_by(email="stu@berkeley.edu").first().display_name == "Stu"

    listed = client.get(f"/api/classes/{cid}/students").get_json()["students"]
    assert listed[0]["email"] == "stu@berkeley.edu"
    assert listed[0]["has_account"] is True and listed[0]["in_group"] is False

    resp = client.delete(f"/api/classes/{cid}/students", json={"email": "stu@berkeley.edu"})
    assert resp.status_code == 200
    assert ClassEnrollment.query.filter_by(class_id=cid).count() == 0


def test_ta_not_on_class_is_forbidden(app, client):
    s = _setup()
    login_as(client, s["other_ta"])
    cid = s["klass"].id
    assert client.get(f"/api/classes/{cid}/students").status_code == 403
    assert client.post(f"/api/classes/{cid}/students", json={"email": "x@berkeley.edu"}).status_code == 403


def test_course_roster_gates_joining_any_section(app, client):
    s = _setup()
    cid, sid, number = s["klass"].id, s["section"].id, s["group"].number

    # Roster has one student; a different student is blocked course-wide.
    db.session.add(ClassEnrollment(class_id=cid, student_email="rostered@berkeley.edu"))
    db.session.commit()

    outsider = User(display_name="Out", role="student", email="outsider@berkeley.edu")
    rostered = User(display_name="In", role="student", email="rostered@berkeley.edu")
    db.session.add_all([outsider, rostered])
    db.session.commit()

    login_as(client, outsider)
    resp = client.post(f"/api/sections/{sid}/groups/join", json={"number": number})
    assert resp.status_code == 403

    login_as(client, rostered)
    resp = client.post(f"/api/sections/{sid}/groups/join", json={"number": number})
    assert resp.status_code == 200


def test_class_with_no_roster_stays_open(app, client):
    s = _setup()
    sid, number = s["section"].id, s["group"].number
    anyone = User(display_name="Any", role="student", email="any@berkeley.edu")
    db.session.add(anyone)
    db.session.commit()

    login_as(client, anyone)
    resp = client.post(f"/api/sections/{sid}/groups/join", json={"number": number})
    assert resp.status_code == 200


def test_joinable_groups_reports_capacity(app, client):
    s = _setup()
    sid, gid = s["section"].id, s["group"].id
    for i in range(Config.MAX_GROUP_SIZE):
        u = User(display_name=f"u{i}", role="student")
        db.session.add(u)
        db.session.flush()
        db.session.add(GroupMembership(group_id=gid, user_id=u.id))
    db.session.commit()

    viewer = User(display_name="V", role="student", email="v@berkeley.edu")
    db.session.add(viewer)
    db.session.commit()
    login_as(client, viewer)

    groups = client.get(f"/api/sections/{sid}/groups/joinable").get_json()["groups"]
    assert len(groups) == 1
    assert groups[0]["capacity"] == Config.MAX_GROUP_SIZE
    assert groups[0]["is_full"] is True
