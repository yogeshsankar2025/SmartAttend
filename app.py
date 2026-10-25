
import os
import sqlite3
import base64
from datetime import date, datetime
from functools import wraps

import cv2
import numpy as np
from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, flash, jsonify
)

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "attendance.db"))
FACE_DIR = os.environ.get("FACE_DATA_DIR", os.path.join(BASE_DIR, "face_data"))
MODEL_PATH = os.environ.get("FACE_MODEL_PATH", os.path.join(BASE_DIR, "face_model.yml"))

os.makedirs(FACE_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-demo-secret")

# Demo credentials. Set these environment variables on Render
# before sharing your website.
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "SmartAttend123!")


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

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

        # Add these columns when upgrading an older database.
        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(attendance)"
            ).fetchall()
        }

        if "method" not in columns:
            conn.execute("""
                ALTER TABLE attendance
                ADD COLUMN method TEXT NOT NULL DEFAULT 'manual'
            """)

        if "time" not in columns:
            conn.execute("""
                ALTER TABLE attendance
                ADD COLUMN time TEXT NOT NULL DEFAULT ''
            """)


init_db()


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return wrapper


# --------------------------------------------------
# COMMON PAGE DESIGN
# --------------------------------------------------

STYLE = """
<style>
* { box-sizing: border-box; }

body {
    font-family: Arial, sans-serif;
    background: #f1f5f9;
    margin: 0;
    color: #172554;
}

header {
    background: #163f70;
    color: white;
    padding: 22px;
    text-align: center;
}

main {
    max-width: 1050px;
    margin: 22px auto;
    padding: 16px;
}

nav {
    display: flex;
    flex-wrap: wrap;
    gap: 15px;
    padding: 14px;
    background: white;
    border-radius: 10px;
}

nav a {
    color: #075985;
    font-weight: bold;
}

.card {
    background: white;
    padding: 20px;
    margin: 14px 0;
    border-radius: 12px;
    box-shadow: 0 2px 8px #0001;
}

input, select, button {
    padding: 10px;
    margin: 5px;
    border: 1px solid #bbb;
    border-radius: 6px;
    font-size: 1rem;
}

button, .btn {
    background: #1769aa;
    color: white;
    border: 0;
    cursor: pointer;
    padding: 10px 14px;
    border-radius: 6px;
    text-decoration: none;
    display: inline-block;
}

.secondary {
    background: #475569;
}

table {
    width: 100%;
    border-collapse: collapse;
}

th, td {
    text-align: left;
    padding: 10px;
    border-bottom: 1px solid #ddd;
}

.tablewrap {
    overflow-x: auto;
}

.flash {
    background: #fff2c6;
    padding: 10px;
    margin: 8px 0;
    border-radius: 6px;
}

.warning {
    background: #fff2c6;
    padding: 12px;
    border-radius: 8px;
}

video {
    width: 100%;
    max-width: 640px;
    background: #111;
    border-radius: 8px;
}

.muted {
    color: #475569;
}
</style>
"""


def page(content, **context):
    rendered_content = render_template_string(content, **context)

    return render_template_string(
        """
        <!doctype html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <meta name="viewport"
                  content="width=device-width, initial-scale=1">
            <title>SmartAttend</title>
        """
        + STYLE +
        """
        </head>
        <body>
            <header>
                <h1>SmartAttend</h1>
                <p>Automated Attendance Tracking and Detention Reporting System</p>
            </header>

            <main>
                {% if session.get('logged_in') %}
                <nav>
                    <a href="{{ url_for('home') }}">Dashboard</a>
                    <a href="{{ url_for('students') }}">Students</a>
                    <a href="{{ url_for('manual_attendance') }}">Manual Attendance</a>
                    <a href="{{ url_for('face_attendance') }}">Face Attendance</a>
                    <a href="{{ url_for('reports') }}">Reports</a>
                    <a href="{{ url_for('logout') }}">Logout</a>
                </nav>
                {% endif %}

                {% with messages = get_flashed_messages() %}
                    {% for message in messages %}
                        <div class="flash">{{ message }}</div>
                    {% endfor %}
                {% endwith %}

                {{ content|safe }}
            </main>
        </body>
        </html>
        """,
        content=rendered_content
    )


# --------------------------------------------------
# OPENCV HELPERS
# --------------------------------------------------

def get_face_detector():
    cascade_path = os.path.join(
        cv2.data.haarcascades,
        "haarcascade_frontalface_default.xml"
    )
    return cv2.CascadeClassifier(cascade_path)


def decode_camera_image(data):
    if not data or "," not in data:
        return None

    try:
        encoded = data.split(",", 1)[1]
        raw = base64.b64decode(encoded)
        array = np.frombuffer(raw, dtype=np.uint8)
        return cv2.imdecode(array, cv2.IMREAD_COLOR)
    except Exception:
        return None


def face_model_ready():
    return (
        hasattr(cv2, "face")
        and os.path.isfile(MODEL_PATH)
    )


# --------------------------------------------------
# LOGIN ROUTES
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("home"))

        flash("Incorrect username or password.")

    return page("""
        <section class="card">
            <h2>Admin Login</h2>
            <form method="post">
                <input name="username"
                       placeholder="Username" required>
                <input name="password"
                       type="password"
                       placeholder="Password" required>
                <button type="submit">Login</button>
            </form>
        </section>
    """)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

@app.route("/")
@login_required
def home():
    with connect_db() as conn:
        total_students = conn.execute(
            "SELECT COUNT(*) FROM students"
        ).fetchone()[0]

        present_today = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE day = ? AND status = 'Present'
            """,
            (date.today().isoformat(),)
        ).fetchone()[0]

    return page("""
        <section class="card">
            <h2>Welcome to SmartAttend</h2>
            <p>Registered students: <b>{{ total_students }}</b></p>
            <p>Present today: <b>{{ present_today }}</b></p>
            <p>Use Face Attendance or Manual Attendance to record attendance.</p>
            <p class="warning">
                This is a prototype. Face recognition can be incorrect.
                Review records and keep manual correction available.
            </p>
        </section>
    """, total_students=total_students, present_today=present_today)


# --------------------------------------------------
# STUDENT MANAGEMENT
# --------------------------------------------------

@app.route("/students", methods=["GET", "POST"])
@login_required
def students():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        reg_no = request.form.get("reg_no", "").strip()

        if not name or not reg_no:
            flash("Enter both student name and register number.")
        else:
            try:
                with connect_db() as conn:
                    conn.execute(
                        """
                        INSERT INTO students(name, reg_no)
                        VALUES (?, ?)
                        """,
                        (name, reg_no)
                    )
                flash("Student added. Capture face samples next.")

            except sqlite3.IntegrityError:
                flash("That register number already exists.")

        return redirect(url_for("students"))

    with connect_db() as conn:
        rows = conn.execute(
            "SELECT * FROM students ORDER BY name"
        ).fetchall()

    counts = {}

    for student in rows:
        folder = os.path.join(FACE_DIR, str(student["id"]))

        if os.path.isdir(folder):
            counts[student["id"]] = sum(
                1 for filename in os.listdir(folder)
                if filename.lower().endswith(".jpg")
            )
        else:
            counts[student["id"]] = 0

    return page("""
        <section class="card">
            <h2>Register Student</h2>
            <form method="post">
                <input name="name"
                       placeholder="Student name" required>
                <input name="reg_no"
                       placeholder="Register number" required>
                <button type="submit">Add Student</button>
            </form>
        </section>

        <section class="card">
            <h2>Student List and Face Enrollment</h2>

            {% if rows %}
            <div class="tablewrap">
                <table>
                    <tr>
                        <th>Name</th>
                        <th>Register No.</th>
                        <th>Face Samples</th>
                        <th>Action</th>
                    </tr>

                    {% for s in rows %}
                    <tr>
                        <td>{{ s.name }}</td>
                        <td>{{ s.reg_no }}</td>
                        <td>{{ counts.get(s.id, 0) }}</td>
                        <td>
                            <a class="btn"
                               href="{{ url_for('enroll', student_id=s.id) }}">
                               Capture Face
                            </a>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
            {% else %}
                <p>No students registered yet.</p>
            {% endif %}

            <form method="post" action="{{ url_for('train') }}">
                <button class="secondary" type="submit">
                    Train / Retrain Face Model
                </button>
            </form>
        </section>
    """, rows=rows, counts=counts)


# --------------------------------------------------
# FACE ENROLLMENT PAGE
# --------------------------------------------------

@app.route("/enroll/<int:student_id>")
@login_required
def enroll(student_id):
    with connect_db() as conn:
        student = conn.execute(
            "SELECT * FROM students WHERE id = ?",
            (student_id,)
        ).fetchone()

    if not student:
        flash("Student not found.")
        return redirect(url_for("students"))

    return page("""
        <section class="card">
            <h2>Capture Face Samples</h2>
            <p>
                Student: <b>{{ student.name }}</b>
                — {{ student.reg_no }}
            </p>
            <p>
                Obtain consent before enrollment. Capture several samples
                in good lighting with one face visible.
            </p>

            <video id="video" autoplay playsinline></video>
            <canvas id="canvas" hidden></canvas>

            <p>
                <button id="capture">Save Face Sample</button>
                <button id="stop" class="secondary">Stop Camera</button>
            </p>
            <p id="message" aria-live="polite"></p>
        </section>

        <script>
        const video = document.getElementById("video");
        const canvas = document.getElementById("canvas");
        const message = document.getElementById("message");
        let stream = null;

        async function startCamera() {
            try {
                stream = await navigator.mediaDevices.getUserMedia({
                    video: true,
                    audio: false
                });
                video.srcObject = stream;
            } catch (error) {
                message.textContent =
                    "Camera unavailable. Allow camera access on this HTTPS site.";
            }
        }

        document.getElementById("capture").onclick = async () => {
            if (!video.videoWidth) {
                message.textContent = "Camera is not ready.";
                return;
            }

            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            canvas.getContext("2d").drawImage(video, 0, 0);

            const response = await fetch(
                "{{ url_for('save_sample', student_id=student.id) }}",
                {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        image: canvas.toDataURL("image/jpeg", 0.85)
                    })
                }
            );

            const result = await response.json();
            message.textContent = result.message;
        };

        document.getElementById("stop").onclick = () => {
            if (stream) stream.getTracks().forEach(track => track.stop());
            video.srcObject = null;
            message.textContent = "Camera stopped.";
        };

        startCamera();
        </script>
    """, student=student)


# --------------------------------------------------
# SAVE FACE SAMPLE
# --------------------------------------------------

@app.route("/api/sample/<int:student_id>", methods=["POST"])
@login_required
def save_sample(student_id):
    with connect_db() as conn:
        student = conn.execute(
            "SELECT id FROM students WHERE id = ?",
            (student_id,)
        ).fetchone()

    if not student:
        return jsonify(ok=False, message="Student not found."), 404

    data = request.get_json(silent=True) or {}
    frame = decode_camera_image(data.get("image"))

    if frame is None:
        return jsonify(ok=False, message="Could not read camera image."), 400

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = get_face_detector().detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
    )

    if len(faces) != 1:
        return jsonify(
            ok=False,
            message="Keep exactly one face clearly visible."
        ), 400

    x, y, w, h = faces[0]
    face = cv2.resize(gray[y:y+h, x:x+w], (200, 200))

    folder = os.path.join(FACE_DIR, str(student_id))
    os.makedirs(folder, exist_ok=True)

    existing = [
        f for f in os.listdir(folder)
        if f.lower().endswith(".jpg")
    ]
    filename = os.path.join(folder, f"sample_{len(existing)+1:03d}.jpg")

    if not cv2.imwrite(filename, face):
        return jsonify(ok=False, message="Could not save face sample."), 500

    return jsonify(
        ok=True,
        message=f"Saved sample {len(existing)+1}. Capture several samples."
    )


# --------------------------------------------------
# TRAIN FACE RECOGNITION MODEL
# --------------------------------------------------

@app.route("/train", methods=["POST"])
@login_required
def train():
    if not hasattr(cv2, "face"):
        flash("OpenCV face module is unavailable. Check requirements.txt.")
        return redirect(url_for("students"))

    images = []
    labels = []

    with connect_db() as conn:
        registered = conn.execute(
            "SELECT id FROM students"
        ).fetchall()

    for student in registered:
        folder = os.path.join(FACE_DIR, str(student["id"]))

        if not os.path.isdir(folder):
            continue

        for filename in os.listdir(folder):
            if not filename.lower().endswith(".jpg"):
                continue

            path = os.path.join(folder, filename)
            image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)

            if image is not None:
                images.append(cv2.resize(image, (200, 200)))
                labels.append(int(student["id"]))

    if not images:
        flash("No face samples found. Enroll students first.")
        return redirect(url_for("students"))

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(images, np.asarray(labels, dtype=np.int32))
    recognizer.write(MODEL_PATH)

    flash(f"Face model trained using {len(images)} samples.")
    return redirect(url_for("students"))


# --------------------------------------------------
# FACE ATTENDANCE PAGE
# --------------------------------------------------

@app.route("/face-attendance")
@login_required
def face_attendance():
    return page("""
        <section class="card">
            <h2>Face Recognition Attendance</h2>
            <p>
                Allow camera access and keep one enrolled face in view.
                Verify the result after recognition.
            </p>

            <video id="video" autoplay playsinline></video>
            <canvas id="canvas" hidden></canvas>

            <p>
                <button id="recognize">Recognize and Mark Present</button>
                <button id="stop" class="secondary">Stop Camera</button>
            </p>
            <p id="message" aria-live="polite"></p>
        </section>

        <script>
        const video = document.getElementById("video");
        const canvas = document.getElementById("canvas");
        const message = document.getElementById("message");
        let stream = null;

        async function startCamera() {
            try {
                stream = await navigator.mediaDevices.getUserMedia({
                    video: true,
                    audio: false
                });
                video.srcObject = stream;
            } catch (error) {
                message.textContent =
                    "Camera access failed. Allow camera access on this HTTPS site.";
            }
        }

        document.getElementById("recognize").onclick = async () => {
            if (!video.videoWidth) {
                message.textContent = "Camera is not ready.";
                return;
            }

            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            canvas.getContext("2d").drawImage(video, 0, 0);

            const response = await fetch("{{ url_for('recognize') }}", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    image: canvas.toDataURL("image/jpeg", 0.85)
                })
            });

            const result = await response.json();
            message.textContent = result.message +
                (result.score !== undefined
                    ? " (match score: " + result.score + ")"
                    : "");
        };

        document.getElementById("stop").onclick = () => {
            if (stream) stream.getTracks().forEach(track => track.stop());
            video.srcObject = null;
            message.textContent = "Camera stopped.";
        };

        startCamera();
        </script>
    """)


# --------------------------------------------------
# RECOGNIZE FACE AND MARK ATTENDANCE
# --------------------------------------------------

@app.route("/api/recognize", methods=["POST"])
@login_required
def recognize():
    if not face_model_ready():
        return jsonify(
            ok=False,
            message="Face model is not available. Enroll faces and train the model."
        ), 400

    data = request.get_json(silent=True) or {}
    frame = decode_camera_image(data.get("image"))

    if frame is None:
        return jsonify(ok=False, message="Could not read camera image."), 400

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = get_face_detector().detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
    )

    if len(faces) != 1:
        return jsonify(
            ok=False,
            message="Keep exactly one face clearly visible."
        ), 400

    x, y, w, h = faces[0]
    face = cv2.resize(gray[y:y+h, x:x+w], (200, 200))

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(MODEL_PATH)
    label, score = recognizer.predict(face)

    # Lower LBPH scores mean closer matches. This threshold needs testing.
    if score > 65:
        return jsonify(
            ok=False,
            message="No confident match. Try again or use manual attendance.",
            score=round(float(score), 1)
        )

    today = date.today().isoformat()
    now = datetime.now().strftime("%H:%M:%S")

    with connect_db() as conn:
        student = conn.execute(
            "SELECT * FROM students WHERE id = ?",
            (int(label),)
        ).fetchone()

        if not student:
            return jsonify(
                ok=False,
                message="Recognized ID is not in the student list."
            ), 400

        try:
            conn.execute(
                """
                INSERT INTO attendance
                    (student_id, day, status, method, time)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    student["id"], today, "Present",
                    "face recognition", now
                )
            )
            conn.commit()
            message = (
                f"Attendance marked for {student['name']} "
                f"({student['reg_no']}). Please verify the record."
            )

        except sqlite3.IntegrityError:
            message = (
                f"{student['name']} already has an attendance record today."
            )

    return jsonify(
        ok=True,
        message=message,
        score=round(float(score), 1)
    )


# --------------------------------------------------
# MANUAL ATTENDANCE
# --------------------------------------------------

@app.route("/attendance", methods=["GET", "POST"])
@login_required
def manual_attendance():
    today = date.today().isoformat()

    with connect_db() as conn:
        if request.method == "POST":
            student_id = request.form.get("student_id", type=int)
            status = request.form.get("status", "Present")

            if not student_id or status not in ("Present", "Absent"):
                flash("Select a student and a valid status.")
                return redirect(url_for("manual_attendance"))

            student = conn.execute(
                "SELECT id FROM students WHERE id = ?",
                (student_id,)
            ).fetchone()

            if not student:
                flash("Student not found.")
                return redirect(url_for("manual_attendance"))

            now = datetime.now().strftime("%H:%M:%S")

            conn.execute(
                """
                INSERT INTO attendance
                    (student_id, day, status, method, time)
                VALUES (?, ?, ?, 'manual', ?)
                ON CONFLICT(student_id, day)
                DO UPDATE SET
                    status = excluded.status,
                    method = 'manual',
                    time = excluded.time
                """,
                (student_id, today, status, now)
            )
            conn.commit()
            flash("Manual attendance saved.")
            return redirect(url_for("manual_attendance"))

        students = conn.execute(
            "SELECT * FROM students ORDER BY name"
        ).fetchall()

    return page("""
        <section class="card">
            <h2>Manual Attendance — {{ today }}</h2>

            {% if students %}
            <form method="post">
                <label>Student</label>
                <select name="student_id" required>
                    {% for s in students %}
                    <option value="{{ s.id }}">
                        {{ s.name }} — {{ s.reg_no }}
                    </option>
                    {% endfor %}
                </select>

                <label>Status</label>
                <select name="status">
                    <option value="Present">Present</option>
                    <option value="Absent">Absent</option>
                </select>

                <button type="submit">Save Attendance</button>
            </form>
            {% else %}
                <p>Add students first.</p>
            {% endif %}
        </section>
    """, students=students, today=today)


# --------------------------------------------------
# REPORTS
# --------------------------------------------------

@app.route("/reports")
@login_required
def reports():
    with connect_db() as conn:
        rows = conn.execute("""
            SELECT
                s.id,
                s.name,
                s.reg_no,
                COUNT(a.id) AS recorded,
                SUM(
                    CASE WHEN a.status = 'Present'
                    THEN 1 ELSE 0 END
                ) AS present
            FROM students s
            LEFT JOIN attendance a ON a.student_id = s.id
            GROUP BY s.id
            ORDER BY s.name
        """).fetchall()

        logs = conn.execute("""
            SELECT s.name, s.reg_no, a.day, a.time,
                   a.status, a.method
            FROM attendance a
            JOIN students s ON s.id = a.student_id
            ORDER BY a.day DESC, a.time DESC
            LIMIT 100
        """).fetchall()

    return page("""
        <section class="card">
            <h2>Attendance Report</h2>
            <p>
                Below 75% is a review flag, not an automatic disciplinary decision.
                This percentage uses recorded sessions only.
            </p>

            <div class="tablewrap">
                <table>
                    <tr>
                        <th>Name</th>
                        <th>Register No.</th>
                        <th>Present</th>
                        <th>Recorded</th>
                        <th>Attendance</th>
                        <th>Status</th>
                    </tr>

                    {% for s in rows %}
                    {% set p = s.present or 0 %}
                    {% set total = s.recorded or 0 %}
                    {% set pct = (100 * p / total) if total else 0 %}

                    <tr>
                        <td>{{ s.name }}</td>
                        <td>{{ s.reg_no }}</td>
                        <td>{{ p }}</td>
                        <td>{{ total }}</td>
                        <td>{{ "%.1f"|format(pct) }}%</td>
                        <td>
                            {% if total and pct < 75 %}
                                Below 75% — review
                            {% elif total %}
                                OK
                            {% else %}
                                No records
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </section>

        <section class="card">
            <h2>Recent Attendance Records</h2>
            <div class="tablewrap">
                <table>
                    <tr>
                        <th>Date</th>
                        <th>Time</th>
                        <th>Name</th>
                        <th>Status</th>
                        <th>Method</th>
                    </tr>

                    {% for record in logs %}
                    <tr>
                        <td>{{ record.day }}</td>
                        <td>{{ record.time }}</td>
                        <td>{{ record.name }}</td>
                        <td>{{ record.status }}</td>
                        <td>{{ record.method }}</td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="5">No attendance records yet.</td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </section>
    """, rows=rows, logs=logs)


# --------------------------------------------------
# ERROR HANDLER
# --------------------------------------------------

@app.errorhandler(500)
def server_error(error):
    return (
        "An internal error occurred. Check the Render deployment logs.",
        500
    )


# --------------------------------------------------
# LOCAL DEVELOPMENT
# --------------------------------------------------

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
