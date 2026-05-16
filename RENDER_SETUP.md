# Render setup for Buxin-Academy

## Service settings

| Field | Value |
|-------|--------|
| **Name** | `Buxin-Academy` (or `buxin-academy-api`) |
| **Language** | Python 3 |
| **Branch** | `main` |
| **Region** | Virginia (US East) — same as Neon |
| **Root Directory** | *(leave empty)* |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT --timeout 120 app:app` |

**If deploy shows `Running 'gunicorn app:app'`** — that is wrong. Update Start Command in Render **Settings** to the line above, then **Manual Deploy**.
| **Instance** | Free (for testing) |

### Required: Python version

Render may default to Python 3.14, which breaks the database driver.

In **Environment** add:

| Key | Value |
|-----|--------|
| `PYTHON_VERSION` | `3.10.12` |

Then **Manual Deploy** again. (`runtime.txt` and `.python-version` are also in the repo.)

## Environment variables

| Key | Value |
|-----|--------|
| `SECRET_KEY` | Long random string (not the dev default) |
| `JWT_SECRET` | Another long random string |
| `DATABASE_URL` | Your Neon URL (already set) |
| `CLOUDINARY_CLOUD_NAME` | `do7bo97gv` |
| `CLOUDINARY_API_KEY` | Your key |
| `CLOUDINARY_API_SECRET` | Your secret |
| `CLOUDINARY_URL` | Optional if the three above are set |
| `CORS_ORIGINS` | See below |
| `ADMIN_EMAIL` | `admin@buxinev.com` |
| `ADMIN_PASSWORD` | Strong password for production |
| `FLASK_DEBUG` | `0` |

**Do not set `PORT`** — Render sets it automatically. Remove `PORT` if you added it.

### CORS_ORIGINS

Until the frontend is deployed, use:

```
http://localhost:5500,http://127.0.0.1:5500
```

After Vercel/GitHub Pages deploy, add your live URL:

```
http://localhost:5500,https://your-frontend.vercel.app
```

## After deploy

1. Open `https://YOUR-SERVICE.onrender.com/api/health` — should show `{"status":"ok"}`.
2. Put that URL in `frontend/js/config.js` as `PROD_API_URL`.
3. Add the frontend URL to `CORS_ORIGINS` on Render and redeploy.
