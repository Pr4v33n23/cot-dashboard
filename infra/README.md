# Deployment

> **Capital stop reminder** (PLAN §0.3): $0 spent on hosting until first paying user commits. The configs in this folder are pre-built so deploy can happen instantly when that condition is met — but they're not active.

## Layout

| File | Target | What it does |
|---|---|---|
| [apps/api/Dockerfile](../apps/api/Dockerfile) | Fly.io | Builds the FastAPI image with the entire `packages/ingest/` + bundled cache |
| [infra/fly/fly.toml](fly/fly.toml) | Fly.io | App config — shared-1x, auto-stop on idle, healthcheck on /healthz |
| [apps/web/vercel.json](../apps/web/vercel.json) | Vercel | SvelteKit static build; `/api/*` rewrites to the Fly origin |
| [.github/workflows/ci.yml](../.github/workflows/ci.yml) | GitHub Actions | Lint + import smoke (Python) + `npm run check` + build (web) on every push |
| [.github/workflows/friday-cftc-ingest.yml](../.github/workflows/friday-cftc-ingest.yml) | GitHub Actions | Weekly cron: pull fresh CFTC ZIP + prices, optionally sync to R2 + POST /refresh |
| [.github/workflows/daily-news-ingest.yml](../.github/workflows/daily-news-ingest.yml) | GitHub Actions | Daily cron: pull yfinance news, POST /refresh |

## First-time deploy (Fly + Vercel)

```bash
# 1. API on Fly.io
brew install flyctl
fly auth login
cd /path/to/cot-dashboard
fly launch --copy-config infra/fly/fly.toml --no-deploy
fly deploy --dockerfile apps/api/Dockerfile
fly status

# 2. Web on Vercel
npm i -g vercel
cd apps/web
vercel link
vercel --prod
```

## Optional secrets

Set these in GitHub repo → Settings → Secrets & variables → Actions if you
want the cron jobs to push cache to R2 + trigger /refresh on the live API:

| Secret | Purpose |
|---|---|
| `REFRESH_URL` | Base URL of the deployed API (e.g. `https://cot-lens-api.fly.dev`) |
| `AWS_ACCESS_KEY_ID` | R2 access key |
| `AWS_SECRET_ACCESS_KEY` | R2 secret key |
| `AWS_ENDPOINT_URL` | R2 endpoint (e.g. `https://<account>.r2.cloudflarestorage.com`) |
| `R2_BUCKET` | R2 bucket name |

Without these, the cron jobs still run and produce a fresh cache committed to
the runner — useful for verifying the pipeline works before going paid.
