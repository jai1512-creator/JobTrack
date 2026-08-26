from flask import Flask, render_template, request, redirect
from datetime import datetime
import sqlite3

app = Flask(__name__)
def format_date(date_string):
    date_object = datetime.strptime(date_string, "%Y-%m-%d")
    return date_object.strftime("%b %d, %Y")
@app.template_filter("format_date")
def format_date_filter(date_string):
    return format_date(date_string)    
DATABASE = "jobtracker.db"
ALLOWED_STATUSES = {"applied", "interview", "selected", "rejected"}

def validate_application(company, position, applied_date, status):
    if not company.strip():
        return "Company is required."

    if not position.strip():
        return "Position is required."

    if status not in ALLOWED_STATUSES:
        return "Invalid application status."

    try:
        datetime.strptime(applied_date, "%Y-%m-%d")
    except ValueError:
        return "Invalid application date."

    return None

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.context_processor
def inject_settings():
    conn = get_db_connection()

    settings = conn.execute("""
        SELECT *
        FROM settings
        WHERE id = 1
    """).fetchone()

    conn.close()

    return {
        "app_settings": settings
    }

def init_db():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            position TEXT NOT NULL,
            applied_date TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            display_name TEXT NOT NULL DEFAULT 'Your Name',
            show_rejected INTEGER NOT NULL DEFAULT 1,
            theme TEXT NOT NULL DEFAULT 'light'
        )
    """)

    columns = conn.execute("PRAGMA table_info(settings)").fetchall()
    column_names = [column["name"] for column in columns]

    if "show_rejected" not in column_names:
        conn.execute("""
            ALTER TABLE settings
            ADD COLUMN show_rejected INTEGER NOT NULL DEFAULT 1
        """)

    if "theme" not in column_names:
        conn.execute("""
            ALTER TABLE settings
            ADD COLUMN theme TEXT NOT NULL DEFAULT 'light'
        """)

    conn.execute("""
        INSERT OR IGNORE INTO settings (
            id,
            display_name,
            show_rejected,
            theme
        )
        VALUES (1, 'Your Name', 1, 'light')
    """)

    conn.commit()
    conn.close()
     

@app.route("/")
def home():
    conn = get_db_connection()

    settings = conn.execute("""
        SELECT *
        FROM settings
        WHERE id = 1
    """).fetchone()

    if settings["show_rejected"]:
        applications = conn.execute("""
            SELECT * FROM applications
            ORDER BY id DESC
        """).fetchall()
    else:
        applications = conn.execute("""
            SELECT * FROM applications
            WHERE status != 'rejected'
            ORDER BY id DESC
        """).fetchall()

    stats = conn.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(
                CASE
                    WHEN applied_date >= date('now', 'start of month')
                    THEN 1
                    ELSE 0
                END
            ) AS this_month,
            SUM(CASE WHEN status = 'applied' THEN 1 ELSE 0 END) AS applied,
            SUM(CASE WHEN status = 'interview' THEN 1 ELSE 0 END) AS interviews,
            SUM(CASE WHEN status = 'selected' THEN 1 ELSE 0 END) AS selected,
            SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
            ROUND(
                100.0 * SUM(CASE WHEN status = 'interview' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0),
                1
            ) AS interview_rate,
            ROUND(
                100.0 * SUM(CASE WHEN status = 'selected' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0),
                1
            ) AS selection_rate
        FROM applications
    """).fetchone()

    conn.close()

    return render_template(
        "index.html",
        applications=applications,
        stats=stats,
        settings=settings,
        error=request.args.get("error"),
        edit_id=request.args.get("edit_id")
    )
  


@app.route("/analytics")
def analytics():
    conn = get_db_connection()
    stats = conn.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'applied' THEN 1 ELSE 0 END) AS applied,
            SUM(CASE WHEN status = 'interview' THEN 1 ELSE 0 END) AS interviews,
            SUM(CASE WHEN status = 'selected' THEN 1 ELSE 0 END) AS selected,
            SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected
        FROM applications
    """).fetchone()
    conn.close()

    return render_template("analytics.html", stats=stats)


@app.route("/settings")
def settings():
    conn = get_db_connection()

    settings = conn.execute("""
        SELECT * FROM settings
        WHERE id = 1
    """).fetchone()

    conn.close()

    return render_template(
        "settings.html",
        settings=settings
    )


@app.route("/save_settings", methods=["POST"])
def save_settings():
    display_name = request.form.get("display_name", "").strip()
    show_rejected = 1 if request.form.get("show_rejected") == "1" else 0
    theme = request.form.get("theme", "light")

    if not display_name:
        display_name = "Your Name"

    if theme not in {"light", "system", "dark"}:
        theme = "light"

    conn = get_db_connection()

    conn.execute("""
        UPDATE settings
        SET display_name = ?,
            show_rejected = ?,
            theme = ?
        WHERE id = 1
    """, (display_name, show_rejected, theme))

    conn.commit()
    conn.close()

    return redirect("/settings")    


@app.route("/add_application", methods=["POST"])
def add_application():
    company = request.form.get("company", "").strip()
    position = request.form.get("position", "").strip()
    applied_date = request.form.get("applied_date", "").strip()
    status = request.form.get("status", "").strip()

    error = validate_application(
        company,
        position,
        applied_date,
        status
    )

    if error:
        return redirect("/")

    conn = get_db_connection()

    conn.execute("""
        INSERT INTO applications (company, position, applied_date, status)
        VALUES (?, ?, ?, ?)
    """, (company, position, applied_date, status))

    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/delete_application/<int:application_id>", methods=["POST"])
def delete_application(application_id):
    conn = get_db_connection()

    conn.execute(
        "DELETE FROM applications WHERE id = ?",
        (application_id,)
    )

    conn.commit()
    conn.close()

    return redirect("/")

@app.route("/clear_applications", methods=["POST"])
def clear_applications():
    conn = get_db_connection()

    conn.execute("DELETE FROM applications")

    conn.commit()
    conn.close()

    return redirect("/")

@app.route("/edit_application/<int:application_id>", methods=["POST"])
def edit_application(application_id):
    company = request.form.get("company", "").strip()
    position = request.form.get("position", "").strip()
    applied_date = request.form.get("applied_date", "").strip()
    status = request.form.get("status", "").strip()

    error = validate_application(
        company,
        position,
        applied_date,
        status
    )

    if error:
        return redirect(
            f"/?error={error}&edit_id={application_id}"
        )

    conn = get_db_connection()

    conn.execute("""
        UPDATE applications
        SET company = ?, position = ?, applied_date = ?, status = ?
        WHERE id = ?
    """, (
        company,
        position,
        applied_date,
        status,
        application_id
    ))

    conn.commit()
    conn.close()

    return redirect("/")
   

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
