#!/usr/bin/env bash
# setup-gcp.sh — one-shot GCP setup for Critter.
# Idempotent: safe to re-run. Only creates resources that don't yet exist;
# treats Secret Manager as the source of truth for generated passwords.
#
# Creates:
#   • Cloud SQL Postgres instance (critter-sql) + db (critter) + user (critter_app)
#   • Service account (critter-backend) with required IAM roles
#   • SA JSON key written to backend/.critter-sa-key.json
#   • GCS buckets (critter-clean, critter-unscanned, critter-quarantine)
#   • All secrets in Secret Manager (matching backend/deploy.sh)
#   • backend/.env populated with the right values (only if .env doesn't exist)
#
# Prereqs:
#   - gcloud CLI installed and authenticated (`gcloud auth login`)
#   - GCP project wtroy-test-proj exists with billing enabled
#   - openssl, python3 available locally
#
# Usage:
#   ./setup-gcp.sh

set -euo pipefail

# =============================================================================
# Config
# =============================================================================
PROJECT_ID="wtroy-test-proj"
REGION="us-central1"
INSTANCE_NAME="critter-sql"
DB_NAME="critter"
DB_USER="critter_app"
SA_NAME="critter-backend"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

BUCKET_CLEAN="critter-clean"
BUCKET_UNSCANNED="critter-unscanned"
BUCKET_QUARANTINE="critter-quarantine"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SA_KEY_PATH="${SCRIPT_DIR}/backend/.critter-sa-key.json"
ENV_FILE="${SCRIPT_DIR}/backend/.env"

# =============================================================================
# Pretty output
# =============================================================================
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log()     { echo -e "${BLUE}▶${NC} $1"; }
ok()      { echo -e "${GREEN}✓${NC} $1"; }
warn()    { echo -e "${YELLOW}!${NC} $1"; }
err()     { echo -e "${RED}✗${NC} $1" >&2; }
section() { echo; echo -e "${YELLOW}════ $1 ════${NC}"; }

# =============================================================================
# Helpers
# =============================================================================
secret_exists() {
  gcloud secrets describe "$1" --project="$PROJECT_ID" >/dev/null 2>&1
}

secret_value() {
  gcloud secrets versions access latest --secret="$1" --project="$PROJECT_ID" 2>/dev/null
}

put_secret() {
  # Idempotent: creates the secret on first call, adds a new version after.
  local name="$1"
  local value="$2"
  if secret_exists "$name"; then
    printf "%s" "$value" | gcloud secrets versions add "$name" --data-file=- --project="$PROJECT_ID" >/dev/null
    ok "Updated secret: $name"
  else
    printf "%s" "$value" | gcloud secrets create "$name" --data-file=- --project="$PROJECT_ID" >/dev/null
    ok "Created secret: $name"
  fi
}

ensure_placeholder() {
  # Only create if missing — never overwrite a key the user has already filled in.
  local name="$1"
  if secret_exists "$name"; then
    ok "Secret already set: $name (leaving as-is)"
  else
    printf "REPLACE_ME" | gcloud secrets create "$name" --data-file=- --project="$PROJECT_ID" >/dev/null
    warn "Created placeholder: $name (set the real value before deploy.sh)"
  fi
}

retry() {
  # Retry a command up to 10 times with exponential backoff (2s, 4s, 8s, …, capped at 30s).
  # Used for IAM operations, which are eventually consistent — a freshly-created
  # service account often isn't visible to add-iam-policy-binding for a few seconds.
  local max=10
  local delay=2
  local i=0
  until "$@"; do
    i=$((i+1))
    if [ $i -ge $max ]; then
      err "Command failed after $max attempts: $*"
      return 1
    fi
    warn "Attempt $i failed (likely IAM propagation), retrying in ${delay}s…"
    sleep $delay
    delay=$((delay * 2))
    [ $delay -gt 30 ] && delay=30
  done
}

# =============================================================================
# 0. Sanity checks
# =============================================================================
section "Sanity checks"

if ! command -v gcloud >/dev/null 2>&1; then
  err "gcloud not found. Install: https://cloud.google.com/sdk/docs/install"
  exit 1
fi

ACCOUNT="$(gcloud config get-value account 2>/dev/null || true)"
if [ -z "$ACCOUNT" ]; then
  err "Not logged in. Run: gcloud auth login"
  exit 1
fi
ok "Logged in as: $ACCOUNT"

if ! gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1; then
  err "Project '$PROJECT_ID' not found or you don't have access."
  exit 1
fi
ok "Project $PROJECT_ID accessible"

gcloud config set project "$PROJECT_ID" >/dev/null
gcloud config set compute/region "$REGION" >/dev/null

# =============================================================================
# 1. Enable APIs
# =============================================================================
section "Enabling APIs"

gcloud services enable \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  storage.googleapis.com \
  iam.googleapis.com \
  --project="$PROJECT_ID"

ok "APIs enabled"

# =============================================================================
# 2. Cloud SQL instance (~5–10 min on first run)
# =============================================================================
section "Cloud SQL instance"

if gcloud sql instances describe "$INSTANCE_NAME" --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "Instance '$INSTANCE_NAME' already exists"
else
  log "Creating Cloud SQL instance — this takes 5–10 minutes…"
  ROOT_PW="$(openssl rand -base64 24)"
  gcloud sql instances create "$INSTANCE_NAME" \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region="$REGION" \
    --storage-type=SSD \
    --storage-size=10GB \
    --storage-auto-increase \
    --backup-start-time=07:00 \
    --availability-type=zonal \
    --root-password="$ROOT_PW" \
    --project="$PROJECT_ID"
  ok "Cloud SQL instance created"
fi

CONNECTION_NAME="$(gcloud sql instances describe "$INSTANCE_NAME" --project="$PROJECT_ID" --format='value(connectionName)')"
ok "Connection name: $CONNECTION_NAME"

# =============================================================================
# 3. Database
# =============================================================================
section "Database"

if gcloud sql databases describe "$DB_NAME" --instance="$INSTANCE_NAME" --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "Database '$DB_NAME' already exists"
else
  gcloud sql databases create "$DB_NAME" --instance="$INSTANCE_NAME" --project="$PROJECT_ID"
  ok "Database '$DB_NAME' created"
fi

# =============================================================================
# 4. App user — Secret Manager is the source of truth for the password
# =============================================================================
section "App user"

USER_EXISTS="false"
if gcloud sql users list --instance="$INSTANCE_NAME" --project="$PROJECT_ID" --format='value(name)' | grep -q "^${DB_USER}$"; then
  USER_EXISTS="true"
fi

if [ "$USER_EXISTS" = "true" ] && secret_exists "critter-sql-password"; then
  APP_PW="$(secret_value critter-sql-password)"
  ok "App user '$DB_USER' exists, password loaded from Secret Manager"
elif [ "$USER_EXISTS" = "true" ]; then
  # User exists but no password in SM (probably a half-finished previous run) — rotate.
  warn "User '$DB_USER' exists but no password in Secret Manager — rotating"
  APP_PW="$(openssl rand -base64 24)"
  gcloud sql users set-password "$DB_USER" --instance="$INSTANCE_NAME" --password="$APP_PW" --project="$PROJECT_ID"
  ok "Password rotated for $DB_USER"
else
  log "Creating app user '$DB_USER'"
  APP_PW="$(openssl rand -base64 24)"
  gcloud sql users create "$DB_USER" --instance="$INSTANCE_NAME" --password="$APP_PW" --project="$PROJECT_ID"
  ok "App user created"
fi

# =============================================================================
# 5. Service account + IAM
# =============================================================================
section "Service account + IAM"

if gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "SA '$SA_EMAIL' already exists"
else
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="Critter backend service account" \
    --project="$PROJECT_ID"
  ok "SA created"
fi

log "Granting IAM roles (with retry for IAM propagation)…"
for role in \
  roles/cloudsql.client \
  roles/storage.objectAdmin \
  roles/secretmanager.secretAccessor \
  roles/aiplatform.user; do
  retry gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$role" \
    --condition=None \
    --quiet >/dev/null
done
ok "IAM roles granted"

# =============================================================================
# 6. Service account key (for cloud-sql-proxy + Django GCS auth locally)
# =============================================================================
section "Service account key"

if [ -f "$SA_KEY_PATH" ]; then
  ok "SA key already exists at $SA_KEY_PATH"
  warn "To rotate: delete the file (and ideally the corresponding key in IAM) and re-run"
else
  mkdir -p "$(dirname "$SA_KEY_PATH")"
  gcloud iam service-accounts keys create "$SA_KEY_PATH" \
    --iam-account="$SA_EMAIL" \
    --project="$PROJECT_ID"
  chmod 600 "$SA_KEY_PATH"
  ok "SA key written to $SA_KEY_PATH"
fi

# =============================================================================
# 7. GCS buckets
# =============================================================================
section "GCS buckets"

for BUCKET in "$BUCKET_CLEAN" "$BUCKET_UNSCANNED" "$BUCKET_QUARANTINE"; do
  if gcloud storage buckets describe "gs://$BUCKET" --project="$PROJECT_ID" >/dev/null 2>&1; then
    ok "Bucket gs://$BUCKET already exists"
  else
    gcloud storage buckets create "gs://$BUCKET" \
      --location="$REGION" \
      --project="$PROJECT_ID"
    ok "Created gs://$BUCKET"
  fi
done

# =============================================================================
# 8. Django SECRET_KEY — also stored in SM as source of truth
# =============================================================================
section "Django SECRET_KEY"

if secret_exists "critter-django-secret"; then
  DJANGO_SECRET="$(secret_value critter-django-secret)"
  ok "Loaded SECRET_KEY from Secret Manager"
else
  DJANGO_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
  ok "Generated new SECRET_KEY"
fi

# =============================================================================
# 9. Secret Manager — write everything
# =============================================================================
section "Secret Manager"

put_secret critter-sql-user "$DB_USER"
put_secret critter-sql-password "$APP_PW"
put_secret critter-sql-db-name "$DB_NAME"
put_secret critter-sql-connection-name "$CONNECTION_NAME"
put_secret critter-django-secret "$DJANGO_SECRET"
put_secret critter-bucket-clean "$BUCKET_CLEAN"
put_secret critter-bucket-unscanned "$BUCKET_UNSCANNED"
put_secret critter-bucket-quarantine "$BUCKET_QUARANTINE"

# Service account JSON key as a secret (Cloud Run loads it as an env var)
if secret_exists "critter-service-account-key"; then
  gcloud secrets versions add critter-service-account-key \
    --data-file="$SA_KEY_PATH" --project="$PROJECT_ID" >/dev/null
  ok "Updated secret: critter-service-account-key"
else
  gcloud secrets create critter-service-account-key \
    --data-file="$SA_KEY_PATH" --project="$PROJECT_ID" >/dev/null
  ok "Created secret: critter-service-account-key"
fi

# Placeholders — never overwrite values you've already filled in.
# (No critter-gemini-key — Gemini Vision goes through Vertex AI with the SA.)
ensure_placeholder critter-anthropic-key
ensure_placeholder critter-runway-key
ensure_placeholder critter-elevenlabs-key
ensure_placeholder critter-kling-access-key
ensure_placeholder critter-kling-secret-key
ensure_placeholder critter-stripe-secret
ensure_placeholder critter-stripe-webhook-secret
ensure_placeholder critter-redis-host
ensure_placeholder critter-redis-port

# =============================================================================
# 10. backend/.env (only if missing — never clobber custom edits)
# =============================================================================
section "backend/.env"

if [ -f "$ENV_FILE" ]; then
  warn "$ENV_FILE already exists — not overwriting"
  echo
  echo "  Make sure these match what's in your .env (or just delete .env and re-run):"
  echo "    SECRET_KEY=$DJANGO_SECRET"
  echo "    GCP_SQL_PROD_PASSWORD=$APP_PW"
  echo "    GCP_SQL_CONNECTION_NAME=$CONNECTION_NAME"
  echo "    GOOGLE_SA_KEYFILE=$SA_KEY_PATH"
else
  cat > "$ENV_FILE" <<EOF
# Auto-generated by setup-gcp.sh on $(date)
# Edit AI provider keys when you have them. Re-run setup-gcp.sh anytime.

SECRET_KEY=$DJANGO_SECRET
PROD_DEPLOY=False
SITE_URL=http://localhost:5173
REACT_BASE_URL=http://localhost:5173

# Skip 2FA at login (no email sender configured locally)
REQUIRE_2FA=False

# Run jobs in a daemon thread on the Django process (no RQ worker needed).
# Flip to False once you wire up Memorystore Redis + a real worker.
RUN_JOBS_INLINE=True

# Database (via cloud-sql-proxy on localhost:5433)
GCP_SQL_DB_NAME=$DB_NAME
GCP_SQL_PROD_USER=$DB_USER
GCP_SQL_PROD_PASSWORD=$APP_PW
GCP_SQL_PUBLIC_IP_ADDRESS=127.0.0.1
GCP_SQL_PORT=5433
GCP_SQL_CONNECTION_NAME=$CONNECTION_NAME

# Local Redis (brew services start redis)
REDIS_HOST=localhost
REDIS_PORT=6379

# Google Cloud
GOOGLE_CLOUD_PROJECT_ID=$PROJECT_ID
GOOGLE_CLOUD_REGION=$REGION
GOOGLE_CLOUD_GEMINI_LOCATION=$REGION
GOOGLE_SA_KEYFILE=$SA_KEY_PATH
GS_BUCKET_NAME=$BUCKET_CLEAN
GS_UNSCANNED_BUCKET_NAME=$BUCKET_UNSCANNED
GS_QUARANTINE_BUCKET_NAME=$BUCKET_QUARANTINE

# AI provider keys — fill these in (Veo + Gemini Vision use the SA, no key)
ANTHROPIC_API_KEY=
RUNWAY_API_KEY=
ELEVENLABS_API_KEY=
KLING_ACCESS_KEY=
KLING_SECRET_KEY=
RUNWAY_API_KEY=
ELEVENLABS_API_KEY=

# Email — falls back to console backend in dev when EMAIL_HOST_PASSWORD is empty
EMAIL_HOST_USER=no-reply@critter.app
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=Critter <no-reply@critter.app>

# Stripe (Phase 5)
STRIPE_PUBLISHABLE_KEY=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

# ClamAV (off in dev)
CLAMAV_SCANNER_URL=
ENABLE_CLAMAV_SCANNING=false
EOF
  chmod 600 "$ENV_FILE"
  ok "Wrote $ENV_FILE"
fi

# =============================================================================
# 11. cloud-sql-proxy binary check
# =============================================================================
section "cloud-sql-proxy binary"

PROXY_CANDIDATES=(
  "${SCRIPT_DIR}/../cloud-sql-proxy"
  "${SCRIPT_DIR}/cloud-sql-proxy"
  "$HOME/Code/mine/cloud-sql-proxy"
)

PROXY_FOUND=""
for p in "${PROXY_CANDIDATES[@]}"; do
  if [ -x "$p" ]; then
    PROXY_FOUND="$p"
    break
  fi
done

if [ -n "$PROXY_FOUND" ]; then
  ok "Found cloud-sql-proxy at: $PROXY_FOUND"
else
  warn "cloud-sql-proxy binary not found in any of: ${PROXY_CANDIDATES[*]}"
  echo "    Install on macOS arm64:"
  echo "      curl -o ~/Code/mine/cloud-sql-proxy \\"
  echo "        https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.13.0/cloud-sql-proxy.darwin.arm64"
  echo "      chmod +x ~/Code/mine/cloud-sql-proxy"
fi

# =============================================================================
# Summary
# =============================================================================
section "Done"
cat <<EOF

${GREEN}✓ GCP setup complete for project $PROJECT_ID${NC}

Three terminals to run the app locally — same pattern as RateRail:

  ${YELLOW}Terminal 1 — Cloud SQL proxy${NC}
    cd ~/Code/mine
    ./cloud-sql-proxy \\
      --credentials-file=./april_ideas/backend/.critter-sa-key.json \\
      $CONNECTION_NAME --port=5433

  ${YELLOW}Terminal 2 — Django${NC}
    conda activate <your-env>
    cd ~/Code/mine/april_ideas/backend
    pip install -r requirements.txt   # first time only
    python manage.py migrate
    python manage.py createsuperuser  # first time only
    python manage.py runserver

  ${YELLOW}Terminal 3 — Frontend${NC}
    cd ~/Code/mine/april_ideas/frontend
    npm install                       # first time only
    npm run dev

  ${YELLOW}Terminal 4 (optional) — RQ worker for video generation${NC}
    brew services start redis         # if not running
    conda activate <your-env>
    cd ~/Code/mine/april_ideas/backend
    python manage.py rqworker high default low

  ${YELLOW}Terminal 5 (optional) — ngrok${NC}
    ngrok http 8000

${YELLOW}Still to do (when you're ready):${NC}
  • Fill ANTHROPIC_API_KEY (and optionally RUNWAY_API_KEY) in backend/.env
  • Mirror those into Secret Manager before running ./backend/deploy.sh:
      gcloud secrets versions add critter-anthropic-key --data-file=- <<< 'YOUR_KEY'
      gcloud secrets versions add critter-runway-key --data-file=- <<< 'YOUR_KEY'
  • For prod video generation: provision Memorystore Redis + a 'critter-redis-connector'
    Serverless VPC connector, then update critter-redis-host secret.

EOF
