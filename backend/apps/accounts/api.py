"""Accounts & consent API — API_CONTRACTS.md §2.1–2.2."""

from uuid import UUID

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from ninja import Router
from ninja.security import django_auth

from apps.core.errors import ApiError
from apps.core.http import client_ip

from . import services
from .schemas import (
    AddChildIn,
    ApproveIn,
    ChildOut,
    ConsentLinkOut,
    LoginIn,
    MeOut,
    OkOut,
    OtpSendIn,
    OtpVerifyIn,
    ParentContactIn,
    ParentSignupIn,
    PasswordResetIn,
    StudentSignupIn,
)

BACKEND = "apps.accounts.backends.EmailOrMobileBackend"

auth_router = Router(tags=["auth"])
me_router = Router(tags=["auth"], auth=django_auth)
consent_router = Router(tags=["consent"])
parent_router = Router(tags=["parent"], auth=django_auth)


# --- §2.1 auth ------------------------------------------------------------------------


@auth_router.get("/csrf", response=dict)
def csrf(request):
    """Sets the CSRF cookie; the web app sends the token back in the X-CSRFToken header."""
    return {"csrf_token": get_token(request)}


@auth_router.post("/otp/send", response=OkOut)
def otp_send(request, payload: OtpSendIn):
    services.issue_otp(payload.destination, payload.purpose)
    return {"ok": True, "message": "If this contact is registered, a code has been sent."}


@auth_router.post("/otp/verify", response=MeOut)
def otp_verify(request, payload: OtpVerifyIn):
    if payload.purpose == "reset_password":
        raise ApiError(400, "validation_error", "Use /auth/password/reset for password resets.")
    user = services.check_otp(payload.destination, payload.purpose, payload.code)
    if payload.purpose == "login":
        login(request, user, backend=BACKEND)
    return services.me_payload(user)


@auth_router.post("/password/reset", response=OkOut)
def password_reset(request, payload: PasswordResetIn):
    services.reset_password(payload.destination, payload.code, payload.new_password)
    return {"ok": True, "message": "Password changed. You can log in now."}


@auth_router.post("/signup/student", response={201: MeOut})
def signup_student(request, payload: StudentSignupIn):
    user = services.signup_student(payload, ip=client_ip(request))
    login(request, user, backend=BACKEND)
    return 201, services.me_payload(user)


@auth_router.post("/signup/parent", response={201: MeOut})
def signup_parent(request, payload: ParentSignupIn):
    user = services.signup_parent(payload, ip=client_ip(request))
    login(request, user, backend=BACKEND)
    return 201, services.me_payload(user)


@auth_router.post("/login", response=MeOut)
def do_login(request, payload: LoginIn):
    identifier = payload.identifier.strip()
    try:
        identifier = services.normalize_contact(identifier)[1]
    except ApiError:
        pass  # let authentication fail normally
    user = authenticate(request, username=identifier, password=payload.password)
    if user is None:
        raise ApiError(400, "invalid_credentials", "Wrong email/mobile or password.")
    login(request, user, backend=BACKEND)
    return services.me_payload(user)


@auth_router.post("/logout", response=OkOut, auth=django_auth)
def do_logout(request):
    logout(request)
    return {"ok": True}


@me_router.get("", response=MeOut)
def me(request):
    return services.me_payload(request.user)


# --- §2.2 consent -------------------------------------------------------------------------


@consent_router.post("/requests/resend", response=OkOut, auth=django_auth)
def resend(request):
    services.resend_approval(request.user)
    return {"ok": True, "message": "Approval link sent again."}


@consent_router.patch("/requests/parent-contact", response=OkOut, auth=django_auth)
def change_parent_contact(request, payload: ParentContactIn):
    services.change_parent_contact(request.user, payload.parent_contact)
    return {"ok": True, "message": "A new approval link was sent."}


@consent_router.get("/link/{token}", response=ConsentLinkOut)
def link_details(request, token: str):
    req = services.get_request_for_token(token)
    text = services._current_consent_text()
    profile = req.student.student_profile
    return {
        "child_first_name": req.student.get_short_name(),
        "class_label": profile.class_level.label,
        "consent_version": text.version,
        "consent_text": text.body,
    }


@consent_router.post("/link/{token}/approve", response=OkOut, auth=django_auth)
def approve(request, token: str, payload: ApproveIn):
    if not payload.accept:
        raise ApiError(400, "validation_error", "Tick the consent box to approve.", {"accept": "required"})
    req = services.get_request_for_token(token)
    services.approve_request(req, request.user, payload.relationship, ip=client_ip(request))
    return {"ok": True, "message": "Approved. Your child can now start learning."}


@consent_router.post("/link/{token}/report", response=OkOut)
def report(request, token: str):
    req = services.get_request_for_token(token)
    services.report_request(req, ip=client_ip(request))
    return {"ok": True, "message": "Thank you. This request has been blocked."}


@parent_router.post("/children", response={201: ChildOut})
def add_child(request, payload: AddChildIn):
    child = services.add_child(request.user, payload, ip=client_ip(request))
    profile = child.student_profile
    return 201, {
        "id": child.pk,
        "full_name": child.full_name,
        "class_number": profile.class_level.number,
        "status": profile.status,
    }


@parent_router.post("/children/{child_id}/consent/withdraw", response=OkOut)
def withdraw(request, child_id: UUID):
    services.withdraw_consent(request.user, child_id, ip=client_ip(request))
    return {"ok": True, "message": "Consent withdrawn. The account is paused."}


@parent_router.post("/children/{child_id}/consent/restore", response=OkOut)
def restore(request, child_id: UUID):
    services.restore_consent(request.user, child_id, ip=client_ip(request))
    return {"ok": True, "message": "Consent restored."}
