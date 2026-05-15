# Buxin-Academy

Flask API backend for **Buxin Academy** — robotics education platform.

## Stack

- Python / Flask
- Neon PostgreSQL
- Cloudinary (image uploads)
- JWT authentication
- Flask-SocketIO

## Setup

```bash
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env  # Add your secrets
python app.py
```

Health check: `GET /api/health`

## Deploy (Render)

Use `render.yaml` or set root directory to this repo and start command:

```
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT app:app
```

See `.env.example` for required environment variables.
