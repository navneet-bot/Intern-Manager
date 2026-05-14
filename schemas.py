"""Pydantic schemas for request/response validation"""

from pydantic import BaseModel, EmailStr
from typing import Optional, Dict
from datetime import datetime


# ─── AUTH ────────────────────────────────────────
class RegisterUser(BaseModel):
    name: Optional[str] = None
    email: str
    password: str

class LoginIn(BaseModel):
    email: str
    password: str

class LoginOut(BaseModel):
    access_token: str
    user_id: int
    role: str
    name: str
    email: str
    permissions: Optional[str] = ""


# ─── USER ────────────────────────────────────────
class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    permissions: Optional[str] = ""

    class Config:
        from_attributes = True


# ─── TASK ────────────────────────────────────────
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    assigned_to: str
    status: Optional[str] = "Pending"
    priority: Optional[str] = "Medium"
    deadline: Optional[str] = "TBD"
    project: Optional[str] = ""

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    deadline: Optional[str] = None
    project: Optional[str] = None

class TaskOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = ""
    assigned_to: Optional[str] = ""
    status: str
    priority: str
    deadline: Optional[str] = "TBD"
    project: Optional[str] = ""
    created_by: Optional[str] = ""
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── PROJECT ─────────────────────────────────────
class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    status: Optional[str] = "In Progress"
    progress: Optional[int] = 0
    color: Optional[str] = "#3b82f6"
    members: Optional[str] = ""

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[int] = None
    color: Optional[str] = None
    members: Optional[str] = None

class ProjectOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = ""
    status: str
    progress: int
    color: str
    members: Optional[str] = ""
    created_by: Optional[str] = ""
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── CANDIDATE ───────────────────────────────────
class CandidateCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = ""
    skill: Optional[str] = ""
    resume: Optional[str] = ""
    state: Optional[str] = ""
    college: Optional[str] = ""
    edu_domain: Optional[str] = ""
    duration: Optional[str] = ""

class CandidateUpdate(BaseModel):
    status: Optional[str] = None
    phone: Optional[str] = None
    skill: Optional[str] = None
    state: Optional[str] = None
    college: Optional[str] = None
    edu_domain: Optional[str] = None
    duration: Optional[str] = None
    resume: Optional[str] = None

class CandidateOut(BaseModel):
    id: int
    name: str
    email: str
    phone: Optional[str] = ""
    skill: Optional[str] = ""
    resume: Optional[str] = ""
    status: str
    state: Optional[str] = ""
    college: Optional[str] = ""
    edu_domain: Optional[str] = ""
    duration: Optional[str] = ""
    applied_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GoogleFormImportRequest(BaseModel):
    sheet_id: str
    sheet_name: Optional[str] = None
    field_map: Optional[Dict[str, str]] = None
    status: Optional[str] = "Pending"
    skip_existing: Optional[bool] = True


# ─── WORK LOG ────────────────────────────────────
class WorkLogCreate(BaseModel):
    email: Optional[str] = ""
    name: Optional[str] = ""
    login_time: Optional[str] = ""
    logout_time: Optional[str] = ""
    work_assigned: Optional[str] = ""
    work_did: Optional[str] = ""
    hours_worked: Optional[str] = ""
    issues: Optional[str] = ""
    resolved: Optional[str] = ""
    started_at: Optional[str] = ""
    completed_at: Optional[str] = ""


# ─── ATTENDANCE ──────────────────────────────────
class AttendanceMark(BaseModel):
    date: str                       # YYYY-MM-DD
    status: str                     # Present | Absent | Leave
    email: Optional[str] = None     # admin can specify target

class AttendanceOut(BaseModel):
    id: int
    email: str
    date: str
    status: str

    class Config:
        from_attributes = True


# ─── REPORT ──────────────────────────────────────
class ReportCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    task_ref: Optional[str] = ""
    file_name: Optional[str] = ""
    file_data: Optional[str] = ""    # base64 encoded file content

class ReportOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = ""
    task_ref: Optional[str] = ""
    file_name: Optional[str] = ""
    file_data: Optional[str] = ""
    submitted_by: Optional[str] = ""
    reviewed: bool
    submitted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── GROUP ───────────────────────────────────────
class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    icon: Optional[str] = "📁"
    members: Optional[str] = ""

class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    members: Optional[str] = None

class GroupOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = ""
    icon: Optional[str] = "📁"
    members: Optional[str] = ""
    created_by: Optional[str] = ""
    created_at: Optional[datetime] = None
    message_count: Optional[int] = 0

    class Config:
        from_attributes = True


# ─── GROUP MESSAGE ───────────────────────────────
class GroupMessageCreate(BaseModel):
    message: str

class GroupMessageOut(BaseModel):
    id: int
    group_id: int
    sender: str
    message: str
    sent_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── MEETING ─────────────────────────────────────
class MeetingCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    date: str
    time: str
    meet_link: Optional[str] = ""
    members: Optional[str] = "[]"

class MeetingOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = ""
    date: str
    time: str
    meet_link: Optional[str] = ""
    members: Optional[str] = "[]"
    created_by: Optional[str] = ""
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── NOTIFICATION ────────────────────────────────
class NotificationCreate(BaseModel):
    title: str
    body: Optional[str] = ""
    icon: Optional[str] = "🔔"
    target_email: Optional[str] = "ALL"

class NotificationOut(BaseModel):
    id: int
    title: str
    body: Optional[str] = ""
    icon: Optional[str] = "🔔"
    target_email: str
    read: bool
    seen_by: Optional[str] = "[]"
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── CHAT ────────────────────────────────────────
class MessageCreate(BaseModel):
    receiver_id: int
    message: str

class MessageOut(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    message: str
    sent_at: Optional[datetime] = None

    class Config:
        from_attributes = True