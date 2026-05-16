# Render setup for Buxin-Academy

## Auto-deploy from GitHub (push → live)

If you have to **Manual Deploy** every time you push, fix the link between GitHub and Render:

1. In **Render** → your Web Service → **Settings** → **Build & Deploy**:
   - **Branch**: `main` (or the branch you use).
   - **Auto-Deploy**: **On Commit** (enable deploys when you push).
2. In **GitHub** → repo **Settings** → **Webhooks**:
   - There should be a Render webhook; recent deliveries should be **green**.
   - If it’s missing or failing, disconnect and reconnect the repo in Render, or reinstall the Render GitHub app for that repo.

Auto-deploy cannot be turned on from this codebase; it’s only in the Render + GitHub UI.

### If pushes never start a deploy (nothing in Render “Events”)

Work through these in order:

1. **Correct repo on the service**  
   Your **API** service must be connected to **`Buxin-Academy`** (backend), not `Buxin-Academy-Front-End`. Pushing the frontend repo will not deploy the backend.

2. **Branch name**  
   Render must watch the **same branch you push to** (e.g. `main`). If your default branch is `master` but Render is set to `main`, pushes won’t trigger.

3. **Auto-Deploy is really “On”**  
   **Settings → Build & Deploy → Auto-Deploy** = **On Commit** (not “Off”). Save if you change it.

4. **GitHub App access (very common)**  
   Render uses the **Render GitHub App**, not only a webhook:

   - GitHub → **Settings** → **Applications** → **Installed GitHub Apps** → **Render** → **Configure**.
   - Under **Repository access**, either **All repositories** or **Only select repositories** must **include** `buxinelectronics-art/Buxin-Academy` (and any others Render should see).  
   - If the repo was added to GitHub **after** you limited access, it won’t be on the list — add it and save.

5. **Reconnect the service**  
   In Render: **Settings → Build & Deploy →** disconnect Git and connect again; pick the repo and branch. That recreates permission + hooks.

6. **Confirm GitHub sees the push**  
   On GitHub, open the repo → **Commits** and confirm your commit appears on the branch Render uses.

7. **Manual deploy once**  
   After fixing the above, use **Manual Deploy** once; then push a tiny commit (e.g. README) and check **Events** for a new build.

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
| **Instance** | Free (for testing) — spins down after ~15 min idle; first request after idle can take **30–90s**. Paid instances stay up. The frontend retries API calls to handle cold starts. |

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
2. Open `https://YOUR-SERVICE.onrender.com/api/wake` — should show `{"status":"ok","db":1}` when the database is reachable.
3. Put that URL in `frontend/js/config.js` as `PROD_API_URL`.
4. Add the frontend URL to `CORS_ORIGINS` on Render and redeploy.

The **frontend** calls `/api/wake` once per browser tab on load so the API starts waking as soon as someone opens the site (GitHub Pages does not contact Render by itself).
