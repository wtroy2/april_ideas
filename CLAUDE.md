# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project overview

**Critter** — AI-powered video generation for pet (and person) content creators on Instagram / TikTok. Creators upload photos of their pet → save as a reusable **Subject** → pick a **Theme** template → generate batches of consistent short-form videos.

This repo deliberately mirrors the patterns in the sibling RateRail project at `~/Code/mine/local_django_react/django_loan`. When in doubt, do what RateRail does.

- **Stack**: Django 5.1 + DRF backend, React 18 + Vite frontend (no TypeScript), PostgreSQL, Redis, GCS
- **Deploy target**: Google Cloud Run (backend + worker), Firebase Hosting (frontend)
- **GCP project**: `wtroy-test-proj`
- **Multi-tenant**: organization model from day one

---

## Code style & preferences (lifted from RateRail)

- **Always provide complete files or complete functions** — never partial snippets, no "rest remains the same"
- **Brand colors are blues only — NEVER use purples**:
  - Dark: `#1e3a8a` · Primary: `#2563eb` · Light: `#3b82f6` · Accent: `#1e40af` · Background light: `#dbeafe` · Background lighter: `#eff6ff`
- **UI philosophy**: Build interfaces that are a joy to use — clean, responsive, intuitive
- **Django patterns**: `@api_view` function-based views (NOT ViewSets), DRF serializers for validation, `IsAuthenticated` by default
- **React patterns**: Functional components with hooks, React Context for state, centralized axios client (`src/api.js`), toast notifications for user feedback
- **No TypeScript** — frontend is pure JavaScript (JSX)
- **Error handling**: try/catch in async functions, meaningful error messages

---

## Development commands

### Backend (from `backend/`)

```bash
# Install
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run migrations
python manage.py makemigrations && python manage.py migrate

# Run dev server
python manage.py runserver

# Run RQ worker (separate terminal — needs Redis)
python manage.py rqworker high default low

# Tests
python manage.py test
python manage.py test <app_name>

# Cloud SQL proxy (for hitting prod DB locally — optional)
./cloud-sql-proxy --credentials-file=./.gcp-key.json wtroy-test-proj:us-central1:critter-sql --port=5433
```

### Frontend (from `frontend/`)

```bash
npm install
npm run dev      # Vite dev server at http://localhost:5173
npm run build    # Production build to dist/
npm run lint     # ESLint
```

### Redis

```bash
brew services start redis
redis-cli ping   # → PONG
```

### Production deployment

```bash
# Backend
cd backend && ./deploy.sh

# Worker
cd backend && ./deploy_worker.sh

# Frontend
cd frontend && VITE_API_URL=https://api.critter.app npm run build
firebase deploy --project wtroy-test-proj
```

---

## Architecture

### Backend: Django 5.1 + DRF

- **Settings**: `backend/backend/settings.py` — env-driven via `.env`, `PROD_DEPLOY=True` switches between Cloud SQL proxy (local) and unix socket (prod)
- **Auth**: JWT via `djangorestframework-simplejwt` with token blacklisting (2-hour access, 1-day refresh), email 2FA (`users.middleware.TwoFactorSecurityMiddleware`), single-device sessions (`users.middleware.SingleDeviceSessionMiddleware`)
- **Background jobs**: `django-rq` with Redis (queues: high, default, low). Video generation runs on `low` (timeout 30min). Worker runs as separate Cloud Run service via `Dockerfile.worker`
- **Storage**: `django-storages` with GCS. User-uploaded photos go through unscanned → quarantine → ClamAV scan → clean bucket pipeline (same as RateRail). Generated videos go directly to clean bucket since we produced them
- **AI providers**: Veo 3 via Vertex AI (primary video), Runway Gen-4 (character consistency), Gemini 2.5 Flash Image (reference processing), Claude Sonnet 4.6 (scripts/captions). Provider abstraction in `providers/` so models can swap

### Django apps

| App | Purpose |
|-----|---------|
| `users` | CustomUser, JWT, 2FA, password reset, sessions, single-device middleware |
| `orgs` | Multi-tenant orgs, members (admin/editor/viewer roles), invitations |
| `core` | Shared utilities (UUID URL converter, base mixins) |
| `analytics` | Request analytics middleware |
| `billing` | Stripe subscriptions (Phase 5) |
| `subjects` | Pet/Person profiles. Photos, descriptions, reference set. Auto-described via Gemini vision |
| `themes` | Reusable templates (style, music vibe, shot structure, caption template). 5+ seeded for pets |
| `assets` | Uploaded images + generated videos. Wraps GCS pipeline |
| `providers` | Adapters for Veo, Runway, Gemini, ElevenLabs, Anthropic. Single `generate_video(subject, theme, prompt)` interface |
| `generations` | Generation jobs (status, outputs, regenerations). RQ pipeline runs on `low` queue |
| `trends` | Pet-niche trend scraper (sounds, hashtags, formats) — Phase 5 |
| `scheduling` | Optional IG/TikTok auto-post via Buffer/Ayrshare — Phase 4 |

### URL structure

All API endpoints prefixed with `/api/{app}/`. JWT tokens at `/api/users/token/` and `/api/users/token/refresh/`.

### Middleware stack (order matters)

CORS → Security → WhiteNoise → Session → Common → CSRF → Auth → SingleDeviceSession → 2FA → AuthErrorHandling → Messages → Clickjacking → Analytics

### Frontend: React 18 + Vite

- **Entry**: `frontend/src/main.jsx` → `App.jsx`
- **API client**: `frontend/src/api.js` — Axios with JWT interceptors and auto-refresh, base URL from `VITE_API_URL`
- **Token mgmt**: `frontend/src/utils/TokenManager.jsx` — singleton, handles refresh debouncing
- **Auth state**: `frontend/src/context/AuthContext.jsx` — exposes `isAuthenticated`, `username`, `organizationStatus`, role helpers
- **Routing**: React Router v6, nested under `MainLayout` with `<ProtectedRoute>` wrappers
- **UI**: Bootstrap 5 + Lucide React icons + React Toastify + react-spinners
- **No state library** — React Context only

---

## Key patterns

- **Environment config**: All secrets/config via env vars loaded from `backend/.env` with `python-dotenv`. `PROD_DEPLOY=True` switches to production mode.
- **Database**: PostgreSQL only (Cloud SQL in prod). Local dev: either Cloud SQL proxy on port 5433 OR a local Postgres. No SQLite.
- **Custom user model**: `users.CustomUser` extends `AbstractUser`, email is unique.
- **Multi-tenant**: Every domain model FK to `Organization`. Org membership is one-per-user (`OneToOneField` from `OrganizationMember.user`). Roles: admin / editor / viewer.
- **Single-device sessions**: `UserSession` model + `SingleDeviceSessionMiddleware` enforces it. JWT `jti` claim is the session key.
- **2FA**: `TwoFactorCode` model handles login codes (6 digits, 10-min expiry), password reset (8 chars, 30-min expiry), and username recovery. Codes hashed (SHA256) at rest.
- **Static files**: WhiteNoise in prod, `collectstatic` runs in Docker CMD.
- **WSGI**: Gunicorn (2 workers, 4 threads).
- **Logging**: Structured logging to files — `auth.log`, `critter.log`, `security.log`.
- **Provider abstraction**: All external AI providers (Veo, Runway, Anthropic, Gemini, ElevenLabs) live behind adapters in `providers/`. Generation pipeline calls the abstract interface. To swap models, add a new adapter and update routing.

---

## GCP infrastructure

### Cloud Storage buckets (created on first deploy)
- `critter-clean` — finished assets (clean photos, generated videos)
- `critter-unscanned` — fresh uploads awaiting scan
- `critter-quarantine` — files flagged by ClamAV

### Cloud Run services
- **Backend**: `critter-backend` (2 CPU, 2Gi, 0-10 instances)
- **Worker**: `critter-worker` — RQ worker with health endpoint on port 8080

### Key GCP settings
- **Project**: `wtroy-test-proj`
- **Region**: `us-central1`
- **Cloud SQL**: `wtroy-test-proj:us-central1:critter-sql`
- **Redis (Memorystore)**: configured via VPC connector
- **Vertex AI Veo**: `us-central1` location

---

## Security

- JWT tokens: 2-hour access, 1-day refresh, blacklist on logout
- 2FA: 6-digit email codes, 10-min expiry
- Password reset: 8-char codes, 30-min expiry
- File uploads: quarantine pipeline, signed URLs (1-hour expiry), max 50MB
- Rate limiting via `django-ratelimit` on auth endpoints
- CORS: permissive in dev, specific origins in prod

---

## Vendor integrations

- **Vertex AI (Veo 3)**: Primary video gen — uses existing Gemini API keys via Google Cloud SDK
- **Runway**: Character-consistent video gen via References API (Phase 3 fallback)
- **Anthropic Claude**: Script and caption generation
- **Gemini 2.5 Flash Image**: Pet photo processing (description + reference set curation)
- **ElevenLabs**: Voiceover (when needed)
- **Stripe**: Subscriptions (Phase 5)

---

## Known limitations / next up

- **Tests**: minimal automated tests (mirrors RateRail) — add pytest-django when stable
- **No TypeScript**: frontend is pure JS by design (matches RateRail)
- **Trend scraper**: not yet implemented — Phase 5
- **Stripe paywall**: not yet wired — Phase 5
- **IG/TikTok auto-post**: not yet wired — Phase 4
