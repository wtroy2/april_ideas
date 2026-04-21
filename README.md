# Critter

AI video generation for pet (and person) content creators. Upload a few photos of your pet, save it as a reusable Subject, pick a Theme template, and generate batches of consistent short-form videos for Instagram / TikTok.

## Stack

- **Backend**: Django 5.1 + DRF + django-rq + PostgreSQL + Redis
- **Frontend**: React 18 + Vite + Bootstrap (no TypeScript)
- **Storage**: Google Cloud Storage (with quarantine pipeline)
- **Auth**: JWT (simplejwt) + email 2FA + single-device sessions
- **Multi-tenant**: Organization model from day one
- **Video gen**: Veo 3 (Vertex AI) + Runway Gen-4 (References)
- **LLM**: Claude Sonnet 4.6 (scripts/captions) + Gemini 2.5 Flash Image (reference processing)
- **Deploy**: Cloud Run (backend + worker) + Firebase Hosting (frontend)
- **GCP project**: `wtroy-test-proj`

Mirrors the patterns in `~/Code/mine/local_django_react/django_loan` (RateRail).

## Quick start

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in values
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# In another terminal — RQ worker
python manage.py rqworker high default low

# Frontend
cd frontend
npm install
cp .env.example .env  # then set VITE_API_URL if needed
npm run dev
```

See `CLAUDE.md` for full architecture, patterns, and deployment notes.
