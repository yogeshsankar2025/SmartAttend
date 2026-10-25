
from flask import Flask, request, redirect, url_for, session, render_template_string
import sqlite3
import os
from functools import wraps
from datetime import date

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "smartattend-demo-change-this")

DB = os.environ.get("DATABASE_PATH", "attendance.db")

def connect_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                reg_no TEXT UNIQUE NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                status TEXT NOT NULL,
                UNIQUE(student_id, day)
            )
        """)

init_db()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

PAGE = """
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SmartAttend</title>
<style>
body{font-family:Arial;background:#f1f5f9;margin:0;color:#172554}
header{background:#123b70;color:white;padding:22px;text-align:center}
main{max-width:950px;margin:24px auto;padding:18px}
nav a{margin:6px;color:#075985;font-weight:bold}
.card{background:white;padding:20px;margin:14px 0;border-radius:12px}
input,select,button{padding:10px;margin:5px;border:1px solid #bbb;border-radius:5px}
button{background:#1769aa;color:white;cursor:pointer}
table{width:100%;border-collapse:collapse;background:white}
th,td{padding:10px;border-bottom:1px solid #ddd;text-align:left}
</style>
</head>
<body>
<header><h1>SmartAttend</h1>
<p>Automated Attendance Tracking and Detention Reporting System</p></header>
<main>
{% if session.get('logged_in') %}
<nav>
<a href="/">Dashboard</a>
<a href="/students">Students</a>
<a href="/attendance">Mark Attendance</a>
<a href="/reports">Reports</a>
<a href="/logout">Logout</a>
</nav>
{% endif %}
{% with messages = get_flashed_messages() %}
{% for message in messages %}<p>{{ message }}</p>{% endfor %}
{% endwith %}
{{ content|safe }}
</main>
</body></html>
"""

def page(content, **kwargs):
    return render_template_string(PAGE, content=render_template_string(
        content, **kwargs))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if (request.form.get("username") == "admin"
                and request.form.get("password") == "SmartAttend123!"):
            session["logged_in"] = True
            return redirect(url_for("home"))
        return page("""<div class="card"><h2>Login failed</h2>
        <a href="/login">Try again</a></div>""")
    return page("""
    <div class="card"><h2>Admin Login</h2>
    <p>Demo username: admin</p>
    <p>Demo password: SmartAttend123!</p>
    <form method="post">
    <input name="username" placeholder="Username" required>
    <input name="password" type="password" placeholder="Password" required>
    <button>Login</button></form></div>""")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def home():
    with connect_db() as conn:
        students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        today = conn.execute(
            "SELECT COUNT(*) FROM attendance WHERE day=? AND status='Present'",
            (date.today().isoformat(),)).fetchone()[0]
    return page("""
    <div class="card"><h2>Welcome to SmartAttend</h2>
    <p>Registered students: <b>{{ students }}</b></p>
    <p>Present today: <b>{{ today }}</b></p>
    <p>Use the navigation links to manage students and attendance.</p>
    <p><b>Note:</b> This demo uses manual attendance, not facial recognition.</p>
    </div>""", students=students, today=today)

@app.route("/students", methods=["GET", "POST"])
@login_required
def student_list():
    with connect_db() as conn:
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            reg = request.form.get("reg_no", "").strip()
            if name and reg:
                try:
                    conn.execute(
                        "INSERT INTO students(name, reg_no) VALUES (?,?)",
                        (name, reg))
                    conn.commit()
                except sqlite3.IntegrityError:
                    pass
            return redirect(url_for("student_list"))
        students = conn.execute("SELECT * FROM students ORDER BY name").fetchall()
    return page("""
    <div class="card"><h2>Register Student</h2>
    <form method="post">
    <input name="name" placeholder="Student name" required>
    <input name="reg_no" placeholder="Register number" required>
    <button>Add Student</button></form></div>
    <div class="card"><h2>Student List</h2>
    <table><tr><th>Name</th><th>Register No.</th></tr>
    {% for s in students %}<tr><td>{{ s.name }}</td>
    <td>{{ s.reg_no }}</td></tr>{% endfor %}</table></div>
    """, students=students)

@app.route("/attendance", methods=["GET", "POST"])
@login_required
def mark_attendance():
    today = date.today().isoformat()
    with connect_db() as conn:
        if request.method == "POST":
            for s in conn.execute("SELECT id FROM students").fetchall():
                status = request.form.get(str(s["id"]), "Absent")
                conn.execute("""
                    INSERT INTO attendance(student_id, day, status)
                    VALUES (?,?,?)
                    ON CONFLICT(student_id, day)
                    DO UPDATE SET status=excluded.status
                """, (s["id"], today, status))
            conn.commit()
            return redirect(url_for("reports"))
        students = conn.execute("SELECT * FROM students ORDER BY name").fetchall()
    return page("""
    <div class="card"><h2>Mark Attendance — {{ today }}</h2>
    {% if not students %}<p>Add students first.</p>{% endif %}
    <form method="post">
    {% for s in students %}
    <p>{{ s.name }} ({{ s.reg_no }})
    <select name="{{ s.id }}">
    <option value="Present">Present</option>
    <option value="Absent">Absent</option>
    </select></p>
    {% endfor %}
    {% if students %}<button>Save Attendance</button>{% endif %}
    </form></div>
    """, students=students, today=today)

@app.route("/reports")
@login_required
def reports():
    with connect_db() as conn:
        rows = conn.execute("""
            SELECT s.name, s.reg_no,
            COUNT(a.id) AS recorded,
            SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) AS present
            FROM students s LEFT JOIN attendance a ON s.id=a.student_id
            GROUP BY s.id ORDER BY s.name
        """).fetchall()
    return page("""
    <div class="card"><h2>Attendance Report</h2>
    <p>Detention flag: attendance below 75% of recorded sessions.</p>
    <table><tr><th>Name</th><th>Register No.</th>
    <th>Present</th><th>Recorded</th><th>Attendance</th><th>Status</th></tr>
    {% for s in rows %}
    {% set p = s.present or 0 %}
    {% set total = s.recorded or 0 %}
    {% set pct = (100*p/total) if total else 0 %}
    <tr><td>{{ s.name }}</td><td>{{ s.reg_no }}</td>
    <td>{{ p }}</td><td>{{ total }}</td><td>{{ "%.1f"|format(pct) }}%</td>
    <td>{% if total and pct < 75 %}Below 75%{% elif total %}OK{% else %}No records{% endif %}</td></tr>
    {% endfor %}</table></div>
    """, rows=rows)

@app.errorhandler(500)
def server_error(error):
    return "An internal error occurred. Check the deployment logs.", 500

if __name__ == "__main__":
    app.run(debug=False)
