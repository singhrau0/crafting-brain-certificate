"""Copy into PythonAnywhere's WSGI configuration file."""
import os
from pathlib import Path
import sys

project = Path.home() / 'crafting-brain-certificate'
sys.path.insert(0, str(project))
os.environ['HTTPS_ONLY'] = '1'
os.environ.setdefault('DATABASE_PATH', str(project / 'instance/certificates.sqlite3'))
from dotenv import load_dotenv
load_dotenv(project / '.env')
if not os.getenv('SECRET_KEY'):
    raise RuntimeError('Set a random SECRET_KEY in the project .env before deployment.')
from app import app as application
