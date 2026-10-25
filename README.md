# SmartAttend Desktop Application

Python desktop application based on the uploaded project report: Automated Attendance Tracking and Detention Reporting System Using Face Recognition.

## Features
- First-run admin account setup and login/logout
- Empty student list on first launch (no sample records)
- Student registration, search, and removal
- Manual daily attendance with duplicate-per-day prevention
- Today's attendance log
- Attendance percentage and 75% detention/deficit report
- CSV export and configurable working days (default 30)
- SQLite database created automatically

## Run on Windows
1. Extract the ZIP file.
2. Open the extracted folder in File Explorer.
3. Click the folder address bar, type `cmd`, and press Enter.
4. Run: `py app.py`
5. Create an administrator username and password when prompted.

The core app uses Python's standard library; no `pip install` is required. Tkinter is normally included with the Windows Python installer.

## Facial recognition status
The report describes a Tkinter GUI, OpenCV, `face_recognition`, webcam dataset capture, and live matching. This deliverable implements the GUI, authentication, SQLite records, attendance, and reporting, but live facial recognition/webcam capture is **not yet connected**. It should be integrated and tested separately with compatible camera and Python dependencies. Manual attendance is clearly marked as manual and does not claim facial recognition occurred.

## Data
`attendance_system.db` is created beside `app.py`. To reset the demo, close the app and delete that database file; this removes saved admin, student, attendance, and settings records. The `dataset` folder is reserved for future face images.

Use real student records or face images only with appropriate permission. This is a local educational prototype, not a production-ready institutional system.
