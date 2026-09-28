from typing import Literal, Optional
from uuid import UUID

from ninja import Schema
from pydantic import model_validator

OtpPurpose = Literal["verify_contact", "login", "reset_password"]
Relationship = Literal["mother", "father", "guardian", "other"]


class _NeedsContact(Schema):
    email: Optional[str] = None
    mobile: Optional[str] = None

    @model_validator(mode="after")
    def need_email_or_mobile(self):
        if not self.email and not self.mobile:
            raise ValueError("Enter an email or a mobile number.")
        return self


class OtpSendIn(Schema):
    destination: str
    purpose: OtpPurpose


class OtpVerifyIn(OtpSendIn):
    code: str


class PasswordResetIn(Schema):
    destination: str
    code: str
    new_password: str


class StudentSignupIn(_NeedsContact):
    full_name: str
    password: str
    class_number: int
    board_code: str
    city: str
    school_name: str = ""
    parent_contact: str


class ParentSignupIn(_NeedsContact):
    full_name: str
    password: str
    preferred_language: str = "en"


class LoginIn(Schema):
    identifier: str  # email or mobile
    password: str


class AddChildIn(_NeedsContact):
    full_name: str
    password: str
    class_number: int
    board_code: str
    city: str
    school_name: str = ""
    relationship: Relationship = "guardian"


class ApproveIn(Schema):
    relationship: Relationship = "guardian"
    accept: bool


class ParentContactIn(Schema):
    parent_contact: str


class StudentOut(Schema):
    class_number: int
    board: str
    city: str
    school_name: str
    status: str


class ParentOut(Schema):
    preferred_language: str
    notify_by: str


class ChildOut(Schema):
    id: UUID
    full_name: str
    class_number: int
    status: str


class RoleOut(Schema):
    role: str
    subject: Optional[str] = None
    class_number: Optional[int] = None


class MeOut(Schema):
    id: UUID
    full_name: str
    email: Optional[str] = None
    mobile: Optional[str] = None
    email_verified: bool
    mobile_verified: bool
    account_type: str
    student: Optional[StudentOut] = None
    parent: Optional[ParentOut] = None
    children: list[ChildOut] = []
    roles: list[RoleOut] = []


class ConsentLinkOut(Schema):
    child_first_name: str
    class_label: str
    consent_version: str
    consent_text: str


class OkOut(Schema):
    ok: bool = True
    message: str = ""
