import os
import tempfile
import unittest
from unittest.mock import patch, Mock

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = TEMP.name + "/test.sqlite3"
import app as desk


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.client = desk.app.test_client()
        self.client.get("/login")
        with desk.app.app_context():
            desk.db().execute("DELETE FROM certificates")
            desk.db().commit()

    def post(self, path, **data):
        with self.client.session_transaction() as session:
            data["csrf"] = session["csrf"]
        response = self.client.post(path, data=data)
        self.client.get("/login")  # Populate CSRF after session rotation.
        return response

    def login(self):
        return self.post("/login", email=desk.LOGIN_EMAIL, password=desk.LOGIN_PASSWORD)

    def details(self, **changes):
        data = dict(name="Aarav Sharma", email="aarav@example.com",
                    course=desk.courses[0], joined="2026-01-01", completed="2026-03-01")
        data.update(changes)
        return data

    def token(self, **changes):
        data = desk.validated(self.details(**changes))
        return desk.tokens.dumps([desk.LOGIN_EMAIL, data])

    def test_login_access_and_logout(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertIn(b"Check your email", self.post("/login", email=desk.LOGIN_EMAIL, password="wrong").data)
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.post("/logout")
        self.assertEqual(self.client.get("/history").status_code, 302)

    def test_csrf(self):
        self.assertEqual(self.client.post("/login", data={}).status_code, 400)

    def test_courses_and_custom_validation(self):
        self.login()
        for course in desk.courses:
            self.assertEqual(self.post("/preview", **self.details(course=course)).status_code, 200)
        self.assertEqual(self.post("/preview", **self.details(course="Other", other="Advanced AI Internship")).status_code, 200)
        for changes in (dict(course="Other", other=" "), dict(course="invalid"),
                        dict(joined="2026-04-01"), dict(email="bad"),
                        dict(completed="2099-01-01"), dict(name="A"*101)):
            self.assertEqual(self.post("/preview", **self.details(**changes)).status_code, 400)

    def test_preview_issue_download_and_duplicate(self):
        self.login()
        token = self.token()
        preview = self.post("/preview/pdf", draft=token)
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.data.startswith(b"%PDF"))
        self.post("/issue", draft=token, action="save")
        self.post("/issue", draft=token, action="save")
        with desk.app.app_context():
            records = desk.db().execute("SELECT * FROM certificates").fetchall()
        self.assertEqual(len(records), 1)
        saved = self.client.get("/records/" + records[0]["id"] + "/pdf")
        self.assertEqual(saved.data, records[0]["pdf"])
        self.assertIn(b"Aarav Sharma", self.client.get("/history").data)
        self.assertEqual(self.client.get("/records/missing/pdf").status_code, 404)
        self.post("/logout")
        self.assertEqual(self.client.get("/records/" + records[0]["id"] + "/pdf").status_code, 302)

    def test_duration_and_summary(self):
        from certificate import course_duration
        for start, end, expected in [
            ("2026-01-01", "2026-04-01", "3 months"),
            ("2026-01-01", "2026-07-01", "6 months"),
            ("2026-01-31", "2026-02-28", "1 month"),
            ("2026-01-01", "2026-04-05", "3 months and 4 days"),
            ("2026-01-01", "2026-01-01", "1 day"),
        ]:
            self.assertEqual(course_duration(dict(joined=start, completed=end)), expected)
        self.login()
        response = self.post("/preview", **self.details(summary="Completed Python assignments and a capstone project."))
        self.assertIn(b"Completed Python assignments", response.data)
        self.assertIn(b"2 months", response.data)
        self.assertEqual(self.post("/preview", **self.details(summary="a " * 111)).status_code, 400)

    def test_tampered_preview(self):
        self.login()
        self.assertEqual(self.post("/preview/pdf", draft="invalid").status_code, 400)

    @patch.dict(os.environ, {"SMTP_EMAIL": "sender@example.com", "SMTP_APP_PASSWORD": "test", "SMTP_PORT": "587"})
    @patch("app.smtplib.SMTP")
    def test_email_and_no_duplicate_send(self, smtp_class):
        smtp = smtp_class.return_value
        self.login()
        self.post("/issue", draft=self.token(), action="send")
        with desk.app.app_context():
            row = desk.db().execute("SELECT * FROM certificates").fetchone()
        self.assertEqual(row["status"], "Accepted")
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("sender@example.com", "test")
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["To"], "aarav@example.com")
        self.assertEqual(message["From"], "sender@example.com")
        attachment = list(message.iter_attachments())[0]
        self.assertEqual(attachment.get_content_type(), "application/pdf")
        self.assertEqual(attachment.get_payload(decode=True), row["pdf"])
        self.post("/records/" + row["id"] + "/send")
        self.assertEqual(smtp.send_message.call_count, 1)

    @patch.dict(os.environ, {"SMTP_EMAIL": "sender@example.com", "SMTP_APP_PASSWORD": "test", "SMTP_PORT": "587"})
    @patch("app.smtplib.SMTP")
    def test_authentication_failure_is_retryable(self, smtp_class):
        import smtplib
        smtp_class.return_value.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
        self.login()
        self.post("/issue", draft=self.token(), action="send")
        with desk.app.app_context():
            row = desk.db().execute("SELECT * FROM certificates").fetchone()
        self.assertEqual(row["status"], "Rejected")
        smtp_class.return_value.send_message.assert_not_called()

    @patch.dict(os.environ, {"SMTP_EMAIL": "sender@example.com", "SMTP_APP_PASSWORD": "test", "SMTP_PORT": "465"})
    @patch("app.smtplib.SMTP_SSL")
    def test_uncertain_submission_blocks_retry(self, smtp_class):
        smtp_class.return_value.send_message.side_effect = TimeoutError()
        self.login()
        self.post("/issue", draft=self.token(), action="send")
        with desk.app.app_context():
            row = desk.db().execute("SELECT * FROM certificates").fetchone()
        self.assertEqual(row["status"], "Check provider")
        self.post("/records/" + row["id"] + "/send")
        self.assertEqual(smtp_class.return_value.send_message.call_count, 1)


if __name__ == "__main__":
    unittest.main()
