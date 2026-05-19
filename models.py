"""SQLAlchemy ORM models for Job Jockey"""

from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"
    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, nullable=False)
    email       = Column(String, unique=True, index=True, nullable=False)
    password    = Column(String, nullable=False)
    role        = Column(String, default="intern")          # admin | intern | super_admin
    permissions = Column(String, default="")               # comma-separated
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"
    id          = Column(Integer, primary_key=True, index=True)
    title       = Column(String, nullable=False)
    description = Column(Text, default="")
    assigned_to = Column(String, index=True)               # email of assignee
    status      = Column(String, default="Pending")        # Pending | In Progress | Completed
    priority    = Column(String, default="Medium")         # High | Medium | Low
    deadline    = Column(String, default="TBD")
    project     = Column(String, default="")
    created_by  = Column(String)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class Project(Base):
    __tablename__ = "projects"
    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, nullable=False)
    description = Column(Text, default="")
    status      = Column(String, default="In Progress")    # In Progress | Completed | Pending
    progress    = Column(Integer, default=0)               # 0–100
    color       = Column(String, default="#3b82f6")
    members     = Column(Text, default="")                 # JSON list of emails
    created_by  = Column(String)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class Candidate(Base):
    __tablename__ = "candidates"
    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, nullable=False)
    email      = Column(String, index=True)
    phone      = Column(String, default="")
    skill      = Column(String, default="")
    resume     = Column(String, default="")
    resume_link = Column(String, default="")               # Resume URL link
    status     = Column(String, default="Pending")
    state      = Column(String, default="")
    college    = Column(String, default="")
    edu_domain  = Column(String, default="")
    duration    = Column(String, default="")
    extra_data  = Column(Text, default="")   # JSON: extra CSV columns not in standard fields
    applied_at  = Column(DateTime(timezone=True), server_default=func.now())


class Attendance(Base):
    __tablename__ = "attendance"
    id     = Column(Integer, primary_key=True, index=True)
    email  = Column(String, index=True)
    date   = Column(String, index=True)                    # YYYY-MM-DD
    status = Column(String, default="Present")             # Present | Absent | Leave


class Report(Base):
    __tablename__ = "reports"
    id           = Column(Integer, primary_key=True, index=True)
    title        = Column(String, nullable=False)
    description  = Column(Text, default="")
    task_ref     = Column(String, default="")              # task title or id
    file_name    = Column(String, default="")
    file_data    = Column(Text, default="")                # base64 encoded file
    submitted_by = Column(String)
    reviewed     = Column(Boolean, default=False)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())


class Group(Base):
    __tablename__ = "groups"
    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, nullable=False)
    description = Column(Text, default="")
    icon        = Column(String, default="📁")
    members     = Column(Text, default="")                 # JSON list of emails
    created_by  = Column(String)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class Meeting(Base):
    __tablename__ = "meetings"
    id          = Column(Integer, primary_key=True, index=True)
    title       = Column(String, nullable=False)
    description = Column(Text, default="")
    date        = Column(String)                           # YYYY-MM-DD
    time        = Column(String)                           # HH:MM
    meet_link   = Column(String, default="")
    members     = Column(Text, default="[]")               # JSON list of emails invited
    created_by  = Column(String)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"
    id           = Column(Integer, primary_key=True, index=True)
    title        = Column(String, nullable=False)
    body         = Column(Text, default="")
    icon         = Column(String, default="🔔")
    target_email = Column(String, default="ALL")
    read         = Column(Boolean, default=False)
    seen_by      = Column(Text, default="[]")   # JSON list of emails who read it
    created_at   = Column(DateTime(timezone=True), server_default=func.now())


class WorkLog(Base):
    __tablename__ = "work_logs"
    id           = Column(Integer, primary_key=True, index=True)
    email        = Column(String, index=True)
    name         = Column(String, default="")
    login_time   = Column(String, default="")
    logout_time  = Column(String, default="")
    work_assigned= Column(Text, default="")
    work_did     = Column(Text, default="")
    hours_worked = Column(String, default="")
    issues       = Column(Text, default="")
    resolved     = Column(Text, default="")
    started_at   = Column(String, default="")
    completed_at = Column(String, default="")
    date         = Column(String, default="")   # YYYY-MM-DD
    created_at   = Column(DateTime(timezone=True), server_default=func.now())


class GroupMessage(Base):
    __tablename__ = "group_messages"
    id         = Column(Integer, primary_key=True, index=True)
    group_id   = Column(Integer, index=True)
    sender     = Column(String)                              # email
    message    = Column(Text, nullable=False)
    sent_at    = Column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id          = Column(Integer, primary_key=True, index=True)
    sender_id   = Column(Integer, index=True)
    receiver_id = Column(Integer, index=True)              # 0 = broadcast
    message     = Column(Text, nullable=False)
    sent_at     = Column(DateTime(timezone=True), server_default=func.now())


class Config(Base):
    __tablename__ = "config"
    key   = Column(String, primary_key=True)
    value = Column(Text, default="")