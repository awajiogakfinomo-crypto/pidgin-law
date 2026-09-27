# Pidgin Law

Pidgin Law helps people understand Nigerian legal English by translating contracts, notices, court documents, and other legal text into clear Nigerian Pidgin. It is an access-to-justice tool, not legal advice.

## Features

- Nigerian Pidgin translation with everyday and formal tones
- Side-by-side English and Pidgin output
- Curated legal glossary with plain-Pidgin explanations
- Dictionary fallback that works without an API key
- Groq-powered full-text translation using an OpenAI-compatible API
- PDF, DOCX, TXT, Markdown, and CSV uploads
- Audio transcription and translation for MP3, WAV, M4A, AAC, OGG, FLAC, OPUS, and WebM
- Translation from public article, PDF, and audio URLs
- TXT and PDF export
- Rate limiting and private-network URL protection
- Docker-ready FastAPI service and Netlify static build

## Important limitations

The Groq API key is optional for pasted text and readable document dictionary mode, but required for full generated translation and audio transcription. Groq does not provide OCR for scanned PDFs in this project; searchable PDFs work through local extraction, while scanned PDFs are rejected with a clear message.

Uploaded files and linked content are sent to the configured provider when AI translation is used. Do not submit confidential, privileged, personal, or sensitive legal documents unless your provider and deployment policy allow it. Translation does not replace a Nigerian lawyer, legal aid clinic, or court guidance.

## Quick start

Requirements: Python 3.12 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

Open http://127.0.0.1:8000.

The application runs in dictionary mode without an API key. For generated translation and audio, create a Groq key at https://console.groq.com/keys and set it in `.env`:

```dotenv
GROQ_API_KEY=your-key-here
GROQ_MODEL=openai/gpt-oss-120b
GROQ_AUDIO_MODEL=whisper-large-v3-turbo
```

Never commit `.env` or expose `GROQ_API_KEY` in browser code.

## Input support

| Input | Without Groq | With Groq |
| --- | --- | --- |
| Pasted text | Glossary dictionary mode | Full Pidgin translation |
| TXT, Markdown, CSV | Local extraction plus dictionary mode | Full Pidgin translation |
| DOCX and searchable PDF | Local extraction plus dictionary mode | Full Pidgin translation |
| Audio upload or audio URL | Not available | Whisper transcription, then Pidgin translation |
| Scanned PDF | Rejected | Rejected; OCR is not enabled |
| Public HTML article URL | Local extraction plus dictionary mode | Full Pidgin translation |

Maximum source size is 14 MB. URL ingestion accepts only public HTTP/HTTPS URLs and blocks localhost and private-network addresses.

## API

Interactive API documentation is available at http://127.0.0.1:8000/api/docs.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Service status and active model |
| POST | `/api/translate` | Translate pasted text |
| POST | `/api/translate/file` | Translate an uploaded document or audio file |
| POST | `/api/translate/url` | Fetch and translate a public article, PDF, or audio URL |
| GET | `/api/glossary` | Search the legal glossary |
| GET | `/api/samples` | Load example documents |
| POST | `/api/export/txt` | Download a TXT report |
| POST | `/api/export/pdf` | Download a PDF report |

## Project structure

```text
app/
  main.py                 FastAPI application and static frontend
  config.py               Environment-backed settings
  models/                 Pydantic request and response schemas
  routers/                Text, source, glossary, and export endpoints
  services/               Translation, ingestion, chunking, glossary, and PDF logic
  data/                   Glossary and sample documents
  static/                 Browser UI, styles, and JavaScript
scripts/                  Netlify static build script
tests/                    API and service tests
Dockerfile                Container deployment
netlify.toml              Netlify static frontend configuration
```

## Tests

```powershell
python -m pytest -q
```

The tests do not call Groq. Provider calls are mocked where needed.

## Docker

Build and run the API locally:

```powershell
docker build -t pidgin-law .
docker run --env-file .env -p 8000:8000 pidgin-law
```

## Deployment

GitHub contains the source repository:

https://github.com/awajiogakfinomo-crypto/pidgin-law

Netlify can host the static frontend using the included `netlify.toml`:

- Build command: `python scripts/build_netlify.py`
- Publish directory: `dist`
- No environment variables are required for static dictionary mode.
- Set `API_BASE_URL` to a public FastAPI service URL to enable server-backed translation, files, audio, links, and exports.

Netlify does not run this Python API. Deploy the Dockerfile to a container host such as Render and set `GROQ_API_KEY` there. Keep the API URL and provider key server-side. The Dockerfile uses the host-provided `PORT` value.
