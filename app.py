import csv, os, sqlite3, tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, date
from hashlib import pbkdf2_hmac
import secrets, hmac

HERE=os.path.abspath(os.path.dirname(__file__)); DB=os.path.join(HERE,'attendance_system.db'); MIN_ATTENDANCE=75

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c

def init_db():
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,pwhash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS students(register_no TEXT PRIMARY KEY,name TEXT NOT NULL,department TEXT NOT NULL,year TEXT NOT NULL,section TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY,register_no TEXT NOT NULL,day TEXT NOT NULL,time TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Present',UNIQUE(register_no,day),FOREIGN KEY(register_no) REFERENCES students(register_no) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        INSERT OR IGNORE INTO settings(key,value) VALUES('working_days','30');''')

def hashpw(p):
    s=secrets.token_bytes(16); return s.hex()+'$'+pbkdf2_hmac('sha256',p.encode(),s,200000).hex()
def checkpw(p,v):
    try:
        s,h=v.split('$'); return hmac.compare_digest(pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(s),200000).hex(),h)
    except Exception: return False

def working_days():
    with db() as c: r=c.execute("SELECT value FROM settings WHERE key='working_days'").fetchone()
    return max(1,int(r['value'] if r else 30))

class App:
 def __init__(self,root):
    self.root=root; root.title('SmartAttend | Attendance Management'); root.geometry('1100x700'); root.minsize(850,560); root.configure(bg='#f3f6fb')
    self.style=ttk.Style(); self.style.theme_use('clam'); self.style.configure('Treeview',rowheight=28,font=('Segoe UI',10)); self.style.configure('Treeview.Heading',font=('Segoe UI',9,'bold')); self.style.configure('TButton',padding=7,font=('Segoe UI',10))
    os.makedirs(os.path.join(HERE,'dataset'),exist_ok=True); init_db(); self.admin=None; self.auth()
 def clear(self):
    for w in self.root.winfo_children(): w.destroy()
 def count_admins(self):
    with db() as c: return c.execute('SELECT COUNT(*) n FROM admins').fetchone()['n']
 def auth(self):
    self.clear(); box=tk.Frame(self.root,bg='white',padx=38,pady=32,highlightbackground='#dfe6f0',highlightthickness=1); box.place(relx=.5,rely=.5,anchor='center',width=420)
    tk.Label(box,text='✓  SmartAttend',bg='white',fg='#4263eb',font=('Segoe UI',22,'bold')).pack(anchor='w')
    tk.Label(box,text='Automated Attendance & Detention Reporting',bg='white',fg='#7c889b',font=('Segoe UI',9)).pack(anchor='w',pady=(4,22))
    first=self.count_admins()==0; tk.Label(box,text='Create administrator account' if first else 'Administrator login',bg='white',fg='#1c2b42',font=('Segoe UI',15,'bold')).pack(anchor='w',pady=(0,14))
    u=tk.StringVar(); p=tk.StringVar(); cp=tk.StringVar()
    def field(label,var,secret=False):
        tk.Label(box,text=label,bg='white',fg='#526078').pack(anchor='w'); e=ttk.Entry(box,textvariable=var,show='•' if secret else ''); e.pack(fill='x',ipady=5,pady=(5,12)); return e
    ue=field('Username',u); field('Password',p,True)
    if first: field('Confirm password',cp,True)
    def submit():
        name=u.get().strip(); pw=p.get()
        if first:
            if len(name)<3: return messagebox.showerror('Validation','Username must have at least 3 characters.')
            if len(pw)<8: return messagebox.showerror('Validation','Password must have at least 8 characters.')
            if pw!=cp.get(): return messagebox.showerror('Validation','Passwords do not match.')
            try:
                with db() as c: c.execute('INSERT INTO admins(username,pwhash) VALUES(?,?)',(name,hashpw(pw)))
                messagebox.showinfo('SmartAttend','Admin account created. Please sign in.'); self.auth()
            except sqlite3.IntegrityError: messagebox.showerror('Account','Username already exists.')
        else:
            with db() as c: a=c.execute('SELECT * FROM admins WHERE username=?',(name,)).fetchone()
            if a and checkpw(pw,a['pwhash']): self.admin=name; self.dashboard()
            else: messagebox.showerror('Login failed','Incorrect username or password.')
    ttk.Button(box,text='Create account' if first else 'Sign in',command=submit).pack(fill='x',ipady=4,pady=(4,12))
    tk.Label(box,text='Student list starts empty. Register students after signing in.',bg='white',fg='#8994a5',font=('Segoe UI',8)).pack(anchor='w')
    self.root.bind('<Return>',lambda e:submit()); ue.focus_set()
 def shell(self,title,subtitle):
    self.clear(); self.root.unbind('<Return>'); side=tk.Frame(self.root,bg='#15243b',width=205); side.pack(side='left',fill='y'); side.pack_propagate(False)
    tk.Label(side,text='✓ SmartAttend',bg='#15243b',fg='white',font=('Segoe UI',17,'bold')).pack(anchor='w',padx=16,pady=(24,4)); tk.Label(side,text='ATTENDANCE SUITE',bg='#15243b',fg='#8e9db6',font=('Segoe UI',8,'bold')).pack(anchor='w',padx=19,pady=(0,24))
    for text,fn in [('Dashboard',self.dashboard),('Students',self.students),('Attendance',self.attendance),('Detention Reports',self.reports),('Settings',self.settings)]: ttk.Button(side,text=text,command=fn).pack(fill='x',padx=12,pady=4)
    ttk.Button(side,text='Log out',command=self.auth).pack(side='bottom',fill='x',padx=12,pady=16)
    self.body=tk.Frame(self.root,bg='#f3f6fb',padx=26,pady=22); self.body.pack(side='left',fill='both',expand=True)
    tk.Label(self.body,text=title,bg='#f3f6fb',fg='#17243a',font=('Segoe UI',23,'bold')).pack(anchor='w'); tk.Label(self.body,text=subtitle,bg='#f3f6fb',fg='#78859a').pack(anchor='w',pady=(4,18))
 def tree(self,parent,cols,heads):
    wrap=tk.Frame(parent,bg='white'); wrap.pack(fill='both',expand=True,pady=(10,0)); t=ttk.Treeview(wrap,columns=cols,show='headings')
    for c,h in zip(cols,heads): t.heading(c,text=h); t.column(c,width=130,anchor='w')
    sb=ttk.Scrollbar(wrap,orient='vertical',command=t.yview); t.configure(yscrollcommand=sb.set); t.pack(side='left',fill='both',expand=True); sb.pack(side='right',fill='y'); return t
 def dashboard(self):
    self.shell('Dashboard',f'Welcome, {self.admin}. Your attendance workspace is ready.')
    with db() as c:
        n=c.execute('SELECT COUNT(*) n FROM students').fetchone()['n']; today=c.execute('SELECT COUNT(*) n FROM attendance WHERE day=?',(date.today().isoformat(),)).fetchone()['n']; rows=c.execute('SELECT s.register_no,s.name,COUNT(a.id) present FROM students s LEFT JOIN attendance a ON a.register_no=s.register_no GROUP BY s.register_no ORDER BY s.name').fetchall()
    wd=working_days(); shortage=sum(1 for r in rows if r['present']/wd*100<MIN_ATTENDANCE)
    cards=tk.Frame(self.body,bg='#f3f6fb'); cards.pack(fill='x')
    for title,val,sub in [('Total students',n,'Registered profiles'),('Present today',today,date.today().isoformat()),('Attendance shortage',shortage,'Below 75% threshold'),('Required attendance','75%','Project rule')]:
        f=tk.Frame(cards,bg='white',padx=16,pady=15,highlightbackground='#e4eaf2',highlightthickness=1); f.pack(side='left',fill='both',expand=True,padx=(0,8)); tk.Label(f,text=title,bg='white',fg='#7b8799').pack(anchor='w'); tk.Label(f,text=str(val),bg='white',fg='#1c2b42',font=('Segoe UI',23,'bold')).pack(anchor='w',pady=7); tk.Label(f,text=sub,bg='white',fg='#9aa4b2',font=('Segoe UI',8)).pack(anchor='w')
    panel=tk.Frame(self.body,bg='white',padx=20,pady=18); panel.pack(fill='both',expand=True,pady=18); tk.Label(panel,text='Student list',bg='white',fg='#1c2b42',font=('Segoe UI',14,'bold')).pack(anchor='w')
    if not rows:
        tk.Label(panel,text='No students registered yet',bg='white',fg='#334158',font=('Segoe UI',14,'bold')).pack(pady=(55,8)); tk.Label(panel,text='The list is empty. Register your first student to get started.',bg='white',fg='#8792a3').pack(pady=(0,15)); ttk.Button(panel,text='+ Register first student',command=self.students).pack()
    else:
        t=self.tree(panel,('register_no','name','present'),('Register number','Student name','Days present'))
        for r in rows[:10]: t.insert('','end',values=(r['register_no'],r['name'],r['present']))
 def students(self):
    self.shell('Students','Register, search and manage student profiles.')
    form=tk.LabelFrame(self.body,text='Register a student',bg='white',fg='#344258',padx=12,pady=12); form.pack(fill='x',pady=(0,14)); keys=['register_no','name','department','year','section']; labels=['Register number','Full name','Department','Year','Section']; entries={}
    for i,(k,lbl) in enumerate(zip(keys,labels)):
        cell=tk.Frame(form,bg='white'); cell.grid(row=i//3,column=i%3,sticky='ew',padx=6,pady=6); tk.Label(cell,text=lbl,bg='white',fg='#56647a').pack(anchor='w'); e=ttk.Entry(cell); e.pack(fill='x',ipady=4,pady=4); entries[k]=e
    for i in range(3): form.grid_columnconfigure(i,weight=1)
    def add():
        vals=[entries[k].get().strip() for k in keys]
        if not all(vals): return messagebox.showerror('Validation','Complete all student fields.')
        try:
            with db() as c: c.execute('INSERT INTO students(register_no,name,department,year,section) VALUES(?,?,?,?,?)',vals)
            messagebox.showinfo('SmartAttend','Student added.'); self.students()
        except sqlite3.IntegrityError: messagebox.showerror('Duplicate','That register number already exists.')
    ttk.Button(form,text='+ Add student',command=add).grid(row=1,column=2,sticky='e',padx=6,pady=6)
    row=tk.Frame(self.body,bg='#f3f6fb'); row.pack(fill='x'); tk.Label(row,text='Registered students',bg='#f3f6fb',fg='#1c2b42',font=('Segoe UI',14,'bold')).pack(side='left'); q=tk.StringVar(); ttk.Entry(row,textvariable=q,width=25).pack(side='right',padx=7)
    panel=tk.Frame(self.body,bg='white',padx=12,pady=12); panel.pack(fill='both',expand=True,pady=8); t=self.tree(panel,keys,labels)
    def refresh():
        t.delete(*t.get_children()); term='%'+q.get().strip()+'%'
        with db() as c: rs=c.execute('SELECT * FROM students WHERE register_no LIKE ? OR name LIKE ? ORDER BY name',(term,term)).fetchall()
        for r in rs: t.insert('','end',values=tuple(r[k] for k in keys))
    ttk.Button(row,text='Search',command=refresh).pack(side='right')
    def remove():
        sel=t.selection()
        if not sel: return messagebox.showinfo('Select student','Select a row first.')
        reg=t.item(sel[0],'values')[0]
        if messagebox.askyesno('Confirm',f'Remove {reg} and its attendance records?'):
            with db() as c: c.execute('DELETE FROM students WHERE register_no=?',(reg,))
            refresh()
    ttk.Button(self.body,text='Remove selected student',command=remove).pack(anchor='e',pady=5); refresh()
 def attendance(self):
    self.shell('Attendance','Record a student as present for today. Duplicate daily entries are blocked.')
    panel=tk.Frame(self.body,bg='white',padx=20,pady=18); panel.pack(fill='x',pady=(0,14)); tk.Label(panel,text='Mark present',bg='white',fg='#1c2b42',font=('Segoe UI',14,'bold')).pack(anchor='w')
    with db() as c: students=c.execute('SELECT register_no,name FROM students ORDER BY name').fetchall()
    opts=[f"{s['register_no']} — {s['name']}" for s in students]; chosen=tk.StringVar(value=opts[0] if opts else ''); combo=ttk.Combobox(panel,textvariable=chosen,values=opts,state='readonly',width=55); combo.pack(anchor='w',pady=10)
    def mark():
        if ' — ' not in chosen.get(): return messagebox.showwarning('No students','Register a student first.')
        reg=chosen.get().split(' — ',1)[0]; now=datetime.now()
        try:
            with db() as c: c.execute('INSERT INTO attendance(register_no,day,time,status) VALUES(?,?,?,?)',(reg,now.strftime('%Y-%m-%d'),now.strftime('%H:%M:%S'),'Present'))
            messagebox.showinfo('Attendance','Attendance recorded.'); self.attendance()
        except sqlite3.IntegrityError: messagebox.showwarning('Already recorded','Attendance has already been recorded for this student today.')
    ttk.Button(panel,text='✓ Mark present',command=mark).pack(anchor='w')
    p=tk.Frame(self.body,bg='white',padx=15,pady=15); p.pack(fill='both',expand=True); tk.Label(p,text="Today's attendance log",bg='white',fg='#1c2b42',font=('Segoe UI',14,'bold')).pack(anchor='w'); t=self.tree(p,('register_no','name','day','time','status'),('Register number','Student','Date','Time','Status'))
    with db() as c: rows=c.execute('SELECT a.*,s.name FROM attendance a JOIN students s ON s.register_no=a.register_no WHERE a.day=? ORDER BY a.time DESC',(date.today().isoformat(),)).fetchall()
    for r in rows: t.insert('','end',values=(r['register_no'],r['name'],r['day'],r['time'],r['status']))
 def reports(self):
    self.shell('Detention Reports','Students below 75% attendance are flagged for administrative review.')
    wd=working_days(); panel=tk.Frame(self.body,bg='white',padx=16,pady=16); panel.pack(fill='both',expand=True); top=tk.Frame(panel,bg='white'); top.pack(fill='x'); tk.Label(top,text=f'Working days: {wd}    |    Threshold: 75%',bg='white',fg='#65738a').pack(side='left'); ttk.Button(top,text='Export CSV',command=self.export).pack(side='right')
    t=self.tree(panel,('register_no','name','present','working','pct','status'),('Register number','Student','Present days','Working days','Attendance %','Status'))
    with db() as c: rows=c.execute('SELECT s.register_no,s.name,COUNT(a.id) present FROM students s LEFT JOIN attendance a ON a.register_no=s.register_no GROUP BY s.register_no ORDER BY s.name').fetchall()
    for r in rows:
        pct=min(100,r['present']/wd*100); status='Eligible' if pct>=MIN_ATTENDANCE else 'DETENTION / DEFICIT'; t.insert('','end',values=(r['register_no'],r['name'],r['present'],wd,f'{pct:.2f}%',status))
    if not rows: tk.Label(panel,text='No report data yet. Register students and record attendance first.',bg='white',fg='#8792a3').pack(pady=24)
 def export(self):
    path=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV files','*.csv')],initialfile='smartattend_report.csv')
    if not path:return
    wd=working_days()
    with db() as c: rows=c.execute('SELECT s.register_no,s.name,s.department,s.year,s.section,COUNT(a.id) present FROM students s LEFT JOIN attendance a ON a.register_no=s.register_no GROUP BY s.register_no ORDER BY s.name').fetchall()
    with open(path,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f); w.writerow(['Register Number','Name','Department','Year','Section','Days Present','Working Days','Attendance %','Status'])
        for r in rows:
            pct=min(100,r['present']/wd*100); w.writerow([r['register_no'],r['name'],r['department'],r['year'],r['section'],r['present'],wd,f'{pct:.2f}','Eligible' if pct>=MIN_ATTENDANCE else 'DETENTION / DEFICIT'])
    messagebox.showinfo('Export complete','CSV report saved successfully.')
 def settings(self):
    self.shell('Settings','Configure the working-day total used by attendance reports.')
    p=tk.Frame(self.body,bg='white',padx=22,pady=22); p.pack(anchor='nw',fill='x'); tk.Label(p,text='Attendance rules',bg='white',fg='#1c2b42',font=('Segoe UI',14,'bold')).pack(anchor='w'); tk.Label(p,text='Total working days (1–366)',bg='white',fg='#56647a').pack(anchor='w',pady=(18,5)); v=tk.StringVar(value=str(working_days())); ttk.Entry(p,textvariable=v,width=18).pack(anchor='w'); tk.Label(p,text='Minimum attendance threshold: 75%',bg='white',fg='#78859a').pack(anchor='w',pady=12)
    def save():
        try:
            n=int(v.get())
            if not 1<=n<=366: raise ValueError
            with db() as c: c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('working_days',?)",(str(n),))
            messagebox.showinfo('Settings','Working days saved.')
        except ValueError: messagebox.showerror('Invalid value','Enter a whole number from 1 to 366.')
    ttk.Button(p,text='Save settings',command=save).pack(anchor='w')

if __name__=='__main__':
 root=tk.Tk(); App(root); root.mainloop()
