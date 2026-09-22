# Why `allin1-app.tar.gz` says "Extraction error"

## Short answer

**`allin1-app.tar.gz` is not an Android app.** It cannot be installed on a phone,
and no amount of tapping "install" will work. The *"Extraction error. Please check
the files."* popup is coming from your **file manager**, not from Allin1. It is the
generic message Android file managers show when you ask them to extract an archive
they refuse to open — it says nothing about whether the file is corrupt.

The `.tar.gz` is a **server bundle**. It is the thing you deploy to a server, and
then you open Allin1 in a browser and install it as a PWA.

## What is actually in that file

The build script (`scripts/build.sh`) runs this:

```bash
tar czf dist/allin1-app.tar.gz backend frontend \
  requirements.txt requirements-dev.txt Dockerfile README.md scripts pyproject.toml
```

So it is just **source code for a Python web server** — 45 files:

| Member | What it is |
|---|---|
| `backend/` | The FastAPI server (yt-dlp + ffmpeg wrapper) |
| `frontend/` | The PWA: `index.html`, CSS, JS, manifest, service worker, icon |
| `requirements.txt` | Python dependencies — these are **not** included in the tarball |
| `Dockerfile` | Recipe for running it in a container |
| `scripts/build.sh` | The script that produced the tarball |

A phone has no Python runtime, no `pip`, and no `ffmpeg`, so even if the archive
unpacked cleanly there is nothing on an Android device that could run it.

## The archive is not corrupted

Verified by rebuilding it from the repo and inspecting every entry:

- gzip magic bytes correct (`1f 8b 08 00`)
- valid gzip + tar stream, **45/45 members** readable
- 1.6 MB

Your file manager simply does not handle `.tar.gz` (very common — many Android
file managers only extract `.zip` and `.rar`).

## How to actually run Allin1

### Option A — Docker (recommended, any VPS or your laptop)

```bash
docker build -t allin1 .
docker run --rm -p 8000:8000 -v allin1-data:/app/data allin1
```

Then open <http://localhost:8000>.

### Option B — Plain Python

Needs Python 3.12+ **and** `ffmpeg` on the server:

```bash
pip install -r requirements.txt
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

### Then install it as an app

Open the server's URL **in Chrome/ Safari**, then:

- **Android / Chrome:** ⋮ menu → *Add to Home screen* / *Install app*
- **iOS / Safari:** Share → *Add to Home Screen*
- **Desktop:** the install icon in the address bar

That is the real install path for this project. The `manifest.json` and
`service-worker.js` in `frontend/` are already wired for it, and FastAPI serves
the frontend itself from `/`.

## If you wanted a real Android app

The current repo cannot produce one. A genuine `.apk` would need a separate
project — the usual approach is a thin Android wrapper (Kotlin/Compose or
Capacitor) that either:

1. opens your hosted Allin1 server in a WebView, or
2. downloads the file and hands it to Android's `DownloadManager`.

That is a different codebase from this one, not a rebuild of it.

## Environment notes (verified in this workspace)

- Python dependencies installed from PyPI ✅
- `ffmpeg` installed as a static build at `~/.local/bin/ffmpeg` ✅
  (`ffprobe` was **not** available — it needs a binary that the sandbox could not
  download. Affects some format probing, not merging or MP3 conversion.)
- Test suite: **30 passed** ✅
- Server healthy on `0.0.0.0:8000`, `/api/health` → `{"status":"ok","ffmpeg_available":true}` ✅
- Live extraction of real media is blocked in this sandbox by its network
  policy (outbound TLS to media sites is filtered).
