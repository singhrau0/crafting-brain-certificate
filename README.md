# Crafting Brain certificate desk

A single-user desk to preview, issue, download and optionally email professional landscape A4 certificates.

## Run locally

Use Python 3.11 or newer:

~~~sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./start.sh
~~~

The local server uses port 5001 to avoid the macOS AirPlay/Control Center port 5000 conflict.
You can also run `.venv/bin/python app.py` directly.

Open http://127.0.0.1:5001 and sign in:

- Email: **demo@craftingbrain.com**
- Password: **Demo@1234**

This is the one fixed account. No employee setup or management is required.
The supplied static/IMG_8836.jpg signature is included automatically in every new PDF.
Presets are Gen AI Internship Course and Data Analytics Internship Course.
Choose Other to enter a custom course name (up to 100 characters).
Duration uses elapsed calendar months and remaining days (same-day courses show 1 day).
An optional course work summary (220 characters) records actual topics or projects; otherwise a general completion statement is used.
The template supports Western European Latin text and wraps long names and course titles.

Preview does not save a record. Issue saves the PDF and its unique certificate ID.
History preserves original PDFs; template changes affect new certificates only.
Duplicate email/course/date combinations return the original record.

## Email

Fill in the local .env file:

~~~dotenv
SMTP_EMAIL=your-email@gmail.com
SMTP_APP_PASSWORD=your-app-password
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
~~~

Use your mailbox app password, then restart the app. The .env file is ignored by Git.
For other providers, use their SMTP host and port. Port 465 uses TLS immediately;
other ports use STARTTLS. Authentication always happens over TLS.
The sender mailbox is independent of the fixed desk login.

Enter the candidate email in the form, preview the certificate, then choose
**Issue & email certificate**. The saved PDF is sent as an attachment.
Saved, unsent certificates can also be sent from History.
Accepted means the SMTP server accepted the message, not confirmed inbox delivery.
Rejected can be retried after fixing settings. Check provider or Sending requires
checking the mailbox/provider before reconciliation to avoid duplicate mail.
On Render, add these same SMTP variables in the service environment; local .env is not deployed.

## Render (after manual approval)

The included render.yaml uses a Starter service and persistent disk for SQLite.
Connect the project repository as a Render Blueprint when ready to deploy.
Render generates SECRET_KEY; DATABASE_PATH points to the mounted disk.
No employee variables are needed. Keep the signature JPG in the repository.
A stable SECRET_KEY keeps sessions valid across restarts. Local development uses a fixed fallback.
HTTPS cookies are enabled on Render. Sessions expire after eight hours.
The fixed login is defined in app.py.

## Tests

~~~sh
python -m unittest discover -s tests -v
~~~

Tests use a temporary database and mock email delivery; they never send real email.
