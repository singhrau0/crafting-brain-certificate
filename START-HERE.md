# PythonAnywhere deployment

This package contains the current single-user app.
Login: demo@craftingbrain.com / Demo@1234.

1. Upload and extract the ZIP in your home directory.
2. Create a virtualenv inside crafting-brain-certificate/.venv using the same Python version selected for the web app, then install requirements.txt.
3. Create .env in the project folder with SMTP_EMAIL, SMTP_APP_PASSWORD, SMTP_HOST=smtp.gmail.com and SMTP_PORT=587. Add a random SECRET_KEY. Keep this file private (chmod 600 .env).
4. In Web, add a free web app with Manual configuration and the matching Python version. Set its virtualenv to /home/YOUR_USERNAME/crafting-brain-certificate/.venv.
5. Replace the Web tab WSGI file contents with pythonanywhere_wsgi.py.
6. Enable Force HTTPS and reload the web app.
7. Test login, preview, download and email to an address you control. Verify SMTP delivery on the hosting account.

The ZIP excludes .env, local history, samples and test artifacts.
The signature is included only in static/IMG_8836.jpg.
SQLite records live in the project instance directory. Back them up.
Free hosting has 512 MiB storage and monthly web-app renewal.
