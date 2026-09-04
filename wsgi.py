"""WSGI entrypoint for production servers (gunicorn / PythonAnywhere).

Local dev:      python app.py
Gunicorn:       gunicorn wsgi:app
PythonAnywhere: point the web app's WSGI file at `from wsgi import app`
"""
from app import create_app

app = create_app()
