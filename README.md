# Job Jockey — Intern Management Platform

Job Jockey is a web-based platform to manage interns in a company. Admin can add candidates, approve them, assign tasks, track attendance, schedule meetings, send notifications and monitor performance — all from one place.

---

## What is this project

This is a full stack web application. The backend is built with FastAPI (Python) and the frontend is a single HTML file. The database is SQLite. There is no need to install anything extra except Python packages.

When a candidate applies and gets approved, they automatically get a login account with a jobjockey email like `rahul.sharma@jobjockey.in` and a welcome email is sent to them. They can then login and see their tasks, submit reports, chat with the team and more.

---

## Tech used

- **Backend** — FastAPI, SQLAlchemy, SQLite, python-jose (JWT)
- **Frontend** — HTML, CSS, Vanilla JavaScript (single file)
- **Charts** — Chart.js
- **Email** — EmailJS (free, no server needed)
- **Real-time chat** — WebSocket with HTTP polling fallback

---

## Files in this project

```
jobjockey/
├── main.py                  → All API routes
├── models.py                → Database tables
├── schemas.py               → Request and response formats
├── database.py              → Database connection
├── seed.py                  → Creates demo data
├── migrate.py               → Adds new columns to existing database
├── requirements.txt         → Python packages needed
└── job_jockey_final.html    → Complete frontend (one file)
```

---

## How to run this project

**Step 1 — Clone the repo**
```
git clone https://github.com/YOUR_USERNAME/jobjockey.git
cd jobjockey
```

**Step 2 — Create virtual environment**
```
python -m venv venv
venv\Scripts\activate        (Windows)
source venv/bin/activate     (Mac or Linux)
```

**Step 3 — Install packages**
```
pip install -r requirements.txt
```

**Step 4 — Create database with demo data**
```
python seed.py
```

**Step 5 — Start the backend server**
```
uvicorn main:app --reload
```

**Step 6 — Open the frontend**

Just open `job_jockey_final.html` in your browser. That's it.

---

## Login credentials for testing

| Role | Email | Password |
|------|-------|----------|
| Admin (Boss) | admin@jobjockey.in | 123 |
| Super Admin | navneet@jobjockey.in | 123 |
| Intern | rahul@jobjockey.in | 123 |
| Intern | priya@jobjockey.in | 123 |
| Intern | arjun@jobjockey.in | 123 |

Approved candidates get email like `firstname.lastname@jobjockey.in` with password `123`

---

## Roles and what they can do

**Admin (Boss)**
- Has full access to everything
- Can promote any intern to Super Admin
- Can give or remove specific permissions to Super Admin using checkboxes
- Can approve or reject candidates
- When a candidate is approved, a login account is created automatically
- Can assign tasks to anyone
- Can view productivity scores and grades of all interns

**Super Admin**
- Gets permissions from Admin (Admin can select what they can access)
- Can assign tasks to interns only
- Can manage attendance, groups, meetings
- Can view candidates who are approved
- Cannot manage other admins

**Intern**
- Can see only their own tasks in a kanban board
- Can mark their own attendance
- Can submit daily reports with file attachments
- Can chat with team members
- Can view groups and meetings they are part of

---

## Main features

**Candidates**
- Upload CSV file or sync from Google Form
- Each candidate has fields — Name, Email, Phone, Skills, State, College, Domain, Duration, Resume
- Admin can approve or reject
- Bulk approve or delete multiple candidates at once
- When approved — jobjockey login is created and welcome email is sent

**Tasks**
- Create tasks with title, description, priority, deadline, project
- Assign to any intern or super admin
- Intern gets a notification when task is assigned
- Intern can update task status from Pending to In Progress to Completed
- Admin and Super Admin see all tasks, Intern sees only their own

**Productivity**
- Shows score for each intern based on tasks completed (60%) and attendance (40%)
- Grades from A+ to F
- Bar charts and performance table
- Export to CSV

**Attendance**
- Admin and Super Admin can mark Present, Absent or Leave for each member
- Intern can mark their own attendance
- Export attendance as CSV

**Reports**
- Intern submits report with title, description and any file (PDF, image, Word, etc.)
- File is saved in database as base64
- Admin can download the file and mark report as reviewed

**Groups**
- Create groups with name, description and icon
- Search members by typing first letters
- Selected members shown as colored tags
- Manage members from group card

**Meetings**
- Schedule meetings with title, date, time and Google Meet link
- Select which members to invite
- Invited members automatically get a notification

**Notifications**
- Admin can send notification to everyone or a specific person
- Admin and Super Admin can see who has read each notification (shown as green name tags)

**Chat**
- Real-time chat between any two users
- Messages saved in database
- Hover over message to delete it

**Calendar**
- Shows meetings and task deadlines as colored dots on calendar
- Click any date to see all events for that day
- Upcoming events shown in sidebar

**Email**
- Uses EmailJS (free service, no server needed)
- Configure once in Email Settings page with Service ID, Template ID and Public Key
- Welcome email sent automatically when candidate is approved
- Admin can send custom emails from Email Settings page with templates

---

## Setting up email (optional)

1. Go to emailjs.com and sign up free
2. Add Gmail as email service and note the Service ID
3. Create a template with Subject as `{{subject}}` and Content as `{{message}}` and note the Template ID
4. Go to Account and copy the Public Key
5. In Job Jockey go to Email Settings in the sidebar and enter all three values

---

## If you already have a database and added new columns

Run this to update your existing database without losing data

```
python migrate.py
```

---

## API runs on

```
http://127.0.0.1:8000
```

Swagger docs available at

```
http://127.0.0.1:8000/docs
```

---

## Known limitations

- Passwords are stored as plain text (use bcrypt for production)
- CORS is open to all origins (restrict in production)
- SQLite is used (switch to PostgreSQL for production)
- JWT tokens do not expire (add expiry for production)

---

## Made with

FastAPI, SQLAlchemy, Chart.js, EmailJS, WebSocket, HTML CSS JavaScript
