from typing import Annotated, Literal, Optional
from uuid import UUID

from ninja import Schema
from pydantic import StringConstraints, model_validator

# Input limits match the database columns, so over-long input is a clean 400, never a database error (500).
# Passwords are capped because hashing a huge password is an easy way to burn CPU (denial of service).
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
City = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
School = Annotated[str, StringConstraints(strip_whitespace=True, max_length=150)]
Password = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Contact = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=254)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10)]
BoardCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10)]
Language = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=10)]

OtpPurpose = Literal["verify_contact", "login", "reset_password"]
Relationship = Literal["mother", "father", "guardian", "other"]


class _NeedsContact(Schema):
    email: Optional[Contact] = None
    mobile: Optional[Contact] = None

    @model_validator(mode="after")
    def need_email_or_mobile(self):
        if not self.email and not self.mobile:
            raise ValueError("Enter an email or a mobile number.")
        return self


class OtpSendIn(Schema):
    destination: Contact
    purpose: OtpPurpose


class OtpVerifyIn(OtpSendIn):
    code: Code


class PasswordResetIn(Schema):
    destination: Contact
    code: Code
    new_password: Password


class StudentSignupIn(_NeedsContact):
    full_name: Name
    password: Password
    class_number: int
    board_code: BoardCode
    city: City
    school_name: School = ""
    parent_contact: Contact


class ParentSignupIn(_NeedsContact):
    full_name: Name
    password: Password
    preferred_language: Language = "en"


class LoginIn(Schema):
    identifier: Contact  # email or mobile
    password: Password


class AddChildIn(_NeedsContact):
    full_name: Name
    password: Password
    class_number: int
    board_code: BoardCode
    city: City
    school_name: School = ""
    relationship: Relationship = "guardian"


class ApproveIn(Schema):
    relationship: Relationship = "guardian"
    accept: bool


class ParentContactIn(Schema):
    parent_contact: Contact


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
    email: Optional[Contact] = None
    mobile: Optional[Contact] = None
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
