"""Demo people: students in every consent state, parents, teachers and the four product admins.

All emails use the non-existent ``test.tutor`` domain and all mobiles the +91 90000 000xx range, so no real person can
receive a message. Everyone shares one password, given to ``build`` (from TUTOR_DEMO_PASSWORD on the hosted demo, the
local default in .env.example). Running again resets passwords, states, links and roles; it never duplicates.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from django.contrib.auth.models import Permission
from django.utils import timezone

from apps.accounts import services as account_services
from apps.accounts.models import (
    ApprovalRequest,
    ConsentRecord,
    ConsentText,
    GuardianLink,
    ParentProfile,
    RoleGrant,
    StudentProfile,
    TeacherProfile,
    User,
)
from apps.catalogue.models import Board, ClassLevel, Course, Programme, Subject
from apps.commerce.models import Entitlement

Role = RoleGrant.Role


@dataclass(frozen=True)
class Person:
    key: str
    name: str
    mobile: str
    email: str
    kind: str  # parent | student | teacher | staff
    # students
    class_number: int | None = None
    board: str | None = None
    city: str = "Kolkata"
    status: str | None = None  # active | awaiting_consent | paused
    parent: str | None = None
    relationship: str = "mother"
    entitlements: tuple = ()  # ("course" | "programme", slug)
    # teachers and admins: (role, subject slug or None, class number or None)
    roles: tuple = ()
    admin_access: tuple = ()  # Django model permissions for the back office ("app.codename")
    story: str = ""


CONTENT_PERMS = (
    "content.view_contentversion",
    "content.change_contentversion",
    "assessment.view_question",
    "assessment.view_questionversion",
    "assessment.change_questionversion",
    "catalogue.view_lesson",
    "catalogue.view_course",
)

PEOPLE = [
    # --- parents ---
    Person(
        "parent",
        "Test Parent",
        "+919000000001",
        "parent@test.tutor",
        "parent",
        story="Verified parent of Asha, Esha and Kabir",
    ),
    Person(
        "priya",
        "Priya Nair",
        "+919000000011",
        "priya@test.tutor",
        "parent",
        story="Parent of Meera (Class 11) and Zoya (Class 6)",
    ),
    Person(
        "rahul",
        "Rahul Das",
        "+919000000012",
        "rahul@test.tutor",
        "parent",
        story="Wasim's parent; Wasim's approval link was sent to this number and is still pending",
    ),
    Person(
        "farhan",
        "Farhan Ali",
        "+919000000013",
        "farhan@test.tutor",
        "parent",
        story="Withdrew consent for Rohan (account paused)",
    ),
    # --- students ---
    Person(
        "student_active",
        "Asha Active",
        "+919000000002",
        "asha@test.tutor",
        "student",
        8,
        "CBSE",
        status="active",
        parent="parent",
        story="Consent given, no purchases: free lessons only",
    ),
    Person(
        "student_enrolled",
        "Esha Enrolled",
        "+919000000003",
        "esha@test.tutor",
        "student",
        8,
        "CBSE",
        status="active",
        parent="parent",
        entitlements=(("course", "ai-foundations"),),
        story="Enrolled in AI Foundations; took one quiz",
    ),
    Person(
        "student_waiting",
        "Wasim Waiting",
        "+919000000004",
        "wasim@test.tutor",
        "student",
        8,
        "CBSE",
        status="awaiting_consent",
        parent="rahul",
        relationship="father",
        story="Waiting for parent approval: can browse only",
    ),
    Person(
        "kabir",
        "Kabir Sen",
        "+919000000021",
        "kabir@test.tutor",
        "student",
        8,
        "CBSE",
        status="active",
        parent="parent",
        relationship="father",
        entitlements=(("programme", "class-8-foundation"),),
        story="Class 8 Foundation programme; completed AI Foundations; weak on inverses; rich history",
    ),
    Person(
        "meera",
        "Meera Nair",
        "+919000000022",
        "meera@test.tutor",
        "student",
        11,
        "ICSE",
        city="Bengaluru",
        status="active",
        parent="priya",
        entitlements=(("course", "physics-class-11"),),
        story="Class 11 ICSE Physics, mid-way, 3-day streak",
    ),
    Person(
        "zoya",
        "Zoya Nair",
        "+919000000023",
        "zoya@test.tutor",
        "student",
        6,
        "CBSE",
        city="Bengaluru",
        status="active",
        parent="priya",
        entitlements=(("programme", "class-6-maths-start"),),
        story="Class 6 Maths, 5-day streak",
    ),
    Person(
        "rohan",
        "Rohan Ali",
        "+919000000024",
        "rohan@test.tutor",
        "student",
        8,
        "ICSE",
        status="paused",
        parent="farhan",
        relationship="father",
        entitlements=(("course", "mathematics-class-8"),),
        story="Consent withdrawn: account paused, history kept for 30 days",
    ),
    Person(
        "ishaan",
        "Ishaan Roy",
        "+919000000025",
        "ishaan@test.tutor",
        "student",
        11,
        "CBSE",
        city="Mumbai",
        status="active",
        parent="priya",
        relationship="guardian",
        story="Class 11, consent given, nothing bought yet",
    ),
    # --- teachers ---
    Person(
        "teacher",
        "Tara Teacher",
        "+919000000005",
        "tara@test.tutor",
        "teacher",
        roles=((Role.AUTHOR, "ai-foundations", None), (Role.REVIEWER, "ai-foundations", None)),
        story="Authors and reviews AI Foundations; cannot publish",
    ),
    Person(
        "vikram",
        "Vikram Rao",
        "+919000000031",
        "vikram@test.tutor",
        "teacher",
        roles=((Role.AUTHOR, "mathematics", 8),),
        story="Maths Class 8 author; has a version waiting for review",
    ),
    Person(
        "neha",
        "Neha Gupta",
        "+919000000032",
        "neha@test.tutor",
        "teacher",
        roles=((Role.REVIEWER, "mathematics", None), (Role.REVIEWER, "science", 8)),
        story="Reviews all Maths and Science Class 8",
    ),
    # --- product admins (roles, not Django superusers) ---
    Person(
        "ananya",
        "Ananya Iyer",
        "+919000000041",
        "ananya@test.tutor",
        "staff",
        roles=((Role.SUPER_ADMIN, None, None),),
        admin_access=(
            *CONTENT_PERMS,
            "accounts.view_user",
            "accounts.view_rolegrant",
            "accounts.add_rolegrant",
            "accounts.change_rolegrant",
            "commerce.view_entitlement",
            "operations.view_auditlog",
        ),
        story="Super admin: publishes anything, grants roles",
    ),
    Person(
        "lead",
        "Lalit Lead",
        "+919000000006",
        "lalit@test.tutor",
        "staff",
        roles=((Role.CURRICULUM_LEAD, "ai-foundations", None),),
        admin_access=CONTENT_PERMS,
        story="Curriculum lead, AI Foundations: publishes AI Foundations only",
    ),
    Person(
        "maya",
        "Maya Menon",
        "+919000000042",
        "maya@test.tutor",
        "staff",
        roles=((Role.CURRICULUM_LEAD, "mathematics", None),),
        admin_access=CONTENT_PERMS,
        story="Curriculum lead, Mathematics (all classes): has an approved version ready to publish",
    ),
    Person(
        "omar",
        "Omar Sheikh",
        "+919000000043",
        "omar@test.tutor",
        "staff",
        roles=((Role.OPERATIONS, None, None),),
        admin_access=(
            "accounts.view_user",
            "accounts.view_studentprofile",
            "accounts.view_guardianlink",
            "commerce.view_entitlement",
            "commerce.add_entitlement",
            "commerce.change_entitlement",
            "operations.view_auditlog",
        ),
        story="Operations: support look-ups and manual enrolments; cannot publish",
    ),
]

BY_KEY = {p.key: p for p in PEOPLE}


@dataclass
class PeopleReport:
    users: int = 0
    notes: list = field(default_factory=list)


def _upsert_user(p: Person, password: str, now):
    user = User.objects.filter(mobile=p.mobile).first() or User.objects.filter(email=p.email).first()
    if user is None:
        user = User(mobile=p.mobile)
    user.full_name, user.email, user.mobile, user.account_type = p.name, p.email, p.mobile, p.kind
    user.mobile_verified_at = user.email_verified_at = now
    user.is_active, user.deleted_at, user.is_superuser = True, None, False
    user.is_staff = bool(p.admin_access)
    user.set_password(password)
    user.save()
    return user


def _set_roles(user, p: Person, subjects, classes):
    wanted = {(role, subjects.get(s), classes.get(c)) for role, s, c in p.roles}
    for grant in RoleGrant.objects.filter(user=user, revoked_at__isnull=True):
        if (grant.role, grant.subject, grant.class_level) not in wanted:
            grant.revoked_at = timezone.now()
            grant.save(update_fields=["revoked_at"])
    for role, subject, class_level in wanted:
        RoleGrant.objects.get_or_create(user=user, role=role, subject=subject, class_level=class_level, revoked_at=None)


def _set_admin_access(user, p: Person):
    perms = []
    for dotted in p.admin_access:
        app, codename = dotted.split(".")
        perms.append(Permission.objects.get(content_type__app_label=app, codename=codename))
    user.user_permissions.set(perms)


def _link_parent(student, parent, p: Person, text, now):
    link = GuardianLink.objects.filter(parent=parent, student=student, ended_at__isnull=True).first()
    if link is None:
        link = GuardianLink.objects.create(parent=parent, student=student, relationship=p.relationship)
    consent = link.consents.order_by("-given_at").first()
    if p.status == "active":
        if consent is None or consent.withdrawn_at:
            ConsentRecord.objects.create(guardian_link=link, consent_text=text, given_ip="127.0.0.1")
    elif p.status == "paused":
        if consent is None:
            consent = ConsentRecord.objects.create(
                guardian_link=link, consent_text=text, given_ip="127.0.0.1", given_at=now - timedelta(days=40)
            )
        if not consent.withdrawn_at:
            consent.withdrawn_at = now - timedelta(days=3)
            consent.save(update_fields=["withdrawn_at"])


def _entitle(student, p: Person):
    wanted = set()
    for product_type, slug in p.entitlements:
        model = Course if product_type == "course" else Programme
        product_id = model.objects.get(slug=slug).id
        wanted.add((product_type, product_id))
        Entitlement.objects.get_or_create(
            student=student,
            product_type=product_type,
            product_id=product_id,
            revoked_at=None,
            defaults={"source": "admin_grant"},
        )
    for ent in Entitlement.objects.filter(student=student, revoked_at__isnull=True):
        if (ent.product_type, ent.product_id) not in wanted:
            ent.revoked_at = timezone.now()
            ent.save(update_fields=["revoked_at"])


def build(password: str) -> PeopleReport:
    now = timezone.now()
    report = PeopleReport()
    subjects = {s.slug: s for s in Subject.objects.all()}
    classes = {c.number: c for c in ClassLevel.objects.all()}
    boards = {b.code: b for b in Board.objects.all()}
    text = ConsentText.current()
    users = {}
    for p in PEOPLE:
        user = _upsert_user(p, password, now)
        users[p.key] = user
        report.users += 1
        if p.kind == "parent":
            ParentProfile.objects.get_or_create(user=user)
        if p.kind == "teacher":
            TeacherProfile.objects.update_or_create(user=user, defaults={"display_name": p.name})
        _set_roles(user, p, subjects, classes)
        _set_admin_access(user, p)

    for p in PEOPLE:
        if p.kind != "student":
            continue
        student = users[p.key]
        profile, _ = StudentProfile.objects.get_or_create(
            user=student, defaults={"class_level": classes[p.class_number], "board": boards[p.board], "city": p.city}
        )
        profile.class_level, profile.board, profile.city, profile.status = (
            classes[p.class_number],
            boards[p.board],
            p.city,
            p.status,
        )
        profile.save()
        if p.status == "awaiting_consent":
            parent = BY_KEY[p.parent]
            if not student.approval_requests.filter(status=ApprovalRequest.Status.SENT).exists():
                account_services.create_approval_request(student, "sms", parent.mobile)
        else:
            _link_parent(student, users[p.parent], p, text, now)
        _entitle(student, p)
    return report
