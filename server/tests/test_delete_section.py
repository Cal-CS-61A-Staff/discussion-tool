"""Covers deleting a section vs. deleting a whole class
(server/blueprints/admin.py:delete_section / delete_class). Assignments
belong to the class now (server/models/klass.py), not any one section, so
deleting a section must leave them untouched — only deleting the class
itself cascades to worksheets/questions; deleting a section only cascades
its own groups/co-teachers. The course roster (ClassEnrollment) belongs to
the class, so it survives a section delete and dies with the class.
"""

from server.extensions import db
from server.models.attempt import Attempt
from server.models.group import Group, GroupAssignmentProgress, GroupMembership, GroupQuestionState
from server.models.klass import Class, ClassEnrollment
from server.models.rating import Rating
from server.models.section import Section, SectionCoTeacher
from server.models.test_run import TestRun
from server.models.user import User
from server.models.worksheet import Question, Worksheet
from server.tests.conftest import login_as


def _make_full_class():
    ta = User(display_name="TA", role="ta")
    co_ta = User(display_name="Co TA", role="ta")
    student = User(display_name="Student", role="student")
    db.session.add_all([ta, co_ta, student])
    db.session.flush()

    klass = Class(course_name="C")
    db.session.add(klass)
    db.session.flush()

    section = Section(class_id=klass.id, name="S", ta_user_id=ta.id)
    db.session.add(section)
    db.session.flush()

    db.session.add(SectionCoTeacher(section_id=section.id, user_id=co_ta.id))
    db.session.add(ClassEnrollment(class_id=klass.id, student_email="student@x.com"))

    worksheet = Worksheet(class_id=klass.id, slug="w1", title="W1", is_published=True)
    db.session.add(worksheet)
    db.session.flush()
    question = Question(worksheet_id=worksheet.id, order_index=0, title="Q1", prompt="p")
    db.session.add(question)
    db.session.flush()

    group = Group(section_id=section.id, number=1, name="G1")
    db.session.add(group)
    db.session.flush()
    db.session.add(GroupMembership(group_id=group.id, user_id=student.id))
    db.session.add(GroupAssignmentProgress(group_id=group.id, worksheet_id=worksheet.id))
    db.session.add(GroupQuestionState(group_id=group.id, question_id=question.id))
    db.session.add(Rating(group_id=group.id, question_id=question.id, user_id=student.id, value=3))
    db.session.add(
        Attempt(
            group_id=group.id,
            question_id=question.id,
            user_id=student.id,
            prediction_text="x",
            is_match=True,
        )
    )
    db.session.add(
        TestRun(
            group_id=group.id,
            question_id=question.id,
            user_id=student.id,
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
    return klass, section, worksheet, question, group, ta


def test_delete_section_is_admin_only(app, client, db):
    _klass, section, *_rest, ta = _make_full_class()

    login_as(client, ta)
    resp = client.delete(f"/api/sections/{section.id}")
    assert resp.status_code == 403

    admin = User(display_name="Admin", role="admin")
    db.session.add(admin)
    db.session.commit()

    login_as(client, admin)
    resp = client.delete(f"/api/sections/{section.id}")
    assert resp.status_code == 200


def test_delete_section_cascades_its_groups_but_leaves_assignments(app, client, db):
    _klass, section, worksheet, question, group, _ta = _make_full_class()
    # Captured before any further commit: SQLAlchemy expires every
    # persistent instance in the session on commit, and the group rows are
    # about to be bulk-deleted (synchronize_session=False) rather than
    # individually db.session.delete()'d, so touching an attribute on the
    # stale in-memory object afterward (even .id) would raise
    # ObjectDeletedError instead of just returning the value.
    section_id, worksheet_id, question_id, group_id = section.id, worksheet.id, question.id, group.id

    admin = User(display_name="Admin", role="admin")
    db.session.add(admin)
    db.session.commit()

    login_as(client, admin)
    resp = client.delete(f"/api/sections/{section_id}")
    assert resp.status_code == 200

    assert db.session.get(Section, section_id) is None
    # The section's own groups and their history are gone...
    assert Group.query.filter_by(id=group_id).count() == 0
    assert GroupMembership.query.filter_by(group_id=group_id).count() == 0
    assert GroupAssignmentProgress.query.filter_by(group_id=group_id).count() == 0
    assert GroupQuestionState.query.filter_by(group_id=group_id).count() == 0
    assert Rating.query.filter_by(group_id=group_id).count() == 0
    assert Attempt.query.filter_by(group_id=group_id).count() == 0
    assert TestRun.query.filter_by(group_id=group_id).count() == 0
    assert SectionCoTeacher.query.filter_by(section_id=section_id).count() == 0
    # ...but the assignment and the course roster belong to the class, not
    # this section, so they must survive.
    assert db.session.get(Worksheet, worksheet_id) is not None
    assert db.session.get(Question, question_id) is not None
    assert ClassEnrollment.query.filter_by(student_email="student@x.com").count() == 1


def test_delete_class_is_admin_only(app, client, db):
    klass, *_rest, ta = _make_full_class()

    login_as(client, ta)
    resp = client.delete(f"/api/classes/{klass.id}")
    assert resp.status_code == 403

    admin = User(display_name="Admin", role="admin")
    db.session.add(admin)
    db.session.commit()

    login_as(client, admin)
    resp = client.delete(f"/api/classes/{klass.id}")
    assert resp.status_code == 200


def test_delete_class_cascades_everything(app, client, db):
    klass, section, worksheet, question, group, _ta = _make_full_class()
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
    resp = client.delete(f"/api/classes/{class_id}")
    assert resp.status_code == 200

    assert db.session.get(Class, class_id) is None
    assert Section.query.filter_by(id=section_id).count() == 0
    assert Worksheet.query.filter_by(id=worksheet_id).count() == 0
    assert Question.query.filter_by(id=question_id).count() == 0
    assert Group.query.filter_by(id=group_id).count() == 0
    assert GroupMembership.query.filter_by(group_id=group_id).count() == 0
    assert GroupAssignmentProgress.query.filter_by(group_id=group_id).count() == 0
    assert GroupQuestionState.query.filter_by(group_id=group_id).count() == 0
    assert Rating.query.filter_by(group_id=group_id).count() == 0
    assert Attempt.query.filter_by(group_id=group_id).count() == 0
    assert TestRun.query.filter_by(group_id=group_id).count() == 0
    assert SectionCoTeacher.query.filter_by(section_id=section_id).count() == 0
    assert ClassEnrollment.query.filter_by(class_id=class_id).count() == 0
