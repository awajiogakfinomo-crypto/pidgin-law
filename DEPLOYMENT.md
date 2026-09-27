# Project and deployment

## How the app works

This is a Python 3.12 FastAPI application. `app/main.py` serves the browser UI and JSON endpoints under `/api`; `app/routers` owns the API routes, and `app/services` handles translation, source ingestion, glossary lookup, chunking, and PDF export. The browser assets live in `app/static`. Groq is the generated-translation provider; the curated glossary dictionary mode works without a key.

Run locally with `python run.py` after installing `requirements.txt`. Copy `.env.example` to `.env` and set `GROQ_API_KEY` from [Groq Console](https://console.groq.com/keys) to enable generated translation and audio transcription. The key stays on the server; without it, text remains available in dictionary mode. Groq rate limits and service terms apply. Do not submit confidential, privileged, or sensitive legal documents unless your provider policy permits it. Run tests with `python -m pytest`.

The translator accepts pasted text and `.pdf`, `.docx`, `.txt`, `.md`, or `.csv` files; it also accepts MP3, WAV, M4A, AAC, OGG, FLAC, OPUS, and WebM audio. Public article pages and direct PDF/audio URLs can be submitted in the link field. Uploads and downloads are limited to 14 MB. Audio requires `GROQ_API_KEY`; searchable PDFs, DOCX, and text can be extracted locally. Scanned PDFs are not supported because OCR is not enabled. Link ingestion only accepts public HTTP/HTTPS URLs and blocks local/private network addresses.

## GitHub

After cloning the repository, run these commands from the project directory:

```powershell
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/awajiogakfinomo-crypto/pidgin-law.git
git push -u origin main
```

`.env` is ignored by Git. Keep `GROQ_API_KEY` out of source control; configure it as a host secret.

## Netlify and API hosting

Netlify hosts the static frontend; it does not run this FastAPI application. A separate FastAPI service is required for full-model translation, file/audio uploads, and links. Deploy the Dockerfile to a Python/container host and set `GROQ_API_KEY` in that service's secret settings. Without an API service the static site supports only its local glossary dictionary mode.

Then connect the GitHub repository in Netlify. The included `netlify.toml` sets the build command and publish directory. No environment variables are needed for the static dictionary mode. To use a separately deployed FastAPI service, optionally set:

| Variable | Value |
| --- | --- |
| `API_BASE_URL` | The public origin of the deployed FastAPI service, for example `https://pidgin-law-api.example.com` |

Netlify generates `dist/config.js` from that value and uses the API for translation, glossary, samples, and exports. The API origin should not include `/api`; the frontend adds endpoint paths itself. The FastAPI service currently permits cross-origin browser requests, so the Netlify site can call it directly.