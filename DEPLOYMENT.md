# Project and deployment

## How the app works

This is a Python 3.12 FastAPI application. `app/main.py` serves the browser UI and JSON endpoints under `/api`; `app/routers` owns the API routes, and `app/services` handles translation, glossary lookup, chunking, and PDF export. The browser assets live in `app/static`. Gemini is the preferred generated-translation provider; the curated glossary dictionary mode works without a key.

Run locally with `python run.py` after installing `requirements.txt`. Copy `.env.example` to `.env` and set `GEMINI_API_KEY` from [Google AI Studio](https://aistudio.google.com/apikey) to enable free-tier generated translation and multimodal features. The key stays on the server; without it, text remains available in dictionary mode. Google imposes rate limits, and its free-tier terms state submitted content may be used to improve products. Do not submit confidential, privileged, or sensitive legal documents through the free tier. Run tests with `python -m pytest`.

The translator accepts pasted text and `.pdf`, `.docx`, `.txt`, `.md`, or `.csv` files; it also accepts MP3, WAV, M4A, AAC, OGG, FLAC, OPUS, and WebM audio. Public article pages and direct PDF/audio URLs can be submitted in the link field. Uploads and downloads are limited to 14 MB. Audio and scanned PDFs require `GEMINI_API_KEY`; searchable PDFs, DOCX, and text can be extracted locally. Link ingestion only accepts public HTTP/HTTPS URLs and blocks local/private network addresses.

## GitHub

Git is not included in this workspace environment. After installing Git and creating an empty GitHub repository, run these commands from the project directory:

```powershell
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<owner>/<repository>.git
git push -u origin main
```

`.env` is ignored by Git. Keep `GEMINI_API_KEY` and `XAI_API_KEY` out of source control; configure them as host secrets.

## Netlify and API hosting

Netlify hosts the static frontend; it does not run this FastAPI application. A separate FastAPI service is required for full-model translation, file/audio uploads, and links. Deploy the Dockerfile to a Python/container host and set `GEMINI_API_KEY` in that service's secret settings. Without an API service the static site supports only its local glossary dictionary mode.

Then connect the GitHub repository in Netlify. The included `netlify.toml` sets the build command and publish directory. No environment variables are needed for the static dictionary mode. To use a separately deployed FastAPI service, optionally set:

| Variable | Value |
| --- | --- |
| `API_BASE_URL` | The public origin of the deployed FastAPI service, for example `https://pidgin-law-api.example.com` |

Netlify generates `dist/config.js` from that value and uses the API for translation, glossary, samples, and exports. The API origin should not include `/api`; the frontend adds endpoint paths itself. The FastAPI service currently permits cross-origin browser requests, so the Netlify site can call it directly.