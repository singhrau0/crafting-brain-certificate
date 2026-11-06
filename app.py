from datetime import date, timedelta
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import uuid

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from dotenv import load_dotenv
from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for, make_response)
from itsdangerous import URLSafeTimedSerializer, BadSignature
from certificate import certificate, course_duration, completion_statement

load_dotenv(Path(__file__).parent / ".env")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or "crafting-brain-local-session-key-2026"
LOGIN_EMAIL = "demo@craftingbrain.com"
LOGIN_PASSWORD = "Demo@1234"
app.config.update(SESSION_COOKIE_SECURE=bool(os.getenv("RENDER") or os.getenv("HTTPS_ONLY") == "1"),
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=16384)
courses = ["Gen AI Internship Course", "Data Analytics Internship Course"]
tokens = URLSafeTimedSerializer(app.secret_key, salt="certificate-preview")
dbpath = Path(os.getenv("DATABASE_PATH", "instance/certificates.sqlite3"))
if os.getenv("RENDER") and not dbpath.is_absolute():
    raise ValueError("Set DATABASE_PATH to a file on your persistent disk.")
dbpath.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(dbpath) as setup:
    setup.execute("""CREATE TABLE IF NOT EXISTS certificates (
        id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, details TEXT NOT NULL,
        pdf BLOB NOT NULL, employee TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP,
        status TEXT NOT NULL DEFAULT 'Unsent', provider_id TEXT)""")
    columns = {row[1] for row in setup.execute("PRAGMA table_info(certificates)")}
    if "mail_error" not in columns:
        setup.execute("ALTER TABLE certificates ADD COLUMN mail_error TEXT")


def db():
    if "db" not in g:
        g.db = sqlite3.connect(dbpath, timeout=120)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    if "db" in g:
        g.db.close()


@app.before_request
def csrf():
    session.setdefault("csrf", secrets.token_hex(24))
    if request.method == "POST" and not secrets.compare_digest(
            session["csrf"].encode(), request.form.get("csrf", "").encode()):
        abort(400, "Session expired. Reload the page and try again.")


@app.after_request
def headers(response):
    response.headers.update({"Cache-Control": "no-store", "X-Frame-Options": "SAMEORIGIN",
                             "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})
    return response


def protected(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if session.get("employee") != LOGIN_EMAIL:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("email", "").strip().lower()
        if (secrets.compare_digest(user.encode(), LOGIN_EMAIL.encode())
                and secrets.compare_digest(request.form.get("password", "").encode(), LOGIN_PASSWORD.encode())):
            session.clear()
            session["employee"] = user
            session.permanent = True
            return redirect(url_for("home"))
        flash("Check your email and password.")
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def mail_ready():
    return bool(os.getenv("SMTP_EMAIL", "").strip() and os.getenv("SMTP_APP_PASSWORD", "").strip())


@app.get("/")
@protected
def home():
    return render_template("form.html", courses=courses, fields={})


def validated(form):
    course = form.get("course", "")
    if course != "Other" and course not in courses:
        raise ValueError("Select a course.")
    data = {key: " ".join(form.get(key, "").split()) for key in ("name", "email", "joined", "completed")}
    data["course"] = " ".join(form.get("other", "").split()) if course == "Other" else course
    for key in ("name", "course"):
        value = data[key]
        if not 1 <= len(value) <= 100 or not value.isprintable():
            raise ValueError("Enter a name and course of 1–100 printable characters.")
        try:
            value.encode("cp1252")
        except UnicodeEncodeError:
            raise ValueError("Use Latin-script spelling for this certificate template.") from None
    if len(data["email"]) > 254 or not re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", data["email"]):
        raise ValueError("Enter one valid candidate email address.")
    try:
        start, end = (date.fromisoformat(data[k]) for k in ("joined", "completed"))
    except ValueError:
        raise ValueError("Enter both course dates.") from None
    if not start <= end <= date.today():
        raise ValueError("Completion must be on or after joining and cannot be in the future.")
    data["summary"] = " ".join(form.get("summary", "").split())
    if len(data["summary"]) > 220 or (data["summary"] and not data["summary"].isprintable()):
        raise ValueError("Keep the course work summary within 220 printable characters.")
    try:
        data["summary"].encode("cp1252")
    except UnicodeEncodeError:
        raise ValueError("Use Latin-script spelling for the course work summary.") from None
    if any(len(word) > 40 for word in data["summary"].split()):
        raise ValueError("Use words of at most 40 characters in the course work summary.")
    data.update(joined=start.isoformat(), completed=end.isoformat())
    return data


def draft():
    try:
        employee, data = tokens.loads(request.form.get("draft", ""), max_age=1800)
    except BadSignature:
        abort(400, "Preview expired. Start a new preview.")
    if employee != session["employee"]:
        abort(403)
    return data


@app.post("/preview")
@protected
def preview():
    try:
        data = validated(request.form)
    except ValueError as exc:
        flash(str(exc))
        return render_template("form.html", courses=courses, fields=request.form), 400
    token = tokens.dumps([session["employee"], data])
    return render_template("review.html", data=data, token=token, ready=mail_ready(),
                           duration=course_duration(data), statement=completion_statement(data))


def pdf_response(content, filename):
    response = make_response(content)
    response.headers.update({"Content-Type": "application/pdf",
                             "Content-Disposition": f'inline; filename="{filename}.pdf"'})
    return response


@app.post("/preview/pdf")
@protected
def preview_pdf():
    return pdf_response(certificate(draft()), "preview")


def send_record(identifier):
    if not mail_ready():
        flash("Certificate saved. Configure email to send it.")
        return
    conn = db()
    with conn:
        claimed = conn.execute("""UPDATE certificates SET status='Sending'
            WHERE id=? AND status IN ('Unsent','Rejected')""", (identifier,)).rowcount
    if not claimed:
        flash("This email is already being processed or has a recorded outcome.")
        return
    row = conn.execute("SELECT * FROM certificates WHERE id=?", (identifier,)).fetchone()
    data = json.loads(row["details"])
    status, provider_id = "Rejected", None
    smtp = None
    submitted = False
    mail_error = None
    try:
        sender = os.environ["SMTP_EMAIL"].strip()
        message = EmailMessage()
        message["From"] = sender
        message["To"] = data["email"]
        message["Subject"] = "Your Crafting Brain certificate of completion"
        message["Date"] = formatdate(localtime=False)
        message["Message-ID"] = make_msgid()
        message.set_content(
            f"Hello {data['name']},\n\n"
            f"Congratulations on completing {data['course']}!\n"
            f"Course duration: {course_duration(data)}\n\n"
            "Your certificate of completion is attached to this email. "
            "Thank you for learning with Crafting Brain. "
            "We wish you continued success in your learning and career.\n\n"
            f"Certificate ID: {identifier}\n\nWarm regards,\nCrafting Brain")
        message.add_attachment(bytes(row["pdf"]), maintype="application", subtype="pdf",
                               filename=identifier + ".pdf")
        host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        port = int(os.getenv("SMTP_PORT", "587"))
        context = ssl.create_default_context()
        if port == 465:
            smtp = smtplib.SMTP_SSL(host, port, timeout=120, context=context)
        else:
            smtp = smtplib.SMTP(host, port, timeout=120)
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
        smtp.login(sender, os.environ["SMTP_APP_PASSWORD"].strip())
        provider_id = str(message["Message-ID"])
        submitted = True
        smtp.send_message(message, from_addr=sender, to_addrs=[data["email"]])
        status, provider_id = "Accepted", str(message["Message-ID"])
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused,
            smtplib.SMTPDataError) as exc:
        status = "Rejected"
        mail_error = type(exc).__name__ + " (SMTP " + str(getattr(exc, "smtp_code", "recipient refused")) + ")"
    except (smtplib.SMTPException, OSError, ValueError) as exc:
        # A disconnect during submission may happen after the server accepted mail.
        status = "Check provider" if submitted else "Rejected"
        mail_error = type(exc).__name__ + (" during message submission" if submitted else " before message submission")
        app.logger.warning("SMTP failure for %s: %s", identifier, mail_error)
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except (smtplib.SMTPException, OSError):
                smtp.close()
    with conn:
        conn.execute("UPDATE certificates SET status=?, provider_id=?, mail_error=? WHERE id=?",
                     (status, provider_id, mail_error, identifier))
    if status == "Accepted":
        flash("Certificate emailed to " + data["email"] + ". The mail server accepted it for delivery.")
    elif status == "Rejected":
        flash("Certificate saved, but email could not be sent. Check the sender email, app password and SMTP settings, then retry from history.")
    else:
        flash("Certificate saved. Email delivery is uncertain; check your mail provider before retrying.")


@app.post("/issue")
@protected
def issue():
    data = draft()
    key = [data[k].casefold() for k in ("email", "course", "joined", "completed")]
    fingerprint = hashlib.sha256(json.dumps(key).encode()).hexdigest()
    identifier = "CB-" + uuid.uuid4().hex.upper()
    conn = db()
    with conn:
        created = conn.execute("""INSERT INTO certificates
            (id,fingerprint,details,pdf,employee) VALUES (?,?,?,?,?)
            ON CONFLICT(fingerprint) DO NOTHING""",
            (identifier, fingerprint, json.dumps(data), certificate(data, identifier), session["employee"])).rowcount
    if not created:
        flash("Already issued for this email, course and date range. See the original in history.")
    elif request.form.get("action") == "send":
        send_record(identifier)
    else:
        flash("Certificate issued and saved.")
    return redirect(url_for("history"))


@app.get("/history")
@protected
def history():
    records = db().execute("""SELECT id,details,created,employee,status,mail_error FROM certificates
                              ORDER BY created DESC, rowid DESC""")
    return render_template("history.html", records=[dict(row, data=json.loads(row["details"])) for row in records],
                           ready=mail_ready())


@app.post("/records/<identifier>/send")
@protected
def send(identifier):
    send_record(identifier)
    return redirect(url_for("history"))


@app.get("/records/<identifier>/pdf")
@protected
def download(identifier):
    row = db().execute("SELECT pdf FROM certificates WHERE id=?", (identifier,)).fetchone()
    if not row:
        abort(404)
    return pdf_response(row["pdf"], identifier)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5003")))
