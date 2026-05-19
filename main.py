"""
Job Jockey — FastAPI Backend (Final Version 3.2)
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
import csv, json, re, os, smtplib, ssl, urllib.parse, urllib.request
import bcrypt as _bcrypt
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi.staticfiles import StaticFiles
from database import SessionLocal, engine
import models, schemas
from permissions import has_permission

models.Base.metadata.create_all(bind=engine)

# Auto-migrate: add new columns if they don't exist yet
def _run_migrations():
    import sqlite3
    db_path = "jobjockey.db"
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    existing = [r[1] for r in c.execute("PRAGMA table_info(candidates)").fetchall()]
    for col in ["state", "college", "edu_domain", "duration", "resume_link", "extra_data"]:
        if col not in existing:
            c.execute(f"ALTER TABLE candidates ADD COLUMN {col} TEXT DEFAULT ''")
            conn.commit()
    conn.close()

_run_migrations()

# ── Password helpers (bcrypt direct — avoids passlib/bcrypt 4.x compat issues) ─
def hash_password(plain: str) -> str:
    pw = (plain or "").encode("utf-8")[:72]   # bcrypt hard limit is 72 bytes
    return _bcrypt.hashpw(pw, _bcrypt.gensalt()).decode("utf-8")

def check_password(plain: str, stored: str) -> bool:
    if (stored or "").startswith("$2b$") or (stored or "").startswith("$2a$"):
        try:
            pw = (plain or "").encode("utf-8")[:72]
            return _bcrypt.checkpw(pw, stored.encode("utf-8"))
        except Exception:
            return False
    return plain == stored  # legacy plain-text accounts

# Ensure admin always exists with correct email; password stays as-is if already set
def seed_admin():
    db = SessionLocal()
    try:
        admin = db.query(models.User).filter(models.User.role == "admin").first()
        if admin:
            # Always keep the canonical email and name; never touch the password
            admin.email = "navneet@jobjockey.in"
            admin.name  = "Navneet"
        else:
            db.add(models.User(name="Navneet", email="navneet@jobjockey.in", password=hash_password("123"), role="admin", permissions="all"))
        db.commit()
    finally:
        db.close()

seed_admin()

app = FastAPI(title="Job Jockey API", version="3.1.0")
_cors_env = os.getenv("ALLOWED_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="."), name="static")

SECRET_KEY    = os.getenv("JWT_SECRET_KEY", "JOBJOCKEY_SECRET_2025")
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
def send_welcome_email(to_email: str, name: str, jj_email: str, password: str, db=None) -> tuple:
    """Returns (success: bool, error_msg: str)."""
    if db:
        def _val(k):
            r = db.query(models.Config).filter(models.Config.key == k).first()
            return r.value if r and r.value else ""
        SENDER_EMAIL    = _val("smtp_email") or os.getenv("JJ_EMAIL", _DEFAULT_SMTP_EMAIL)
        SENDER_PASSWORD = _val("smtp_pass")  or os.getenv("JJ_EMAIL_PASS", _DEFAULT_SMTP_PASS)
    else:
        SENDER_EMAIL    = os.getenv("JJ_EMAIL", _DEFAULT_SMTP_EMAIL)
        SENDER_PASSWORD = os.getenv("JJ_EMAIL_PASS", _DEFAULT_SMTP_PASS)
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        return False, "SMTP not configured"
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
    resend_key = os.getenv("RESEND_API_KEY", "")
    if db:
        def _rval(k):
            r = db.query(models.Config).filter(models.Config.key == k).first()
            return r.value if r and r.value else ""
        resend_key = _rval("resend_key") or resend_key
    try:
        _dispatch_email(resend_key, SENDER_EMAIL, SENDER_PASSWORD, to_email,
                        "🎉 Welcome to Job Jockey — Your Login Credentials", html)
        print(f"✅ Welcome email sent to {to_email}")
        return True, ""
    except Exception as e:
        err = str(e)
        print(f"❌ Email failed: {err}")
        return False, err


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
    user = models.User(name=data.name or data.email.split("@")[0], email=data.email, password=hash_password(data.password), role="admin", permissions="all")
    db.add(user); db.commit(); db.refresh(user)
    return {"msg": "Admin created", "id": user.id}

@app.post("/register-intern")
def register_intern(data: schemas.RegisterUser, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == data.email).first(): raise HTTPException(400, "Email already registered")
    user = models.User(name=data.name or data.email.split("@")[0], email=data.email, password=hash_password(data.password), role="intern", permissions="")
    db.add(user); db.commit(); db.refresh(user)
    from datetime import date as _date
    send_to_sheet({"type":"new_user","date":str(_date.today()),"name":user.name,"email":user.email,"role":user.role})
    return {"msg": "Intern created", "id": user.id}

@app.post("/login", response_model=schemas.LoginOut)
def login(data: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == data.email).first()
    if not user or not check_password(data.password, user.password): raise HTTPException(400, "Invalid email or password")
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
    extra_headers = field_map.pop("_extra_headers", [])
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
        extra = {h: row.get(h, "") for h in extra_headers if row.get(h, "").strip()}
        candidate = models.Candidate(
            name=name,
            email=email,
            phone=row.get(field_map.get("phone", "Phone"), "").strip(),
            skill=row.get(field_map.get("skill", "Skill"), "").strip(),
            state=row.get(field_map.get("state", "State"), "").strip(),
            college=row.get(field_map.get("college", "College"), "").strip(),
            edu_domain=row.get(field_map.get("edu_domain", "Education Domain"), "").strip(),
            duration=row.get(field_map.get("duration", "Duration"), "").strip(),
            resume_link=row.get(field_map.get("resume_link", "Resume Link"), "").strip(),
            extra_data=json.dumps(extra) if extra else "",
            status=data.status or "Pending"
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        created.append({"id": candidate.id, "name": candidate.name, "email": candidate.email})

    return {"created": created, "skipped": skipped, "total_rows": len(rows)}

@app.get("/candidates/me")
def get_my_candidate(db: Session = Depends(get_db), user=Depends(get_current_user)):
    c = db.query(models.Candidate).filter(
        models.Candidate.resume.like(f"LOGIN:{user.email}|PASS:%")
    ).first()
    if not c: raise HTTPException(404, "No candidate record found")
    return {"phone": c.phone or "", "skill": c.skill or "", "state": c.state or "",
            "college": c.college or "", "edu_domain": c.edu_domain or "",
            "name": c.name, "email": c.email, "duration": c.duration or "", "resume_link": c.resume_link or ""}

@app.patch("/candidates/me")
def update_my_candidate(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    c = db.query(models.Candidate).filter(
        models.Candidate.resume.like(f"LOGIN:{user.email}|PASS:%")
    ).first()
    if not c: raise HTTPException(404, "No candidate record found")
    for k in ("phone", "skill", "state", "college", "edu_domain", "resume_link"):
        if k in data and data[k] is not None:
            setattr(c, k, data[k])
    db.commit()
    return {"msg": "Info updated"}

@app.patch("/candidates/{cid}")
def update_candidate(cid: int, data: schemas.CandidateUpdate, db: Session = Depends(get_db), user=Depends(require_permission("manage_candidates"))):
    c = db.query(models.Candidate).filter(models.Candidate.id == cid).first()
    if not c: raise HTTPException(404, "Not found")
    for k, v in data.dict(exclude_none=True).items(): setattr(c, k, v)
    db.commit(); db.refresh(c)

    email_sent, email_error = None, ""

    # Only generate credentials on first approval — skip if already approved (resume has LOGIN:)
    if data.status == "Approved" and not (c.resume or "").startswith("LOGIN:"):
        try:
            clean = re.sub(r"[^a-zA-Z\s]", "", c.name or "").strip().lower()
            parts = clean.split()
            base_email = f"{parts[0]}.{parts[-1]}@jobjockey.in" if len(parts) >= 2 else f"{parts[0]}@jobjockey.in" if parts else f"intern@jobjockey.in"
            base = base_email.replace("@jobjockey.in", "")
            jj_email = base_email
            suffix = 1
            while db.query(models.User).filter(models.User.email == jj_email).first():
                jj_email = f"{base}{suffix}@jobjockey.in"
                suffix += 1

            password = "123"

            if not db.query(models.User).filter(models.User.email == jj_email).first():
                db.add(models.User(name=c.name or jj_email.split("@")[0], email=jj_email, password=hash_password(password), role="intern", permissions=""))
                db.commit()

            c.resume = f"LOGIN:{jj_email}|PASS:{password}"
            db.commit(); db.refresh(c)

            email_sent, email_error = send_welcome_email(
                to_email=c.email or "", name=c.name or "",
                jj_email=jj_email, password=password, db=db
            )

        except Exception as exc:
            import traceback
            print(f"❌ Approval error for candidate {cid}: {traceback.format_exc()}")
            db.rollback()
            raise HTTPException(500, f"Approval failed: {exc}")

    result = {k: getattr(c, k, None) for k in ("id","name","email","phone","skill","resume","resume_link","status","state","college","edu_domain","duration")}
    result["email_sent"] = email_sent
    result["email_error"] = email_error
    return result

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
# WORK LOG
# ════════════════════════════════════════════════
def _get_sheet(sheet_name: str):
    """Return a gspread worksheet, or None if not configured."""
    import json as _json
    import gspread
    from google.oauth2.service_account import Credentials
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    sheet_id = os.getenv("GSHEET_ID", "")
    if not sa_json or not sheet_id:
        return None
    creds = Credentials.from_service_account_info(
        _json.loads(sa_json),
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(sheet_id)
    try:
        return ss.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        return ss.add_worksheet(title=sheet_name, rows=1000, cols=20)

def send_to_sheet(payload: dict):
    try:
        if payload.get("type") == "worklog":
            ws = _get_sheet("WorkLogs")
            if ws is None: return
            if ws.row_count < 2 or ws.cell(1, 1).value != "Date":
                ws.insert_row(["Date","Name","Email","Login","Logout","Work Assigned",
                               "Work Did","Hours","Issues","Resolved","Started At","Completed At"], 1)
            ws.append_row([payload.get("date",""), payload.get("name",""), payload.get("email",""),
                           payload.get("login_time",""), payload.get("logout_time",""),
                           payload.get("work_assigned",""), payload.get("work_did",""),
                           payload.get("hours_worked",""), payload.get("issues",""),
                           payload.get("resolved",""), payload.get("started_at",""),
                           payload.get("completed_at","")])
        elif payload.get("type") == "new_user":
            ws = _get_sheet("Users")
            if ws is None: return
            if ws.row_count < 2 or ws.cell(1, 1).value != "Name":
                ws.insert_row(["Name","Email","Role","Registered At"], 1)
            ws.append_row([payload.get("name",""), payload.get("email",""),
                           payload.get("role",""), payload.get("registered_at","")])
    except Exception as e:
        print(f"Google Sheets write failed: {e}")

@app.post("/worklog")
def submit_worklog(data: schemas.WorkLogCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from datetime import date as _date
    log = models.WorkLog(
        email=user.email, name=user.name,
        login_time=data.login_time, logout_time=data.logout_time,
        work_assigned=data.work_assigned, work_did=data.work_did,
        hours_worked=data.hours_worked, issues=data.issues,
        resolved=data.resolved, started_at=data.started_at,
        completed_at=data.completed_at, date=str(_date.today())
    )
    db.add(log); db.commit()
    send_to_sheet({"type":"worklog","date":str(_date.today()),"name":user.name,"email":user.email,
        "work_assigned":data.work_assigned,"work_did":data.work_did,
        "hours_worked":data.hours_worked,"issues":data.issues,"resolved":data.resolved,
        "started_at":data.started_at,"completed_at":data.completed_at,
        "login_time":data.login_time,"logout_time":data.logout_time})
    return {"msg": "Work log saved"}

@app.get("/worklog")
def get_worklogs(db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(models.WorkLog)
    if user.role not in ("admin","super_admin"): q = q.filter(models.WorkLog.email == user.email)
    return q.order_by(models.WorkLog.created_at.desc()).all()

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

@app.get("/groups")
def get_groups(db: Session = Depends(get_db), user=Depends(get_current_user)):
    groups = db.query(models.Group).all()
    result = []
    for g in groups:
        d = schemas.GroupOut.from_orm(g).dict()
        d["message_count"] = db.query(models.GroupMessage).filter(models.GroupMessage.group_id == g.id).count()
        result.append(d)
    return result

@app.patch("/groups/{gid}/members")
def update_group_members(gid: int, data: dict, db: Session = Depends(get_db), user=Depends(require_permission("manage_groups"))):
    g = db.query(models.Group).filter(models.Group.id == gid).first()
    if not g: raise HTTPException(404, "Not found")
    try: old_members = json.loads(g.members or "[]")
    except: old_members = []
    new_members = data.get("members", [])
    g.members = json.dumps(new_members)
    db.commit(); db.refresh(g)
    # Notify members who were just added
    for email in new_members:
        if email not in old_members:
            db.add(models.Notification(
                title=f"👥 Added to {g.name}",
                body=f"You have been added to the group \"{g.name}\"",
                icon="👥", target_email=email
            ))
    db.commit()
    return {"msg": "Members updated", "members": new_members}

@app.delete("/groups/{gid}")
def delete_group(gid: int, db: Session = Depends(get_db), user=Depends(require_boss)):
    g = db.query(models.Group).filter(models.Group.id == gid).first()
    if not g: raise HTTPException(404, "Not found")
    db.delete(g); db.commit(); return {"msg": "Deleted"}

@app.get("/groups/{gid}/messages", response_model=List[schemas.GroupMessageOut])
def get_group_messages(gid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(models.GroupMessage).filter(models.GroupMessage.group_id == gid).order_by(models.GroupMessage.sent_at).all()

@app.post("/groups/{gid}/messages", response_model=schemas.GroupMessageOut)
def send_group_message(gid: int, data: schemas.GroupMessageCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    msg = models.GroupMessage(group_id=gid, sender=user.email, message=data.message)
    db.add(msg); db.commit(); db.refresh(msg)
    # Notify all group members except sender
    g = db.query(models.Group).filter(models.Group.id == gid).first()
    if g:
        try: members = json.loads(g.members or "[]")
        except: members = []
        if data.message.startswith("[img:"):
            fname = data.message[5:data.message.index("]")] if "]" in data.message else "image"
            preview = f"🖼️ Sent an image: {fname}"
        elif data.message.startswith("[file:"):
            fname = data.message[6:data.message.index("]")] if "]" in data.message else "file"
            preview = f"📎 Sent a file: {fname}"
        else:
            preview = data.message[:80] + "..." if len(data.message) > 80 else data.message
        for email in members:
            if email != user.email:
                db.add(models.Notification(
                    title=f"💬 {user.name} in {g.name}",
                    body=preview, icon="💬", target_email=email
                ))
        if members: db.commit()
    return msg

@app.delete("/groups/{gid}/messages/{mid}")
def delete_group_message(gid: int, mid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    msg = db.query(models.GroupMessage).filter(
        models.GroupMessage.id == mid,
        models.GroupMessage.group_id == gid
    ).first()
    if not msg: raise HTTPException(404, "Message not found")
    if msg.sender != user.email and user.role != "admin":
        raise HTTPException(403, "You can only delete your own messages")
    db.delete(msg); db.commit()
    return {"msg": "Deleted"}

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
            if data.message.startswith("[img:"):
                fname = data.message[5:data.message.index("]")] if "]" in data.message else "image"
                preview = f"🖼️ Sent an image: {fname}"
            elif data.message.startswith("[file:"):
                fname = data.message[6:data.message.index("]")] if "]" in data.message else "file"
                preview = f"📎 Sent a file: {fname}"
            else:
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
    if not check_password(current, user.password):
        raise HTTPException(400, "Current password is incorrect")
    if len(new_pass) < 4:
        raise HTTPException(400, "New password must be at least 4 characters")
    user.password = hash_password(new_pass)
    db.commit()
    return {"msg": "Password changed successfully"}

# EMAIL CONFIG & SEND
# ════════════════════════════════════════════════
_DEFAULT_SMTP_EMAIL = "Navneet066@jobjockey.in"
_DEFAULT_SMTP_PASS  = "lmykilowmhbydyfx"
_DEFAULT_FROM_EMAIL = "noreply@jobjockey.in"

def _get_email_config(db):
    """Return (resend_key, smtp_email, smtp_pass) — Resend preferred over SMTP."""
    def _val(key):
        row = db.query(models.Config).filter(models.Config.key == key).first()
        return row.value if row and row.value else ""
    resend_key = _val("resend_key") or os.getenv("RESEND_API_KEY", "")
    smtp_email = _val("smtp_email") or os.getenv("JJ_EMAIL", _DEFAULT_SMTP_EMAIL)
    smtp_pass  = _val("smtp_pass")  or os.getenv("JJ_EMAIL_PASS", _DEFAULT_SMTP_PASS)
    return resend_key, smtp_email, smtp_pass


def _send_smtp(smtp_email: str, smtp_pass: str, to_email: str, subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Job Jockey <{smtp_email}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(html_body, "html"))
    raw = msg.as_string()
    ctx = ssl.create_default_context()
    last_err = None
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=15) as s:
            s.login(smtp_email, smtp_pass)
            s.sendmail(smtp_email, to_email, raw)
        return
    except Exception as e:
        last_err = e
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as s:
            s.ehlo(); s.starttls(context=ctx); s.ehlo()
            s.login(smtp_email, smtp_pass)
            s.sendmail(smtp_email, to_email, raw)
        return
    except Exception as e:
        last_err = e
    raise last_err

def _send_resend(api_key: str, from_email: str, to_email: str, subject: str, html_body: str):
    """Send via Resend HTTP API — works on Railway and all cloud platforms."""
    import json as _json
    payload = _json.dumps({
        "from": f"Job Jockey <{from_email}>",
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return _json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise Exception(f"Resend error {e.code}: {e.read().decode()}")

def _send_sendgrid(api_key: str, from_email: str, to_email: str, subject: str, html_body: str):
    """Send via SendGrid HTTP API — works on Railway (port 443)."""
    payload = json.dumps({
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": "Job Jockey"},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_body}]
    }).encode()
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return {"status": r.status}
    except urllib.error.HTTPError as e:
        raise Exception(f"SendGrid error {e.code}: {e.read().decode()}")

def _send_gmail_api(to_email: str, subject: str, html_body: str):
    """Send via Gmail REST API over HTTPS — bypasses SMTP port blocks on Railway."""
    import base64 as _b64
    client_id     = os.getenv("GMAIL_CLIENT_ID", "")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET", "")
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN", "")
    from_email    = os.getenv("JJ_EMAIL", _DEFAULT_SMTP_EMAIL)
    if not all([client_id, client_secret, refresh_token]):
        raise Exception("Gmail API env vars not set (GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN)")
    # Exchange refresh_token → access_token
    token_data = urllib.parse.urlencode({
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token"
    }).encode()
    token_req = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST"
    )
    with urllib.request.urlopen(token_req, timeout=15) as r:
        access_token = json.loads(r.read())["access_token"]
    # Build RFC-2822 message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Job Jockey <{from_email}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(html_body, "html"))
    raw = _b64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")
    # POST to Gmail API
    payload = json.dumps({"raw": raw}).encode()
    send_req = urllib.request.Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        data=payload,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(send_req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise Exception(f"Gmail API {e.code}: {e.read().decode()}")

def _dispatch_email(resend_key: str, smtp_email: str, smtp_pass: str,
                    to_email: str, subject: str, html_body: str):
    """Priority: SendGrid → Gmail API → Resend → SMTP (local dev fallback)."""
    sg_key = os.getenv("SENDGRID_API_KEY", "")
    if sg_key:
        _send_sendgrid(sg_key, _DEFAULT_FROM_EMAIL, to_email, subject, html_body)
    elif os.getenv("GMAIL_REFRESH_TOKEN"):
        _send_gmail_api(to_email, subject, html_body)
    elif resend_key:
        _send_resend(resend_key, _DEFAULT_FROM_EMAIL, to_email, subject, html_body)
    else:
        _send_smtp(smtp_email, smtp_pass, to_email, subject, html_body)

@app.get("/config/email")
def get_email_config(db: Session = Depends(get_db), user=Depends(require_boss)):
    resend_key, smtp_email, smtp_pass = _get_email_config(db)
    return {
        "resend_key_set":  bool(resend_key),
        "smtp_email":      smtp_email,
        "smtp_configured": bool(smtp_email and smtp_pass),
        "smtp_pass_set":   bool(smtp_pass),
        "method":          "resend" if resend_key else "smtp",
    }

@app.post("/config/email")
def save_email_config(data: dict, db: Session = Depends(get_db), user=Depends(require_boss)):
    for key in ("smtp_email", "smtp_pass", "resend_key"):
        val = data.get(key, "")
        if not val:
            continue
        if key in ("smtp_pass", "resend_key") and val == "********":
            continue
        row = db.query(models.Config).filter(models.Config.key == key).first()
        if row:
            row.value = val
        else:
            db.add(models.Config(key=key, value=val))
    db.commit()
    return {"msg": "Email config saved"}

@app.post("/email/send")
def send_email_api(data: dict, db: Session = Depends(get_db), user=Depends(require_boss)):
    to_email = (data.get("to_email") or "").strip()
    subject  = (data.get("subject")  or "").strip()
    message  = (data.get("message")  or "").strip()
    to_name  = (data.get("to_name")  or to_email.split("@")[0]).strip()
    if not to_email or "@" not in to_email:
        raise HTTPException(400, "Invalid recipient email")
    if not subject:
        raise HTTPException(400, "Subject is required")
    resend_key, smtp_email, smtp_pass = _get_email_config(db)
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;background:#0f172a;color:#e2e8f0;border-radius:12px;overflow:hidden">
      <div style="background:#f59e0b;padding:20px 24px;text-align:center">
        <h1 style="margin:0;color:#000;font-size:22px">Job Jockey</h1>
        <p style="margin:4px 0 0;color:#1e293b;font-size:12px">Intern Management Platform</p>
      </div>
      <div style="padding:28px 32px">
        <p style="margin:0 0 8px;color:#94a3b8;font-size:13px">Hi <strong style="color:#f59e0b">{to_name}</strong>,</p>
        <div style="font-size:14px;line-height:1.7;white-space:pre-wrap;color:#e2e8f0">{message}</div>
        <p style="margin:24px 0 0;color:#64748b;font-size:12px">— Job Jockey Team</p>
      </div>
    </div>"""
    try:
        _dispatch_email(resend_key, smtp_email, smtp_pass, to_email, subject, html_body)
        return {"msg": f"Email sent to {to_email}"}
    except Exception as e:
        raise HTTPException(500, f"Failed to send email: {e}")

@app.post("/email/test")
def test_email(db: Session = Depends(get_db), user=Depends(require_boss)):
    resend_key, smtp_email, smtp_pass = _get_email_config(db)
    to_addr = smtp_email or _DEFAULT_SMTP_EMAIL
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;background:#0f172a;color:#e2e8f0;border-radius:12px;padding:28px">
      <h2 style="color:#f59e0b;margin-top:0">✅ Test Email Successful</h2>
      <p style="color:#94a3b8">Job Jockey email is working.<br>
      Method: <strong style="color:#f59e0b">{"Resend API" if resend_key else "SMTP"}</strong></p>
    </div>"""
    try:
        _dispatch_email(resend_key, smtp_email, smtp_pass, to_addr, "✅ Job Jockey — Email Test", html_body)
        return {"msg": f"Test email sent to {to_addr}"}
    except Exception as e:
        raise HTTPException(500, f"Test failed: {e}")

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