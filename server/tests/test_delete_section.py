"""Covers deleting a room vs. deleting a whole class
(server/blueprints/admin.py:delete_section / delete_class). Groups are
class-scoped now, so deleting a room only removes the room + its
co-teacher rows — groups, history and assignments all survive. Deleting
the class cascades everything.
"""

from server.extensions import db
from server.models.group import Group, GroupAssignmentProgress, GroupMembership, GroupQuestionState
from server.models.klass import Class, ClassMembership
from server.models.rating import Rating
from server.models.section import Section, SectionCoTeacher
from server.models.test_run import TestRun
from server.models.user import User
from server.models.worksheet import Question, Worksheet
from server.tests.conftest import add_member, login_as, make_class


def _make_full_class():
    staff = User(display_name="Staff", role="student")
    co_staff = User(display_name="Co Staff", role="student")
    student = User(display_name="Student", role="student")
    db.session.add_all([staff, co_staff, student])
    db.session.flush()

    klass = make_class("C")
    add_member(staff, klass, "staff")
    add_member(co_staff, klass, "staff")

    section = Section(class_id=klass.id, name="S", ta_user_id=staff.id)
    db.session.add(section)
    db.session.flush()
    db.session.add(SectionCoTeacher(section_id=section.id, user_id=co_staff.id))

    worksheet = Worksheet(class_id=klass.id, slug="w1", title="W1", is_published=True)
    db.session.add(worksheet)
    db.session.flush()
    question = Question(worksheet_id=worksheet.id, order_index=0, title="Q1", prompt="p")
    db.session.add(question)
    db.session.flush()

    group = Group(class_id=klass.id, number=1, name="G1")
    db.session.add(group)
    db.session.flush()
    db.session.add(GroupMembership(group_id=group.id, participant_key="p-stu", participant_name="Student"))
    db.session.add(GroupAssignmentProgress(group_id=group.id, worksheet_id=worksheet.id))
    db.session.add(GroupQuestionState(group_id=group.id, question_id=question.id))
    db.session.add(Rating(group_id=group.id, question_id=question.id, participant_key="p-stu", value=3))
    db.session.add(
        TestRun(
            group_id=group.id,
            question_id=question.id,
            participant_key="p-stu",
            source="shared",
            prediction_text="x",
            code_snapshot="x",
            status="done",
            passed_count=1,
            total_count=1,
            results_json="{}",
        )
    )
    db.session.commit()
    return klass, section, worksheet, question, group, staff


def test_delete_section_is_admin_only(app, client, db):
    _klass, section, *_rest, staff = _make_full_class()

    login_as(client, staff)
    assert client.delete(f"/api/sections/{section.id}").status_code == 403

    admin = User(display_name="Admin", role="admin")
    db.session.add(admin)
    db.session.commit()
    login_as(client, admin)
    assert client.delete(f"/api/sections/{section.id}").status_code == 200


def test_delete_section_leaves_groups_and_assignments(app, client, db):
    _klass, section, worksheet, question, group, _staff = _make_full_class()
    section_id, worksheet_id, question_id, group_id = section.id, worksheet.id, question.id, group.id

    admin = User(display_name="Admin", role="admin")
    db.session.add(admin)
    db.session.commit()

    login_as(client, admin)
    assert client.delete(f"/api/sections/{section_id}").status_code == 200

    assert db.session.get(Section, section_id) is None
    assert SectionCoTeacher.query.filter_by(section_id=section_id).count() == 0
    # Groups are class-scoped now — untouched by a room deletion.
    assert Group.query.filter_by(id=group_id).count() == 1
    assert GroupMembership.query.filter_by(group_id=group_id).count() == 1
    assert GroupAssignmentProgress.query.filter_by(group_id=group_id).count() == 1
    assert db.session.get(Worksheet, worksheet_id) is not None
    assert db.session.get(Question, question_id) is not None


def test_delete_class_is_admin_only(app, client, db):
    klass, *_rest, staff = _make_full_class()

    login_as(client, staff)
    assert client.delete(f"/api/classes/{klass.id}").status_code == 403

    admin = User(display_name="Admin", role="admin")
    db.session.add(admin)
    db.session.commit()
    login_as(client, admin)
    assert client.delete(f"/api/classes/{klass.id}").status_code == 200


def test_delete_class_cascades_everything(app, client, db):
    klass, section, worksheet, question, group, _staff = _make_full_class()
    class_id, section_id, worksheet_id, question_id, group_id = (
        klass.id,
        section.id,
        worksheet.id,
        question.id,
        group.id,
    )

    admin = User(display_name="Admin", role="admin")
    db.session.add(admin)
    db.session.commit()

    login_as(client, admin)
    assert client.delete(f"/api/classes/{class_id}").status_code == 200

    assert db.session.get(Class, class_id) is None
    assert Section.query.filter_by(id=section_id).count() == 0
    assert Worksheet.query.filter_by(id=worksheet_id).count() == 0
    assert Question.query.filter_by(id=question_id).count() == 0
    assert Group.query.filter_by(id=group_id).count() == 0
    assert GroupMembership.query.filter_by(group_id=group_id).count() == 0
    assert GroupAssignmentProgress.query.filter_by(group_id=group_id).count() == 0
    assert GroupQuestionState.query.filter_by(group_id=group_id).count() == 0
    assert Rating.query.filter_by(group_id=group_id).count() == 0
    assert TestRun.query.filter_by(group_id=group_id).count() == 0
    assert SectionCoTeacher.query.filter_by(section_id=section_id).count() == 0
    assert ClassMembership.query.filter_by(class_id=class_id).count() == 0
