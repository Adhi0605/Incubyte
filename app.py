"""Native Vercel FastAPI entrypoint; hosted storage must be PostgreSQL."""
import os
from urllib.parse import urlsplit

database_url = os.environ.get('DATABASE_URL', '')
try:
    parsed_url = urlsplit(database_url)
    valid_database = (database_url.startswith(('postgres://', 'postgresql://'))
                      and parsed_url.hostname and parsed_url.path not in ('', '/'))
except ValueError:
    valid_database = False
if not valid_database:
    raise ValueError('DATABASE_URL must specify PostgreSQL for Vercel hosting')

from backend.app.main import production_app

app = production_app()
