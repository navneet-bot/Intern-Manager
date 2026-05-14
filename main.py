"""
Job Jockey — FastAPI Backend (Final Version 3.1)
Roles: admin (boss) > super_admin > intern
"""

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from typing import Optional, List, Dict, Any
from pathlib import Path
import csv, json, re, os, smtplib, urllib.parse, urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi.staticfiles import StaticFiles
from database import SessionLocal, engine
import models, schemas
from permissions import has_permission

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Job Jockey API", version="3.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="."), name="static")

SECRET_KEY    = "JOBJOCKEY_SECRET_2025"
ALGORITHM     = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

# ── DB ───────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:    yield db
    finally: db.close()

# ── JWT — NO EXPIRY so refresh never logs out ────
def create_token(user_id: int, email: str, role: str) -> str:
    return jwt.encode({"sub": str(user_id), "email": email, "role": role}, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    if not token: raise HTTPException(401, "Not authenticated")
    try:
        payload  = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id  = int(payload.get("sub", 0))
    except (JWTError, ValueError): raise HTTPException(401, "Invalid token")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user: raise HTTPException(401, "User not found")
    return user

def require_admin(user: models.User = Depends(get_current_user)):
    if user.role != "admin": raise HTTPException(403, "Admin access required")
    return user

def require_boss(user: models.User = Depends(get_current_user)):
    if user.role != "admin": raise HTTPException(403, "Only admin (boss) can do this")
    return user

def require_permission(permission: str):
    def checker(user: models.User = Depends(get_current_user)):
        if not has_permission(user, permission):
            raise HTTPException(403, "No permission")
        return user
    return checker

# ── WebSocket ────────────────────────────────────
class ConnectionManager:
    def __init__(self): self.active: dict[int, WebSocket] = {}
    async def connect(self, uid, ws): await ws.accept(); self.active[uid] = ws
    def disconnect(self, uid): self.active.pop(uid, None)
    async def send_to(self, uid, data):
        ws = self.active.get(uid)
        if ws:
            try: await ws.send_json(data)
            except: self.disconnect(uid)
    async def broadcast(self, data):
        for uid, ws in list(self.active.items()):
            try: await ws.send_json(data)
            except: self.disconnect(uid)

manager = ConnectionManager()

# ── Email helper ─────────────────────────────────
def send_welcome_email(to_email: str, name: str, jj_email: str, password: str):
    SENDER_EMAIL    = os.getenv("JJ_EMAIL", "")
    SENDER_PASSWORD = os.getenv("JJ_EMAIL_PASS", "")
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print(f"⚠️  Email not configured. Credentials for {name}: {jj_email} / {password}")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🎉 Welcome to Job Jockey — Your Login Credentials"
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = to_email
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#0f172a;color:#e2e8f0;border-radius:12px;overflow:hidden">
      <div style="background:#f59e0b;padding:24px;text-align:center">
        <h1 style="margin:0;color:#000;font-size:24px">Job <span style="color:#1e293b">Jockey</span></h1>
        <p style="margin:4px 0 0;color:#1e293b;font-size:13px">Intern Management Platform</p>
      </div>
      <div style="padding:32px">
        <h2 style="color:#f59e0b;margin-top:0">Welcome aboard, {name}! 🎉</h2>
        <p style="color:#94a3b8">Your application has been <strong style="color:#10b981">approved</strong>. Log in with:</p>
        <div style="background:#1e293b;border:1px solid #334155;border-radius:10px;padding:20px;margin:20px 0">
          <div style="margin-bottom:12px">
            <span style="color:#64748b;font-size:12px">Platform Email</span><br>
            <strong style="color:#f59e0b;font-size:16px">📧 {jj_email}</strong>
          </div>
          <div>
            <span style="color:#64748b;font-size:12px">Password</span><br>
            <strong style="color:#f59e0b;font-size:16px">🔑 {password}</strong>
          </div>
        </div>
        <p style="color:#94a3b8;font-size:13px">Please change your password after first login.</p>
        <p style="color:#64748b;font-size:12px;margin-top:24px">— Job Jockey Team</p>
      </div>
    </div>"""
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
            print(f"✅ Welcome email sent to {to_email}")
    except Exception as e:
        print(f"❌ Email failed: {e}")


def fetch_google_form_responses(sheet_id: str, sheet_name: Optional[str] = None) -> List[Dict[str, str]]:
    if not sheet_id:
        raise ValueError("sheet_id is required")
    sheet_name_param = f"&sheet={urllib.parse.quote(sheet_name)}" if sheet_name else ""
    url = f"https://docs.google.com/spreadsheets/d/{urllib.parse.quote(sheet_id)}/gviz/tq?tqx=out:csv{sheet_name_param}"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            if response.status != 200:
                raise ValueError(f"Google Sheets request failed with status {response.status}")
            text = response.read().decode("utf-8")
    except Exception as exc:
        raise ValueError(f"Failed to fetch Google Forms responses: {exc}")

    lines = text.splitlines()
    if not lines:
        return []
    reader = csv.DictReader(lines)
    return [dict((k, (v or "").strip()) for k, v in row.items()) for row in reader]


@app.get("/")
def root():
    return FileResponse("index.html")

# ════════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════════
@app.post("/register-admin")
def register_admin(data: schemas.RegisterUser, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.role == "admin").first(): raise HTTPException(400, "Admin already exists")
    if db.query(models.User).filter(models.User.email == data.email).first(): raise HTTPException(400, "Email already registered")
    user = models.User(name=data.name or data.email.split("@")[0], email=data.email, password=data.password, role="admin", permissions="all")
    db.add(user); db.commit(); db.refresh(user)
    return {"msg": "Admin created", "id": user.id}

@app.post("/register-intern")
def register_intern(data: schemas.RegisterUser, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == data.email).first(): raise HTTPException(400, "Email already registered")
    user = models.User(name=data.name or data.email.split("@")[0], email=data.email, password=data.password, role="intern", permissions="")
    db.add(user); db.commit(); db.refresh(user)
    return {"msg": "Intern created", "id": user.id}

@app.post("/login", response_model=schemas.LoginOut)
def login(data: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == data.email).first()
    if not user or user.password != data.password: raise HTTPException(400, "Invalid email or password")
    return schemas.LoginOut(
        access_token=create_token(user.id, user.email, user.role),
        user_id=user.id, role=user.role, name=user.name,
        email=user.email, permissions=user.permissions or ""
    )

# ════════════════════════════════════════════════
# USERS
# ════════════════════════════════════════════════
@app.get("/users", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(models.User).all()

@app.get("/users/interns", response_model=List[schemas.UserOut])
def list_interns(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(models.User).filter(models.User.role == "intern").all()

@app.get("/users/me", response_model=schemas.UserOut)
def me(user=Depends(get_current_user)): return user

@app.patch("/users/{user_id}/promote")
def promote(user_id: int, db: Session = Depends(get_db), user=Depends(require_boss)):
    t = db.query(models.User).filter(models.User.id == user_id).first()
    if not t: raise HTTPException(404, "Not found")
    if t.role == "admin": raise HTTPException(400, "Cannot change admin")
    t.role = "super_admin"
    # Keep any permissions already assigned by the frontend; do not grant all by default.
    db.commit()
    return {"msg": f"{t.name} promoted to Super Admin"}

@app.patch("/users/{user_id}/demote")
def demote(user_id: int, db: Session = Depends(get_db), user=Depends(require_boss)):
    t = db.query(models.User).filter(models.User.id == user_id).first()
    if not t: raise HTTPException(404, "Not found")
    if t.role == "admin": raise HTTPException(400, "Cannot change admin")
    t.role = "intern"; t.permissions = ""
    db.commit()
    return {"msg": f"{t.name} demoted to Intern"}

@app.patch("/users/{user_id}/permissions")
def set_perms(user_id: int, data: dict, db: Session = Depends(get_db), user=Depends(require_boss)):
    t = db.query(models.User).filter(models.User.id == user_id).first()
    if not t: raise HTTPException(404, "Not found")
    t.permissions = data.get("permissions", ""); db.commit()
    return {"msg": "Updated"}

@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), user=Depends(require_boss)):
    t = db.query(models.User).filter(models.User.id == user_id).first()
    if not t: raise HTTPException(404, "Not found")
    if t.role == "admin": raise HTTPException(400, "Cannot delete admin")
    db.delete(t); db.commit()
    return {"msg": "Deleted"}

# ════════════════════════════════════════════════
# TASKS
# ════════════════════════════════════════════════
def can_create_task(user): return has_permission(user, "create_task")

def can_view_all_tasks(user):
    return user.role == "admin" or any(has_permission(user, p) for p in ["create_task", "delete_task", "view_reports"])

@app.post("/tasks", response_model=schemas.TaskOut)
def create_task(data: schemas.TaskCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not can_create_task(user): raise HTTPException(403, "No permission")
    assignee = db.query(models.User).filter(models.User.email == data.assigned_to).first()
    if assignee and user.role == "super_admin" and assignee.role != "intern":
        raise HTTPException(403, "Super admin can only assign to interns")
    task = models.Task(**data.dict(), created_by=user.email)
    db.add(task); db.commit(); db.refresh(task)
    if assignee:
        db.add(models.Notification(
            title=f"📋 New Task: {data.title}",
            body=f"Assigned to you. Priority: {data.priority}. Deadline: {data.deadline or 'TBD'}",
            icon="📋", target_email=assignee.email
        ))
        db.commit()
    return task

@app.get("/tasks", response_model=List[schemas.TaskOut])
def get_tasks(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if can_view_all_tasks(user): return db.query(models.Task).all()
    return db.query(models.Task).filter(models.Task.assigned_to == user.email).all()

@app.patch("/tasks/{task_id}", response_model=schemas.TaskOut)
def update_task(task_id: int, data: schemas.TaskUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task: raise HTTPException(404, "Not found")
    if user.role == "intern" and task.assigned_to != user.email: raise HTTPException(403, "Not your task")
    for k, v in data.dict(exclude_none=True).items(): setattr(task, k, v)
    db.commit(); db.refresh(task); return task

@app.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not has_permission(user, "delete_task"):
        raise HTTPException(403, "No permission")
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task: raise HTTPException(404, "Not found")
    db.delete(task); db.commit(); return {"msg": "Deleted"}

# ════════════════════════════════════════════════
# PROJECTS
# ════════════════════════════════════════════════
@app.post("/projects", response_model=schemas.ProjectOut)
def create_project(data: schemas.ProjectCreate, db: Session = Depends(get_db), user=Depends(require_permission("manage_projects"))):
    p = models.Project(**data.dict(), created_by=user.email)
    db.add(p); db.commit(); db.refresh(p); return p

@app.get("/projects", response_model=List[schemas.ProjectOut])
def get_projects(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(models.Project).all()

@app.patch("/projects/{pid}", response_model=schemas.ProjectOut)
def update_project(pid: int, data: schemas.ProjectUpdate, db: Session = Depends(get_db), user=Depends(require_permission("manage_projects"))):
    p = db.query(models.Project).filter(models.Project.id == pid).first()
    if not p: raise HTTPException(404, "Not found")
    for k, v in data.dict(exclude_none=True).items(): setattr(p, k, v)
    db.commit(); db.refresh(p); return p

@app.delete("/projects/{pid}")
def delete_project(pid: int, db: Session = Depends(get_db), user=Depends(require_boss)):
    p = db.query(models.Project).filter(models.Project.id == pid).first()
    if not p: raise HTTPException(404, "Not found")
    db.delete(p); db.commit(); return {"msg": "Deleted"}

# ════════════════════════════════════════════════
# CANDIDATES
# ════════════════════════════════════════════════
@app.post("/candidates", response_model=schemas.CandidateOut)
def add_candidate(data: schemas.CandidateCreate, db: Session = Depends(get_db)):
    c = models.Candidate(**data.dict()); db.add(c); db.commit(); db.refresh(c); return c

@app.get("/candidates", response_model=List[schemas.CandidateOut])
def get_candidates(db: Session = Depends(get_db), user=Depends(require_permission("manage_candidates"))):
    return db.query(models.Candidate).all()

@app.get("/google-forms/responses")
def google_forms_responses(
    sheet_id: str,
    sheet_name: Optional[str] = None,
    user=Depends(require_permission("manage_candidates"))
):
    if sheet_id.lower() == "e" or len(sheet_id) < 20:
        raise HTTPException(400, "Invalid Google Sheets ID. Use the response spreadsheet URL, not the Google Form link.")
    try:
        rows = fetch_google_form_responses(sheet_id, sheet_name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"sheet_id": sheet_id, "sheet_name": sheet_name or "default", "count": len(rows), "responses": rows}

@app.post("/google-forms/import-candidates")
def import_google_form_candidates(data: schemas.GoogleFormImportRequest, db: Session = Depends(get_db), user=Depends(require_permission("manage_candidates"))):
    try:
        rows = fetch_google_form_responses(data.sheet_id, data.sheet_name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    field_map = data.field_map or {}
    created = []
    skipped = []
    for row in rows:
        name = row.get(field_map.get("name", "Name"), "").strip()
        email = row.get(field_map.get("email", "Email"), "").strip()
        if not name or not email:
            skipped.append({"reason": "missing name or email", "row": row})
            continue
        if data.skip_existing and db.query(models.Candidate).filter(models.Candidate.email == email).first():
            skipped.append({"reason": "email exists", "email": email})
            continue
        candidate = models.Candidate(
            name=name,
            email=email,
            phone=row.get(data.field_map.get("phone", "Phone"), "").strip(),
            skill=row.get(data.field_map.get("skill", "Skill"), "").strip(),
            state=row.get(data.field_map.get("state", "State"), "").strip(),
            college=row.get(data.field_map.get("college", "College"), "").strip(),
            edu_domain=row.get(data.field_map.get("edu_domain", "Education Domain"), "").strip(),
            duration=row.get(data.field_map.get("duration", "Duration"), "").strip(),
            resume=row.get(data.field_map.get("resume", "Resume"), "").strip(),
            status=data.status or "Pending"
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        created.append({"id": candidate.id, "name": candidate.name, "email": candidate.email})

    return {"created": created, "skipped": skipped, "total_rows": len(rows)}

@app.patch("/candidates/{cid}", response_model=schemas.CandidateOut)
def update_candidate(cid: int, data: schemas.CandidateUpdate, db: Session = Depends(get_db), user=Depends(require_permission("manage_candidates"))):
    c = db.query(models.Candidate).filter(models.Candidate.id == cid).first()
    if not c: raise HTTPException(404, "Not found")
    for k, v in data.dict(exclude_none=True).items(): setattr(c, k, v)
    db.commit(); db.refresh(c)

    if data.status == "Approved":
        # Auto-generate jobjockey.in email from name
        # "Rahul Sharma" -> "rahul.sharma@jobjockey.in"
        clean = re.sub(r"[^a-zA-Z\s]", "", c.name).strip().lower()
        parts = clean.split()
        base_email = f"{parts[0]}.{parts[-1]}@jobjockey.in" if len(parts) >= 2 else f"{parts[0]}@jobjockey.in" if parts else f"intern@jobjockey.in"
        base = base_email.replace("@jobjockey.in", "")
        jj_email = base_email
        suffix = 1
        while db.query(models.User).filter(models.User.email == jj_email).first():
            jj_email = f"{base}{suffix}@jobjockey.in"
            suffix += 1

        password = "123"

        # Create intern user account
        if not db.query(models.User).filter(models.User.email == jj_email).first():
            db.add(models.User(name=c.name, email=jj_email, password=password, role="intern", permissions=""))
            db.commit()

        # Store credentials in resume field so frontend can display them
        c.resume = f"LOGIN:{jj_email}|PASS:{password}"
        db.commit(); db.refresh(c)

        # Send welcome email to personal email (non-blocking)
        try:
            send_welcome_email(to_email=c.email, name=c.name, jj_email=jj_email, password=password)
        except Exception as e:
            print(f"Email error: {e}")

    return c

@app.delete("/candidates/{cid}/credentials")
def revoke_credentials(cid: int, db: Session = Depends(get_db), user=Depends(require_boss)):
    """Delete only the login credentials — candidate data remains."""
    c = db.query(models.Candidate).filter(models.Candidate.id == cid).first()
    if not c: raise HTTPException(404, "Not found")

    deleted = False
    if c.resume and c.resume.startswith("LOGIN:"):
        jj_email = c.resume.replace("LOGIN:", "").split("|PASS:")[0]
        intern_user = db.query(models.User).filter(models.User.email == jj_email).first()
        if intern_user and intern_user.role == "intern":
            db.delete(intern_user)
            deleted = True

    # Clear credentials from resume field but keep candidate record
    c.resume = ""
    c.status = "Rejected"
    db.commit()
    return {"msg": f"Credentials revoked. Candidate data remains.", "deleted_user": deleted}

@app.delete("/candidates/{cid}")
def delete_candidate(cid: int, db: Session = Depends(get_db), user=Depends(require_boss)):
    """Delete candidate record but keep their login account if they have one."""
    c = db.query(models.Candidate).filter(models.Candidate.id == cid).first()
    if not c: raise HTTPException(404, "Not found")

    # Only delete candidate record — login account stays
    db.delete(c)
    db.commit()
    return {"msg": "Candidate deleted. Login credentials remain active."}

# ════════════════════════════════════════════════
# ATTENDANCE
# ════════════════════════════════════════════════
@app.post("/attendance", response_model=schemas.AttendanceOut)
def mark_attendance(data: schemas.AttendanceMark, db: Session = Depends(get_db), user=Depends(get_current_user)):
    target = data.email if data.email else user.email
    if target != user.email and not has_permission(user, "manage_attendance"):
        raise HTTPException(403, "No permission")
    existing = db.query(models.Attendance).filter(
        models.Attendance.email == target,
        models.Attendance.date  == data.date
    ).first()
    if existing:
        existing.status = data.status; db.commit(); db.refresh(existing); return existing
    a = models.Attendance(email=target, date=data.date, status=data.status)
    db.add(a); db.commit(); db.refresh(a); return a

@app.get("/attendance", response_model=List[schemas.AttendanceOut])
def get_attendance(date: Optional[str] = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(models.Attendance)
    if user.role == "intern": q = q.filter(models.Attendance.email == user.email)
    if date: q = q.filter(models.Attendance.date == date)
    return q.all()

# ════════════════════════════════════════════════
# REPORTS
# ════════════════════════════════════════════════
@app.post("/reports", response_model=schemas.ReportOut)
def submit_report(data: schemas.ReportCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    r = models.Report(**data.dict(), submitted_by=user.email)
    db.add(r); db.commit(); db.refresh(r)
    for admin in db.query(models.User).filter(models.User.role.in_(["admin","super_admin"])).all():
        db.add(models.Notification(
            title=f"📄 New Report from {user.name}",
            body=f"'{data.title}' submitted. Click Reports to review.",
            icon="📄", target_email=admin.email
        ))
    db.commit(); return r

@app.get("/reports", response_model=List[schemas.ReportOut])
def get_reports(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role == "intern":
        return db.query(models.Report).filter(models.Report.submitted_by == user.email).all()
    if not has_permission(user, "view_reports"):
        raise HTTPException(403, "No permission")
    return db.query(models.Report).all()

@app.patch("/reports/{rid}")
def review_report(rid: int, db: Session = Depends(get_db), user=Depends(require_permission("view_reports"))):
    r = db.query(models.Report).filter(models.Report.id == rid).first()
    if not r: raise HTTPException(404, "Not found")
    r.reviewed = True; db.commit(); return {"msg": "Reviewed"}

# ════════════════════════════════════════════════
# GROUPS
# ════════════════════════════════════════════════
@app.post("/groups", response_model=schemas.GroupOut)
def create_group(data: schemas.GroupCreate, db: Session = Depends(get_db), user=Depends(require_permission("manage_groups"))):
    g = models.Group(**data.dict(), created_by=user.email)
    db.add(g); db.commit(); db.refresh(g); return g

@app.get("/groups", response_model=List[schemas.GroupOut])
def get_groups(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(models.Group).all()

@app.patch("/groups/{gid}/members")
def update_group_members(gid: int, data: dict, db: Session = Depends(get_db), user=Depends(require_permission("manage_groups"))):
    g = db.query(models.Group).filter(models.Group.id == gid).first()
    if not g: raise HTTPException(404, "Not found")
    g.members = json.dumps(data.get("members", []))
    db.commit(); db.refresh(g)
    return {"msg": "Members updated", "members": data.get("members", [])}

@app.delete("/groups/{gid}")
def delete_group(gid: int, db: Session = Depends(get_db), user=Depends(require_boss)):
    g = db.query(models.Group).filter(models.Group.id == gid).first()
    if not g: raise HTTPException(404, "Not found")
    db.delete(g); db.commit(); return {"msg": "Deleted"}

# ════════════════════════════════════════════════
# MEETINGS
# ════════════════════════════════════════════════
def is_valid_meet_link(url: str) -> bool:
    if not url: return True
    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False
        if not parsed.netloc:
            return False
        return "meet.google.com" in parsed.netloc.lower()
    except Exception:
        return False

@app.post("/meetings", response_model=schemas.MeetingOut)
def create_meeting(data: schemas.MeetingCreate, db: Session = Depends(get_db), user=Depends(require_permission("manage_meetings"))):
    if data.meet_link and not is_valid_meet_link(data.meet_link):
        raise HTTPException(400, "Enter a valid Google Meet URL")
    m = models.Meeting(**data.dict(), created_by=user.email)
    db.add(m); db.commit(); db.refresh(m)
    try:    member_emails = json.loads(data.members or "[]")
    except: member_emails = []
    for email in member_emails:
        db.add(models.Notification(
            title=f"📅 Meeting Invite: {data.title}",
            body=f"On {data.date} at {data.time or 'TBD'}. Link: {data.meet_link or 'TBD'}",
            icon="📅", target_email=email
        ))
    if member_emails: db.commit()
    return m

@app.get("/meetings", response_model=List[schemas.MeetingOut])
def get_meetings(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role == "intern":
        meetings = db.query(models.Meeting).all()
        filtered = []
        for m in meetings:
            try:
                members = json.loads(m.members or "[]")
            except Exception:
                members = []
            if user.email in members:
                filtered.append(m)
        return filtered
    if has_permission(user, "manage_meetings"):
        return db.query(models.Meeting).all()
    meetings = db.query(models.Meeting).all()
    filtered = []
    for m in meetings:
        try:
            members = json.loads(m.members or "[]")
        except Exception:
            members = []
        if user.email in members or m.created_by == user.email:
            filtered.append(m)
    return filtered

@app.patch("/meetings/{mid}", response_model=schemas.MeetingOut)
def update_meeting(mid: int, data: dict, db: Session = Depends(get_db), user=Depends(require_permission("manage_meetings"))):
    m = db.query(models.Meeting).filter(models.Meeting.id == mid).first()
    if not m: raise HTTPException(404, "Not found")
    for k, v in data.items():
        if hasattr(m, k): setattr(m, k, v)
    db.commit(); db.refresh(m); return m

@app.delete("/meetings/{mid}")
def delete_meeting(mid: int, db: Session = Depends(get_db), user=Depends(require_boss)):
    m = db.query(models.Meeting).filter(models.Meeting.id == mid).first()
    if not m: raise HTTPException(404, "Not found")
    db.delete(m); db.commit(); return {"msg": "Deleted"}

# ════════════════════════════════════════════════
# NOTIFICATIONS
# ════════════════════════════════════════════════
@app.post("/notifications", response_model=schemas.NotificationOut)
def create_notification(data: schemas.NotificationCreate, db: Session = Depends(get_db), user=Depends(require_permission("send_notifications"))):
    n = models.Notification(**data.dict())
    db.add(n); db.commit(); db.refresh(n); return n

@app.get("/notifications", response_model=List[schemas.NotificationOut])
def get_notifications(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(models.Notification).filter(
        (models.Notification.target_email == user.email) |
        (models.Notification.target_email == "ALL")
    ).order_by(models.Notification.id.desc()).all()

@app.patch("/notifications/{nid}/read")
def mark_read(nid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    n = db.query(models.Notification).filter(models.Notification.id == nid).first()
    if not n: raise HTTPException(404, "Not found")
    n.read = True
    # Track who read it
    try:
        seen = json.loads(n.seen_by or "[]")
    except:
        seen = []
    if user.email not in seen:
        seen.append(user.email)
        n.seen_by = json.dumps(seen)
    db.commit()
    return {"msg": "Read"}

@app.get("/notifications/{nid}/seen-by")
def get_seen_by(nid: int, db: Session = Depends(get_db), user=Depends(require_permission("send_notifications"))):
    n = db.query(models.Notification).filter(models.Notification.id == nid).first()
    if not n: raise HTTPException(404, "Not found")
    try:
        seen_emails = json.loads(n.seen_by or "[]")
    except:
        seen_emails = []
    # Get user details for each email
    users = []
    for email in seen_emails:
        u = db.query(models.User).filter(models.User.email == email).first()
        users.append({"email": email, "name": u.name if u else email})
    return {"notification_id": nid, "title": n.title, "seen_by": users, "total": len(users)}

@app.delete("/notifications/{nid}")
def delete_notification(nid: int, db: Session = Depends(get_db), user=Depends(require_permission("send_notifications"))):
    n = db.query(models.Notification).filter(models.Notification.id == nid).first()
    if not n: raise HTTPException(404, "Not found")
    db.delete(n); db.commit(); return {"msg": "Deleted"}

# ════════════════════════════════════════════════
# CHAT
# ════════════════════════════════════════════════
@app.post("/send", response_model=schemas.MessageOut)
async def send_message(data: schemas.MessageCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if data.receiver_id != 0 and not db.query(models.User).filter(models.User.id == data.receiver_id).first():
        raise HTTPException(404, "Receiver not found")
    msg = models.ChatMessage(sender_id=user.id, receiver_id=data.receiver_id, message=data.message)
    db.add(msg); db.commit(); db.refresh(msg)
    out = schemas.MessageOut.from_orm(msg).dict()
    if data.receiver_id == 0:
        await manager.broadcast(out)
    else:
        await manager.send_to(data.receiver_id, out)
        receiver = db.query(models.User).filter(models.User.id == data.receiver_id).first()
        if receiver:
            preview = data.message[:80] + "..." if len(data.message) > 80 else data.message
            db.add(models.Notification(
                title=f"💬 {user.name}",
                body=preview,
                icon="💬",
                target_email=receiver.email
            ))
            db.commit()
    return msg

@app.get("/messages/{other_id}", response_model=List[schemas.MessageOut])
def get_messages(other_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(models.ChatMessage).filter(
        ((models.ChatMessage.sender_id == user.id) & (models.ChatMessage.receiver_id == other_id)) |
        ((models.ChatMessage.sender_id == other_id) & (models.ChatMessage.receiver_id == user.id))
    ).order_by(models.ChatMessage.id.asc()).all()

# ════════════════════════════════════════════════
@app.delete("/messages/{msg_id}")
def delete_message(msg_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    msg = db.query(models.ChatMessage).filter(models.ChatMessage.id == msg_id).first()
    if not msg: raise HTTPException(404, "Message not found")
    if msg.sender_id != user.id and user.role != "admin":
        raise HTTPException(403, "You can only delete your own messages")
    db.delete(msg); db.commit()
    return {"msg": "Deleted"}

# WEBSOCKET
# ════════════════════════════════════════════════
@app.websocket("/ws/{user_id}")
async def ws_endpoint(ws: WebSocket, user_id: int, token: str, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if int(payload.get("sub", -1)) != user_id: await ws.close(1008); return
    except JWTError: await ws.close(1008); return
    await manager.connect(user_id, ws)
    try:
        while True:
            data = json.loads(await ws.receive_text())
            rid  = data.get("receiver_id")
            txt  = data.get("message", "").strip()
            if not txt or rid is None: continue
            msg  = models.ChatMessage(sender_id=user_id, receiver_id=rid, message=txt)
            db.add(msg); db.commit(); db.refresh(msg)
            out  = schemas.MessageOut.from_orm(msg).dict()
            await manager.send_to(rid, out)
            await manager.send_to(user_id, out)
    except WebSocketDisconnect: manager.disconnect(user_id)

# ════════════════════════════════════════════════
@app.patch("/users/me/password")
def change_password(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    current  = data.get("current_password","")
    new_pass = data.get("new_password","")
    if not current or not new_pass:
        raise HTTPException(400, "Both current and new password required")
    if user.password != current:
        raise HTTPException(400, "Current password is incorrect")
    if len(new_pass) < 4:
        raise HTTPException(400, "New password must be at least 4 characters")
    user.password = new_pass
    db.commit()
    return {"msg": "Password changed successfully"}

# PRODUCTIVITY
# ════════════════════════════════════════════════
@app.get("/productivity")
def get_productivity(db: Session = Depends(get_db), user=Depends(require_permission("view_productivity"))):
    users   = db.query(models.User).filter(models.User.role.in_(["intern","super_admin"])).all()
    tasks   = db.query(models.Task).all()
    att     = db.query(models.Attendance).all()
    reports = db.query(models.Report).all()
    result  = []
    for u in users:
        mt   = [t for t in tasks if t.assigned_to == u.email]
        done = len([t for t in mt if t.status == "Completed"])
        ts   = round((done / len(mt)) * 100) if mt else 0
        ma   = [a for a in att if a.email == u.email]
        pres = len([a for a in ma if a.status == "Present"])
        as_  = round((pres / len(ma)) * 100) if ma else 0
        mr   = [r for r in reports if r.submitted_by == u.email]
        result.append({
            "id": u.id, "name": u.name, "email": u.email, "role": u.role,
            "tasks_total":       len(mt),
            "tasks_done":        done,
            "tasks_in_progress": len([t for t in mt if t.status == "In Progress"]),
            "tasks_pending":     len([t for t in mt if t.status == "Pending"]),
            "task_score":        ts,
            "present":           pres,
            "absent":            len([a for a in ma if a.status == "Absent"]),
            "leave":             len([a for a in ma if a.status == "Leave"]),
            "att_score":         as_,
            "reports_submitted": len(mr),
            "reports_reviewed":  len([r for r in mr if r.reviewed]),
            "overall_score":     round(ts * 0.6 + as_ * 0.4),
        })
    return sorted(result, key=lambda x: x["overall_score"], reverse=True)

# ════════════════════════════════════════════════
# STATS
# ════════════════════════════════════════════════
@app.get("/stats")
def get_stats(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from datetime import date
    today = date.today().isoformat()
    return {
        "total_interns":     db.query(models.User).filter(models.User.role == "intern").count(),
        "total_superadmins": db.query(models.User).filter(models.User.role == "super_admin").count(),
        "tasks_completed":   db.query(models.Task).filter(models.Task.status == "Completed").count(),
        "tasks_pending":     db.query(models.Task).filter(models.Task.status == "Pending").count(),
        "tasks_in_progress": db.query(models.Task).filter(models.Task.status == "In Progress").count(),
        "total_projects":    db.query(models.Project).count(),
        "total_candidates":  db.query(models.Candidate).count(),
        "present_today":     db.query(models.Attendance).filter(
            models.Attendance.status == "Present",
            models.Attendance.date   == today
        ).count(),
    }