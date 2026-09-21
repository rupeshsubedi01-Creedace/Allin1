# Allin1 ⬇️

**Allin1** is a universal media downloader: paste a public link from YouTube,
TikTok, Instagram, Twitter/X, Facebook, Telegram, or any direct media URL,
pick a video quality (or MP3 audio), and download it with a live progress
bar. Every extraction and download is performed for real by
[`yt-dlp`](https://github.com/yt-dlp/yt-dlp) and [`ffmpeg`](https://ffmpeg.org/)
on the server — there are no mocked responses or fake delays.

- **Backend:** Python 3.12 + FastAPI, wrapping yt-dlp for extraction/downloading
  and ffmpeg for stream merging and MP3 conversion.
- **Frontend:** a responsive, installable PWA written in vanilla JS/HTML/CSS
  (works on phone and desktop, no build step required).
- **Live progress:** Server-Sent Events (SSE) stream percent / speed / ETA
  while a download runs, with cancel & retry support.
- **History:** every extract → download is recorded in SQLite, with
  re-download, delete, and clear-all actions.
- **Error handling:** invalid URLs, private/removed media, geo-blocked
  media, timeouts, network loss, and a missing ffmpeg binary all return
  clear, distinct, user-facing error messages.

---

## Project structure

```
Allin1/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers (extract, download, history, health)
│   │   ├── services/       # platform detection, yt-dlp extraction, download manager, error taxonomy
│   │   ├── config.py       # environment-driven settings
│   │   ├── db.py           # SQLite-backed history store
│   │   ├── main.py         # FastAPI app factory + static frontend mounting
│   │   └── schemas.py      # Pydantic request/response models
│   └── tests/               # pytest suite (offline, uses a locally generated media file)
├── frontend/                 # vanilla JS PWA (index.html, css/, js/, manifest, service worker)
├── scripts/build.sh          # lint + test + package build artifact
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
└── .github/workflows/build-and-run.yml
```

## How it works

1. **Extract** — `POST /api/extract {url}` validates the URL, detects the
   platform (icon + label), and runs `yt-dlp` (metadata only, no download)
   to return the real title, thumbnail, duration, and a curated list of
   available formats (best format per resolution, top audio-only formats,
   plus a synthetic "MP3 (192kbps)" option that is produced on the fly via
   ffmpeg during download).
2. **Download** — `POST /api/download {url, format_id, media_type, ...}`
   starts a background thread that runs `yt-dlp` with the chosen format
   selector (merging video+audio with ffmpeg when the chosen quality is
   video-only, or extracting MP3 audio with ffmpeg when requested). The job
   is tracked in memory and persisted to SQLite history.
3. **Progress** — `GET /api/download/{job_id}/events` is a Server-Sent
   Events stream. yt-dlp's `progress_hooks`/`postprocessor_hooks` push
   percent/speed/ETA/status straight to the browser in real time.
4. **Cancel** — `POST /api/download/{job_id}/cancel` sets a flag that is
   checked inside the next progress/postprocessor hook, which raises
   `yt_dlp.utils.DownloadCancelled` to cleanly abort the running download.
5. **File** — once a job's status is `completed`, `GET
   /api/download/{job_id}/file` streams the produced file to the browser.
6. **History** — `GET/DELETE /api/history`, `DELETE /api/history/{id}`,
   `POST /api/history/{id}/redownload` list, clear, delete, and re-trigger
   downloads from SQLite-backed records.

### Error handling

All failures are translated (see `backend/app/services/errors.py`) into one
of: `invalid_url`, `unsupported_url`, `media_unavailable` (private/removed),
`geo_blocked`, `timeout`, `network_error`, `ffmpeg_missing`, or a generic
`extraction_failed`, each with an HTTP status code and a plain-English
`message` the frontend displays directly to the user.

---

## Running locally (without Docker)

Requirements: Python 3.11+ (3.12 recommended), `ffmpeg` on your `PATH`.

```bash
cd Allin1
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Run the API + PWA (frontend is served by FastAPI itself)
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

If you cannot install `ffmpeg` with your system package manager (e.g. in a
restricted sandbox), a pip-provided static build works too:

```bash
pip install imageio-ffmpeg
ln -s "$(python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')" .venv/bin/ffmpeg
```

`ffprobe` is optional: yt-dlp automatically falls back to `ffmpeg -i` when
it is absent.

Open <http://localhost:8000> in your browser (or on your phone via your
machine's LAN IP) — it's an installable PWA, so you can "Add to Home
Screen"/"Install App" on both mobile and desktop.

Data (SQLite history DB + downloaded files) is stored under `./data` by
default; override the location with the `ALLIN1_DATA_DIR` environment
variable.

## Running with Docker

```bash
cd Allin1
docker build -t allin1 .
docker run --rm -p 8000:8000 -v allin1-data:/app/data allin1
```

Then open <http://localhost:8000>.

## Deployment

The Docker image is self-contained (Python 3.12 + ffmpeg + all
dependencies) and listens on port `8000` with a `GET /api/health`
healthcheck baked in, so it can be deployed as-is to any container
platform, for example:

- **Fly.io / Render / Railway** — point them at the `Dockerfile`, expose
  port 8000, and mount a persistent volume at `/app/data` so history and
  downloaded files survive restarts.
- **A plain VPS** — `docker run -d --restart unless-stopped -p 8000:8000 -v /srv/allin1-data:/app/data allin1`
  and put nginx/Caddy in front for TLS.
- **Kubernetes** — build & push the image, mount a `PersistentVolumeClaim`
  at `/app/data`, and expose the Service behind an Ingress with a
  liveness probe on `/api/health`.

Because downloads can take a while for large videos, make sure your reverse
proxy does **not** buffer Server-Sent Events (e.g. with nginx, disable
buffering for the `/api/download/*/events` location — the app already sends
`X-Accel-Buffering: no`).

## Testing & CI

```bash
cd Allin1
bash scripts/build.sh   # ruff lint + pytest + package dist/allin1-app.tar.gz
```

The test-suite never talks to a real social platform. Instead,
`backend/tests/conftest.py` uses `ffmpeg` to synthesize a short local MP4
(test pattern + tone) and serves it over a throw-away
`http.server.ThreadingHTTPServer` on `127.0.0.1`. The tests then drive the
**full** extract → download → SSE-progress → history → re-download → delete
flow against that local URL through FastAPI's `TestClient`, so every code
path (including ffmpeg's MP4 merge/mp3-extraction post-processing) runs for
real.

GitHub Actions (`.github/workflows/build-and-run.yml`) runs on every push
and pull request to `main`: it sets up Python 3.12, installs `ffmpeg` +
dependencies, runs `ruff` and `pytest`, executes `scripts/build.sh`, and
uploads the resulting `dist/allin1-app.tar.gz` as a build artifact.

## API reference (summary)

| Method & path                              | Description                                   |
| ------------------------------------------- | ---------------------------------------------- |
| `GET  /api/health`                          | Liveness/readiness probe                       |
| `POST /api/extract`                         | `{url}` → title, thumbnail, formats            |
| `POST /api/download`                        | Start a download job → `{job_id}`              |
| `GET  /api/download/{job_id}/events`        | SSE progress stream                            |
| `POST /api/download/{job_id}/cancel`        | Cancel a running job                           |
| `GET  /api/download/{job_id}/file`          | Download the completed file                    |
| `GET  /api/history`                         | List all history entries                       |
| `POST /api/history/{id}/redownload`         | Re-run a past download                         |
| `DELETE /api/history/{id}`                  | Delete one history entry (+ its file)          |
| `DELETE /api/history`                       | Clear all history (+ all files)                |

## Notes & limitations

- Some platforms (Instagram, private Facebook groups, age-restricted
  YouTube videos, etc.) require the visitor to be logged in; yt-dlp cannot
  bypass that, and Allin1 surfaces it as a `media_unavailable` error rather
  than failing silently.
- Legal note: only download media you have the right to download (your own
  content, permissively licensed content, or content you have permission to
  save for personal/offline use).
