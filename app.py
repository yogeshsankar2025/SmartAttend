import os, sqlite3, base64
from datetime import date, datetime
from functools import wraps

import cv2
import numpy as np
from flask import Flask, request, redirect, url_for, session, render_template_string, flash, jsonify

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("DATABASE_PATH", os.path.join(BASE, "attendance.db"))
FACE_DIR = os.environ.get("FACE_DATA_DIR", os.path.join(BASE, "face_data"))
MODEL_PATH = os.environ.get("FACE_MODEL_PATH", os.path.join(BASE, "face_model.yml"))
os.makedirs(os.path.dirname(os.path.abspath(DB)), exist_ok=True)
os.makedirs(FACE_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-before-public-use")

def connect_db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with connect_db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS students(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, reg_no TEXT NOT NULL UNIQUE)""")
        c.execute("""CREATE TABLE IF NOT EXISTS attendance(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL, day TEXT NOT NULL, status TEXT NOT NULL,
            method TEXT NOT NULL DEFAULT 'manual', time TEXT NOT NULL DEFAULT '',
            UNIQUE(student_id, day))""")
        # Migrate an older database made by the original SmartAttend app.
        cols = {r["name"] for r in c.execute("PRAGMA table_info(attendance)").fetchall()}
        if "method" not in cols:
            c.execute("ALTER TABLE attendance ADD COLUMN method TEXT NOT NULL DEFAULT 'manual'")
        if "time" not in cols:
            c.execute("ALTER TABLE attendance ADD COLUMN time TEXT NOT NULL DEFAULT ''")

init_db()

def login_required(fn):
    @wraps(fn)
    def inner(*a, **kw):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return inner

STYLE = """
<style>
*{box-sizing:border-box}body{font-family:Arial,sans-serif;background:#f1f5f9;margin:0;color:#172554}
header{background:#163f70;color:white;padding:22px;text-align:center}main{max-width:1050px;margin:22px auto;padding:16px}
nav{display:flex;flex-wrap:wrap;gap:15px;padding:14px;background:#fff;border-radius:10px}nav a{color:#075985;font-weight:bold}
.card{background:#fff;padding:20px;margin:14px 0;border-radius:12px;box-shadow:0 2px 8px #0001}
input,select,button{padding:10px;margin:5px;border:1px solid #bbb;border-radius:6px;font-size:1rem}
button,.btn{background:#1769aa;color:#fff;border:0;cursor:pointer;padding:10px 14px;border-radius:6px;text-decoration:none;display:inline-block}
.secondary{background:#475569}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #ddd}
.tablewrap{overflow-x:auto}.flash{background:#fff2c6;padding:10px;margin:8px 0;border-radius:6px}
video{width:100%;max-width:640px;background:#111;border-radius:8px}.muted{color:#475569}.warning{background:#fff2c6;padding:12px;border-radius:8px}
</style>"""
def page(content, **ctx):
    inner = render_template_string(content, **ctx)
    return render_template_string("""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SmartAttend</title>""" + STYLE +
"""</head><body><header><h1>SmartAttend</h1><p>Automated Attendance Tracking and Detention Reporting System</p></header>
<main>{% if session.get('logged_in') %}<nav>
<a href="{{ url_for('home') }}">Dashboard</a><a href="{{ url_for('students') }}">Students</a>
<a href="{{ url_for('manual_attendance') }}">Manual Attendance</a><a href="{{ url_for('face_attendance') }}">Face Attendance</a>
<a href="{{ url_for('reports') }}">Reports</a><a href="{{ url_for('logout') }}">Logout</a></nav>{% endif %}
{% with msgs=get_flashed_messages() %}{% for m in msgs %}<div class="flash">{{m}}</div>{% endfor %}{% endwith %}
""" + inner + "</main></body></html>")

def face_detector():
    p = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
    return cv2.CascadeClassifier(p)

def read_image_data(data):
    if not data or "," not in data:
        return None
    try:
        raw = base64.b64decode(data.split(",", 1)[1])
        arr = np.frombuffer(raw, np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        return None

def model_available():
    return hasattr(cv2, "face") and os.path.isfile(MODEL_PATH)

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == os.environ.get("ADMIN_USERNAME","admin") and request.form.get("password") == os.environ.get("ADMIN_PASSWORD","SmartAttend123!"):
            session["logged_in"] = True
            return redirect(url_for("home"))
        flash("Login details are incorrect.")
    return page("""<section class="card"><h2>Admin Login</h2><p>Demo username: <b>admin</b></p>
<p>Demo password: <b>SmartAttend123!</b></p><p class="muted">Change these using ADMIN_USERNAME and ADMIN_PASSWORD environment variables before sharing.</p>
<form method="post"><input name="username" placeholder="Username" required><input name="password" type="password" placeholder="Password" required><button>Login</button></form></section>""")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def home():
    with connect_db() as c:
        total = c.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        today = c.execute("SELECT COUNT(*) FROM attendance WHERE day=? AND status='Present'",(date.today().isoformat(),)).fetchone()[0]
    return page("""<section class="card"><h2>Welcome to SmartAttend</h2>
<p>Registered students: <b>{{total}}</b></p><p>Present today: <b>{{today}}</b></p>
<p>Use Face Attendance to capture a camera image and match it against enrolled samples. Manual entry remains available.</p>
<p class="warning">Prototype only: recognition may be wrong. Review records and do not make disciplinary decisions based only on a match.</p></section>""",total=total,today=today)

@app.route("/students", methods=["GET","POST"])
@login_required
def students():
    if request.method == "POST":
        name=request.form.get("name","").strip()
        reg=request.form.get("reg_no","").strip()
        if not name or not reg:
            flash("Enter both name and register number.")
        else:
            try:
                with connect_db() as c: c.execute("INSERT INTO students(name,reg_no) VALUES(?,?)",(name,reg))
                flash("Student added. Capture several face samples next.")
            except sqlite3.IntegrityError: flash("Register number already exists.")
        return redirect(url_for("students"))
    with connect_db() as c: rows=c.execute("SELECT * FROM students ORDER BY name").fetchall()
    return page("""<section class="card"><h2>Add student</h2><form method="post">
<input name="name" placeholder="Student name" required><input name="reg_no" placeholder="Register number" required><button>Add student</button></form></section>
<section class="card"><h2>Students and face enrollment</h2>
{% if rows %}<div class="tablewrap"><table><tr><th>Name</th><th>Register No.</th><th>Face samples</th><th>Action</th></tr>
{% for s in rows %}<tr><td>{{s.name}}</td><td>{{s.reg_no}}</td><td>{{ counts.get(s.id,0) }}</td><td><a class="btn" href="{{url_for('enroll',student_id=s.id)}}">Capture face</a></td></tr>{% endfor %}</table></div>{% else %}<p>No students yet.</p>{% endif %}
<form method="post" action="{{url_for('train')}}"><button class="secondary">Train / retrain face model</button></form></section>""",
rows=rows,counts={int(s["id"]):len([x for x in os.listdir(os.path.join(FACE_DIR,str(s["id"]))) if x.endswith(".jpg"]) if os.path.isdir(os.path.join(FACE_DIR,str(s["id"]))) else 0 for s in rows})

@app.route("/enroll/<int:student_id>")
@login_required
def enroll(student_id):
    with connect_db() as c: s=c.execute("SELECT * FROM students WHERE id=?",(student_id,)).fetchone()
    if not s: flash("Student not found."); return redirect(url_for("students"))
    return page("""<section class="card"><h2>Face enrollment</h2><p>Student: <b>{{s.name}}</b> — {{s.reg_no}}</p>
<p>Get consent first. Capture 5–10 images in decent lighting, with one face visible.</p><video id="v" autoplay playsinline></video><canvas id="c" hidden></canvas><p><button id="snap">Save face sample</button> <button id="stop" class="secondary">Stop camera</button></p><p id="msg" aria-live="polite"></p></section>
<script>
let stream;const v=document.getElementById('v'),c=document.getElementById('c'),msg=document.getElementById('msg');
(async()=>{try{stream=await navigator.mediaDevices.getUserMedia({video:true,audio:false});v.srcObject=stream}catch(e){msg.textContent='Camera permission failed. Open this site over HTTPS and allow camera access.'}})();
document.getElementById('snap').onclick=async()=>{if(!v.videoWidth){msg.textContent='Camera not ready.';return}c.width=v.videoWidth;c.height=v.videoHeight;c.getContext('2d').drawImage(v,0,0);let r=await fetch('{{url_for("save_sample",student_id=s.id)}}',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:c.toDataURL('image/jpeg',.85)})});let d=await r.json();msg.textContent=d.message};
document.getElementById('stop').onclick=()=>{if(stream)stream.getTracks().forEach(t=>t.stop());v.srcObject=null;msg.textContent='Camera stopped.'};
</script><p><a href="{{url_for('students')}}">Back to students</a></p>""",s=s)

@app.route("/api/sample/<int:student_id>", methods=["POST"])
@login_required
def save_sample(student_id):
    with connect_db() as c: s=c.execute("SELECT id FROM students WHERE id=?",(student_id,)).fetchone()
    if not s: return jsonify(ok=False,message="Student not found."),404
    frame=read_image_data((request.get_json(silent=True) or {}).get("image"))
    if frame is None: return jsonify(ok=False,message="Image could not be read."),400
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    faces=face_detector().detectMultiScale(gray,1.1,5,minSize=(80,80))
    if len(faces)!=1: return jsonify(ok=False,message="Keep exactly one face visible in the camera."),400
    x,y,w,h=faces[0]; crop=cv2.resize(gray[y:y+h,x:x+w],(200,200))
    folder=os.path.join(FACE_DIR,str(student_id));os.makedirs(folder,exist_ok=True)
    idx=len([f for f in os.listdir(folder) if f.endswith(".jpg")])+1
    if not cv2.imwrite(os.path.join(folder,f"sample_{idx:03d}.jpg"),crop): return jsonify(ok=False,message="Could not save sample."),500
    return jsonify(ok=True,message=f"Saved face sample {idx}. Capture several samples, then train the model.")

@app.route("/train",methods=["POST"])
@login_required
def train():
    if not hasattr(cv2,"face"):
        flash("OpenCV face module is missing. requirements.txt must use opencv-contrib-python-headless.")
        return redirect(url_for("students"))
    images=[];labels=[]
    with connect_db() as c: students=c.execute("SELECT id FROM students").fetchall()
    for s in students:
        folder=os.path.join(FACE_DIR,str(s["id"]))
        if not os.path.isdir(folder): continue
        for f in os.listdir(folder):
            if f.endswith(".jpg"):
                im=cv2.imread(os.path.join(folder,f),cv2.IMREAD_GRAYSCALE)
                if im is not None: images.append(cv2.resize(im,(200,200)));labels.append(int(s["id"]))
    if not images:
        flash("No face samples yet. Enroll students first.");return redirect(url_for("students"))
    recognizer=cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(images,np.asarray(labels,dtype=np.int32));recognizer.write(MODEL_PATH)
    flash(f"Face model trained using {len(images)} samples.")
    return redirect(url_for("students"))

@app.route("/face-attendance")
@login_required
def face_attendance():
    return page("""<section class="card"><h2>Face attendance</h2><p>Allow camera permission. Keep one enrolled face in view. Review the result before relying on it.</p>
<video id="v" autoplay playsinline></video><canvas id="c" hidden></canvas><p><button id="go">Recognize and mark present</button><button id="stop" class="secondary">Stop camera</button></p><p id="msg" aria-live="polite"></p></section>
<script>let stream;const v=document.getElementById('v'),c=document.getElementById('c'),msg=document.getElementById('msg');
(async()=>{try{stream=await navigator.mediaDevices.getUserMedia({video:true,audio:false});v.srcObject=stream}catch(e){msg.textContent='Camera access failed. Use HTTPS and allow camera permission.'}})();
document.getElementById('go').onclick=async()=>{if(!v.videoWidth){msg.textContent='Camera not ready.';return}c.width=v.videoWidth;c.height=v.videoHeight;c.getContext('2d').drawImage(v,0,0);let r=await fetch('{{url_for("recognize")}}',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:c.toDataURL('image/jpeg',.85)})});let d=await r.json();msg.textContent=d.message+(d.score!==undefined?' (match score '+d.score+')':'')};
document.getElementById('stop').onclick=()=>{if(stream)stream.getTracks().forEach(t=>t.stop());v.srcObject=null;msg.textContent='Camera stopped.'};</script></section>""")

@app.route("/api/recognize",methods=["POST"])
@login_required
def recognize():
    if not model_available(): return jsonify(ok=False,message="Face model not trained or not available. Enroll faces and train the model first."),400
    frame=read_image_data((request.get_json(silent=True) or {}).get("image"))
    if frame is None: return jsonify(ok=False,message="Image could not be read."),400
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    faces=face_detector().detectMultiScale(gray,1.1,5,minSize=(80,80))
    if len(faces)!=1: return jsonify(ok=False,message="Keep exactly one face in view."),400
    x,y,w,h=faces[0]; face=cv2.resize(gray[y:y+h,x:x+w],(200,200))
    recognizer=cv2.face.LBPHFaceRecognizer_create();recognizer.read(MODEL_PATH)
    label,score=recognizer.predict(face)
    if score>65: return jsonify(ok=False,message="No confident match. Try again or use manual attendance.",score=round(float(score),1)),200
    today=date.today().isoformat(); now=datetime.now().strftime("%H:%M:%S")
    with connect_db() as c:
        s=c.execute("SELECT * FROM students WHERE id=?",(int(label),)).fetchone()
        if not s:return jsonify(ok=False,message="Matched ID is not a registered student."),400
        try:
            c.execute("INSERT INTO attendance(student_id,day,status,method,time) VALUES(?,?,?,?,?)",(s["id"],today,"Present","face recognition",now))
            c.commit();msg=f"Marked present: {s['name']} ({s['reg_no']}). Please verify the record."
        except sqlite3.IntegrityError: msg=f"{s['name']} already has an attendance record today. Check reports."
    return jsonify(ok=True,message=msg,score=round(float(score),1))

@app.route("/attendance",methods=["GET","POST"])
@login_required
def manual_attendance():
    today=date.today().isoformat()
    with connect_db() as c:
        students=c.execute("SELECT * FROM students ORDER BY name").fetchall()
        if request.method=="POST":
            sid=request.form.get("student_id",type=int); status=request.form.get("status","Present")
            if not sid or status not in ("Present","Absent"):
                flash("Choose a student and valid status.")
            else:
                try:
                    c.execute("INSERT INTO attendance(student_id,day,status,method,time) VALUES(?,?,?,?,?)",(sid,today,status,"manual",datetime.now().strftime("%H:%M:%S")))
                    c.commit();flash("Manual attendance saved.")
                except sqlite3.IntegrityError:
                    c.execute("UPDATE attendance SET status=?,method='manual',time=? WHERE student_id=? AND day=?",(status,datetime.now().strftime("%H:%M:%S"),sid,today));c.commit()
                    flash("Today's record updated manually.")
            return redirect(url_for("manual_attendance"))
    return page("""<section class="card"><h2>Manual attendance — {{today}}</h2>{% if students %}<form method="post"><label>Student<select name="student_id" required>{% for s in students %}<option value="{{s.id}}">{{s.name}} — {{s.reg_no}}</option>{% endfor %}</select></label><label>Status<select name="status"><option>Present</option><option>Absent</option></select></label><button>Save manual attendance</button></form>{% else %}<p>Add students first.</p>{% endif %}</section>""",students=students,today=today)

@app.route("/reports")
@login_required
def reports():
    with connect_db() as c:
        rows=c.execute("""SELECT s.id,s.name,s.reg_no,COUNT(a.id) recorded,
        SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) present
        FROM students s LEFT JOIN attendance a ON a.student_id=s.id GROUP BY s.id ORDER BY s.name""").fetchall()
        logs=c.execute("""SELECT s.name,s.reg_no,a.day,a.time,a.status,a.method FROM attendance a JOIN students s ON s.id=a.student_id ORDER BY a.day DESC,a.time DESC LIMIT 100""").fetchall()
    return page("""<section class="card"><h2>Attendance report</h2><p>Below 75% is a review flag, not an automatic disciplinary decision.</p><div class="tablewrap"><table><tr><th>Name</th><th>Register No.</th><th>Present</th><th>Recorded</th><th>Percentage</th><th>Flag</th></tr>
    {% for s in rows %}{% set p=s.present or 0 %}{% set n=s.recorded or 0 %}{% set pct=(100*p/n) if n else 0 %}<tr><td>{{s.name}}</td><td>{{s.reg_no}}</td><td>{{p}}</td><td>{{n}}</td><td>{{'%.1f'|format(pct)}}%</td><td>{% if n and pct<75 %}Below 75% — review{% elif n %}OK{% else %}No records{% endif %}</td></tr>{% endfor %}</table></div></section>
    <section class="card"><h2>Recent attendance records</h2><div class="tablewrap"><table><tr><th>Date</th><th>Time</th><th>Name</th><th>Status</th><th>Method</th></tr>{% for a in logs %}<tr><td>{{a.day}}</td><td>{{a.time}}</td><td>{{a.name}}</td><td>{{a.status}}</td><td>{{a.method}}</td></tr>{% else %}<tr><td colspan="5">No records yet.</td></tr>{% endfor %}</table></div></section>""",rows=rows,logs=logs)

if __name__=="__main__":
    app.run(debug=False)
