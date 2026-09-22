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
├── android/                  # native Android shell (Kotlin + WebView) for the API
├── render.yaml / fly.toml    # one-command deploy configs
├── Procfile                  # Railway / Heroku-style entrypoint
└── .github/workflows/
    ├── build-and-run.yml     # lint + tests + server bundle artifact
    └── android-apk.yml       # compiles and publishes the installable APK
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

Requirements: Python 3.12, `ffmpeg` on your `PATH`.

```bash
cd Allin1
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Run the API + PWA (frontend is served by FastAPI itself)
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

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

## Android app

`android/` contains a small native Android shell that turns a hosted Allin1
server into an installable app. It is **not** a second implementation of the
downloader — the server still does all the work with yt-dlp + ffmpeg. The app
renders the bundled PWA in a WebView and then hands finished media to Android's
`DownloadManager`, so files land in your device's **Downloads** folder instead
of being trapped in browser storage.

- Written in Kotlin against the plain Android View system (no Compose, no
  Capacitor) — the whole app is one `Activity` plus resources.
- On first launch it asks for your server address. Bare LAN/loopback addresses
  default to `http://`, everything else to `https://`. The address is stored,
  and can be changed any time from the overflow menu.
- Links to other hosts open in the normal browser; the back button walks
  WebView history.
- A default server URL can be baked in at build time:
  `gradle assembleDebug -Pallin1ServerUrl=https://your-app.onrender.com`

### Getting the APK

You do **not** need Android Studio or any local toolchain. The
[`Build Android APK`](.github/workflows/android-apk.yml) workflow compiles it on
GitHub's runners and publishes the result to the **`apk-latest`** release:

```
https://github.com/rupeshsubedi001-Creedace/Allin1/releases/latest/download/allin1.apk
```

(replace the owner/repo with your own). Trigger it from **Actions → Build
Android APK → Run workflow**; it also runs automatically on changes to
`android/`. Every run uploads `allin1-apk` as a downloadable build artifact as
well.

### Installing it

1. Open the APK link on your phone and download it.
2. Tap the downloaded file. Android will ask you to allow *"Install unknown
   apps"* for your browser or file manager — allow it, then confirm.
3. Open **Allin1** and enter your server address (skip this if you baked one in
   with `-Pallin1ServerUrl`).

The APK is a **debug build**: it is signed with the standard debug key, which
is fine for sideloading but cannot be uploaded to Google Play. For a Play Store
release you would add your own signing config to `android/app/build.gradle.kts`.

## Deployment

> **Step-by-step hosting walkthrough:** see **[DEPLOY.md](DEPLOY.md)** — it
> covers Render, Fly.io, a VPS and running it on your own PC, and explains an
> important caveat: **YouTube often blocks datacenter IP ranges**, so a cloud
> host may hit "Sign in to confirm you're not a bot" where a home machine
> would not.

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

### One-command deploy configs in this repo

| File | Platform | How |
| --- | --- | --- |
| `render.yaml` | Render | **New + → Blueprint**, pick this repo. Free plan works (no persistent disk, so history resets on deploy). |
| `fly.toml` | Fly.io | `fly launch --copy-config --no-deploy` (change `app` to a unique name), then `fly volumes create allin1_data --size 1`, then `fly deploy`. |
| `Dockerfile` | Any container host | `docker build -t allin1 . && docker run -p 8000:8000 -v allin1-data:/app/data allin1` |
| `Procfile` | Railway / Heroku-style | Detects `web:` and runs `scripts/start.sh`. |

`scripts/start.sh` is the single production entrypoint: it honours the `$PORT`
variable that these platforms inject, binds `0.0.0.0`, and enables proxy
headers so HTTPS redirects and health checks behave behind their load
balancers.

Configuration is environment-driven (see `.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `ALLIN1_DATA_DIR` | `<repo>/data` | Where the SQLite history DB and downloaded files live. Point this at your persistent volume. |
| `PORT` | `8000` | Bind port. |
| `ALLIN1_CORS_ORIGINS` | `*` | Comma-separated browser origin allowlist for the API. The PWA and the Android app are same-origin, so they never need this. |
| `FFMPEG_BINARY` | `ffmpeg` | Override the ffmpeg binary path. |
| `WEB_CONCURRENCY` | `1` | Keep at 1 — job state lives in-process, so extra workers would not share it. |

> **Put this behind HTTPS.** The app works over plain HTTP, but `yt-dlp` needs
> outbound internet from the server, and running it on an open port invites
> abuse. Render, Fly and Railway all give you TLS for free.

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

> **Note:** `dist/allin1-app.tar.gz` is a *server bundle* — source code, the
> `Dockerfile`, and helper scripts. It is meant to be unpacked on a machine or
> container that has Python and ffmpeg, **not installed on a phone**. Android
> file managers will refuse to open a `.tar.gz` and show a generic
> "Extraction error". To get something you can actually install on a phone,
> use the APK produced by `android-apk.yml` (see
> [Android app](#android-app)).

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
