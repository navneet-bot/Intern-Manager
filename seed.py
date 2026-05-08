"""seed.py — run once: python seed.py"""
from database import SessionLocal, engine
import models, datetime

models.Base.metadata.create_all(bind=engine)
db = SessionLocal()

users = [
    models.User(name="Admin Boss",    email="admin@jobjockey.in",      password="123", role="admin",       permissions="all"),
    models.User(name="Navneet Kumar", email="navneet@jobjockey.in",    password="123", role="super_admin", permissions="create_task,delete_task,manage_attendance,view_reports,manage_groups,manage_meetings"),
    models.User(name="Rahul Sharma",  email="rahul@jobjockey.in",      password="123", role="intern",      permissions=""),
    models.User(name="Priya Nair",    email="priya@jobjockey.in",      password="123", role="intern",      permissions=""),
    models.User(name="Arjun Das",     email="arjun@jobjockey.in",      password="123", role="intern",      permissions=""),
    models.User(name="Sneha Patel",   email="sneha@jobjockey.in",      password="123", role="intern",      permissions=""),
    models.User(name="Rohan Gupta",   email="rohan@jobjockey.in",      password="123", role="intern",      permissions=""),
    models.User(name="Anjali Singh",  email="anjali@jobjockey.in",     password="123", role="intern",      permissions=""),
]
for u in users:
    if not db.query(models.User).filter(models.User.email == u.email).first():
        db.add(u)
db.commit()

tasks = [
    models.Task(title="Design Homepage",       description="Redesign landing page",          assigned_to="rahul@jobjockey.in",  status="In Progress", priority="High",   deadline="2026-06-15", project="Website Revamp",    created_by="admin@jobjockey.in"),
    models.Task(title="API Integration",       description="Connect mobile app to backend",  assigned_to="arjun@jobjockey.in",  status="Pending",     priority="High",   deadline="2026-06-20", project="Mobile App v2",     created_by="navneet@jobjockey.in"),
    models.Task(title="Write Blog Posts",      description="3 posts for Q2 campaign",        assigned_to="priya@jobjockey.in",  status="Completed",   priority="Medium", deadline="2026-05-30", project="Marketing Campaign", created_by="admin@jobjockey.in"),
    models.Task(title="ETL Pipeline",          description="Build data extraction pipeline", assigned_to="arjun@jobjockey.in",  status="Pending",     priority="Medium", deadline="2026-07-01", project="Data Pipeline",     created_by="navneet@jobjockey.in"),
    models.Task(title="UI Component Library",  description="Build reusable React components",assigned_to="sneha@jobjockey.in",  status="In Progress", priority="Low",    deadline="2026-06-25", project="Website Revamp",    created_by="admin@jobjockey.in"),
    models.Task(title="Write Unit Tests",      description="Test coverage for API gateway",  assigned_to="rohan@jobjockey.in",  status="Pending",     priority="Low",    deadline="2026-06-30", project="API Gateway",       created_by="navneet@jobjockey.in"),
]
for t in tasks:
    db.add(t)
db.commit()

projects = [
    models.Project(name="Website Revamp",     description="Redesign company website",       status="In Progress", progress=72,  color="#3b82f6", members='["rahul@jobjockey.in","sneha@jobjockey.in"]',  created_by="admin@jobjockey.in"),
    models.Project(name="Mobile App v2",      description="React Native intern app",        status="In Progress", progress=45,  color="#f59e0b", members='["arjun@jobjockey.in","rohan@jobjockey.in"]',  created_by="admin@jobjockey.in"),
    models.Project(name="Marketing Campaign", description="Q2 social media and content",    status="In Progress", progress=90,  color="#10b981", members='["priya@jobjockey.in","anjali@jobjockey.in"]', created_by="admin@jobjockey.in"),
    models.Project(name="Data Pipeline",      description="ETL pipeline for analytics",     status="Pending",     progress=30,  color="#8b5cf6", members='["arjun@jobjockey.in"]',                       created_by="navneet@jobjockey.in"),
    models.Project(name="HR Automation",      description="AI candidate screening",         status="Completed",   progress=100, color="#06b6d4", members='["priya@jobjockey.in"]',                       created_by="admin@jobjockey.in"),
    models.Project(name="API Gateway",        description="Centralised FastAPI gateway",    status="In Progress", progress=60,  color="#ef4444", members='["arjun@jobjockey.in","rohan@jobjockey.in"]',  created_by="navneet@jobjockey.in"),
]
for p in projects:
    db.add(p)
db.commit()

candidates = [
    models.Candidate(name="Vikram Mehta", email="vikram@gmail.com", phone="9876543210", skill="Python, FastAPI",   status="Pending"),
    models.Candidate(name="Nisha Kapoor", email="nisha@gmail.com",  phone="9012345678", skill="React, TypeScript", status="Approved"),
    models.Candidate(name="Karan Oberoi", email="karan@gmail.com",  phone="8123456789", skill="Data Science, ML",  status="Pending"),
    models.Candidate(name="Pooja Reddy",  email="pooja@gmail.com",  phone="7890123456", skill="UI/UX Design",      status="Rejected"),
    models.Candidate(name="Dev Malhotra", email="dev@gmail.com",    phone="6789012345", skill="DevOps, Docker",    status="Pending"),
]
for c in candidates:
    db.add(c)
db.commit()

today = datetime.date.today().isoformat()
for email, status in [("rahul@jobjockey.in","Present"),("priya@jobjockey.in","Present"),("arjun@jobjockey.in","Absent"),("sneha@jobjockey.in","Present"),("rohan@jobjockey.in","Leave"),("anjali@jobjockey.in","Present"),("navneet@jobjockey.in","Present")]:
    if not db.query(models.Attendance).filter(models.Attendance.email==email, models.Attendance.date==today).first():
        db.add(models.Attendance(email=email, date=today, status=status))
db.commit()

meetings = [
    models.Meeting(title="Sprint Planning",    description="Q2 sprint kick-off",     date="2026-06-10", time="10:00", meet_link="https://meet.google.com/abc-defg-hij", created_by="admin@jobjockey.in"),
    models.Meeting(title="Design Review",      description="Review homepage designs", date="2026-06-12", time="14:00", meet_link="https://meet.google.com/xyz-pqrs-tuv", created_by="navneet@jobjockey.in"),
    models.Meeting(title="Intern Orientation", description="Welcome new interns",     date="2026-06-15", time="11:00", meet_link="https://meet.google.com/lmn-opqr-stu", created_by="admin@jobjockey.in"),
]
for m in meetings:
    db.add(m)
db.commit()

notifications = [
    models.Notification(title="Welcome to Job Jockey!",   body="Platform is live.",                      icon="🎉", target_email="ALL"),
    models.Notification(title="New task assigned",         body="Design Homepage assigned to you.",       icon="📋", target_email="rahul@jobjockey.in"),
    models.Notification(title="Sprint meeting scheduled",  body="Sprint Planning on June 10 at 10 AM.",  icon="📅", target_email="ALL"),
    models.Notification(title="Submit weekly report",      body="Deadline is this Friday.",               icon="⚠️",  target_email="ALL"),
]
for n in notifications:
    db.add(n)
db.commit()

groups = [
    models.Group(name="Frontend Team",  description="React and UI developers",  icon="💻", members='["rahul@jobjockey.in","sneha@jobjockey.in"]',  created_by="admin@jobjockey.in"),
    models.Group(name="Backend Team",   description="FastAPI and DB engineers",  icon="⚙️",  members='["arjun@jobjockey.in","rohan@jobjockey.in"]',  created_by="navneet@jobjockey.in"),
    models.Group(name="Marketing Team", description="Content and social media",  icon="📣", members='["priya@jobjockey.in","anjali@jobjockey.in"]', created_by="admin@jobjockey.in"),
]
for g in groups:
    db.add(g)
db.commit()

print("✅ Database seeded! Accounts:")
print("  Admin (Boss): admin@jobjockey.in / 123")
print("  Super Admin:  navneet@jobjockey.in / 123")
print("  Interns:      rahul/priya/arjun/sneha/rohan/anjali @jobjockey.in / 123")
db.close()