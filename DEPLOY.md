# Deploying Allin1

Two independent pieces:

| Piece | What it is | Where it goes |
| --- | --- | --- |
| **Server** | FastAPI + yt-dlp + ffmpeg | Render / Fly.io / a VPS / your own PC |
| **App** | The Android APK | Your phone — already published at [`apk-latest`](https://github.com/rupeshsubedi01-Creedace/Allin1/releases/tag/apk-latest) |

The app is just a client. It needs a server to talk to.

---

## ⚠️ Read this first: datacenter IPs and YouTube

**This is the single biggest gotcha with this app.**

YouTube aggressively blocks requests from datacenter IP ranges (AWS, GCP,
Render, Fly, DigitalOcean…). On a cloud host you will frequently see:

> `Sign in to confirm you're not a bot`

That is YouTube blocking the *hosting provider's IP range*, not a bug in
Allin1. TikTok and Instagram are usually more permissive; YouTube is the
strict one.

So pick based on what you need:

| Option | YouTube reliability | Cost | Reachable from anywhere? |
| --- | --- | --- | --- |
| **Run on your own PC** (recommended) | ✅ Best — residential IP | Free | Only on your home Wi-Fi |
| VPS with a residential-ish IP | ⚠️ Sometimes | ~$5/mo | Yes |
| Render / Fly free tier | ❌ Often blocked | Free | Yes |

If your main use is YouTube, run it on your own machine. You can also add
`--cookies-from-browser`-style support later (yt-dlp supports passing a
cookies file) if you need it on a cloud host.

---

## Option A — Run it on your own PC (best for YouTube, free)

Any Windows/macOS/Linux machine on the same Wi-Fi as your phone.

**1. Install ffmpeg** (required — merging and MP3 conversion need it)

- Windows: `winget install Gyan.FFmpeg`
- macOS: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

**2. Install and start Allin1**

```bash
git clone https://github.com/rupeshsubedi01-Creedace/Allin1.git
cd Allin1
pip install -r requirements.txt
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

**3. Find your PC's LAN IP**

- Windows: `ipconfig` → look for *IPv4 Address* (usually `192.168.x.x`)
- macOS: `ipconfig getifaddr en0`
- Linux: `hostname -I`

**4. Point the app at it**

Open **Allin1** on your phone → overflow menu (⋮) → **Change server** → type:

```
192.168.1.10:8000
```

(use your real IP). Because it's a private address the app automatically
uses `http://`. Leave the PC running and your phone will connect over your
home network.

> Note: phones on mobile data cannot reach a home LAN IP. This works on your
> home Wi-Fi only — that is the trade-off for the better YouTube success rate.

---

## Option B — Render (free, reachable anywhere)

No CLI needed; works from your phone's browser.

1. Sign up at <https://render.com> and connect your GitHub account.
2. **New +** → **Blueprint**.
3. Pick the `rupeshsubedi01-Creedace/Allin1` repository.
4. Render reads `render.yaml` and shows a service called `allin1`. Approve it.
5. Wait for the first build (~3-5 minutes — it installs ffmpeg and Python deps).
6. Note the URL it gives you, e.g. `https://allin1-xxxx.onrender.com`.
7. Open that URL — you should see the Allin1 interface.

Then put that URL into the app via **Change server**.

**Free-tier caveats (know before you rely on it):**

- The instance **sleeps after ~15 minutes idle**. The next request takes
  ~50 seconds to wake. Your phone will show a loading spinner, then work.
- **No persistent disk** on the free plan, so download history resets on every
  redeploy. Add a Disk (paid) mounted at `/app/data` to keep it.
- Very large videos may hit memory limits on the free instance.

---

## Option C — Fly.io

```bash
# 1. Install flyctl, then:
fly auth login

# 2. Edit fly.toml and change `app` to a globally unique name

# 3. Create the volume that holds history + media
fly volumes create allin1_data --size 1

# 4. Deploy
fly deploy
```

`fly.toml` already mounts the volume at `/app/data`, sets the health check to
`/api/health`, and runs `scripts/start.sh` (which honours the `$PORT` Fly
injects). Fly has a genuinely usable free allowance and a Singapore region
(`sin`), which is the closest to Dubai.

---

## Option D — A plain VPS

```bash
docker build -t allin1 .
docker run -d --restart unless-stopped \
  -p 8000:8000 \
  -v /srv/allin1-data:/app/data \
  allin1
```

Put nginx or Caddy in front for TLS. **Important:** disable response buffering
for SSE, or the live progress bar will arrive in one lump at the end:

```nginx
location /api/download/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_buffering off;
    proxy_read_timeout 3600s;
}
```

The app already sends `X-Accel-Buffering: no`, which nginx honours, but
`proxy_buffering off` makes it explicit.

---

## After deploying: connect the app

1. Download the APK: <https://github.com/rupeshsubedi01-Creedace/Allin1/releases/download/apk-latest/allin1.apk>
2. Tap it and allow *"Install unknown apps"* when Android asks.
3. Open **Allin1**, enter your server address, tap **Connect**.

Bare addresses like `192.168.1.10:8000` become `http://…`; anything else
becomes `https://…`. You can change the address any time from the ⋮ menu.

### Rebuilding the APK with your URL baked in

So you never have to type the address:

**GitHub → Actions → Build Android APK → Run workflow** and put your URL in
the `server_url` box. Or locally:

```bash
cd android
gradle assembleDebug -Pallin1ServerUrl=https://your-app.onrender.com
```

---

## Verifying a deployment

```bash
curl https://your-app.example.com/api/health
# {"status":"ok","ffmpeg_available":true}
```

If `ffmpeg_available` is `false`, the container is missing ffmpeg — the
bundled `Dockerfile` installs it, so you are probably running the raw Python
entrypoint without ffmpeg on `PATH`.

---

## Config reference

| Variable | Default | Purpose |
| --- | --- | --- |
| `ALLIN1_DATA_DIR` | `<repo>/data` | SQLite history DB + downloaded files. Point at your persistent volume. |
| `PORT` | `8000` | Bind port. Injected automatically by most platforms. |
| `ALLIN1_CORS_ORIGINS` | `*` | Comma-separated browser origin allowlist. The PWA and Android app are same-origin and don't need it. |
| `FFMPEG_BINARY` | `ffmpeg` | Override the ffmpeg path. |
| `WEB_CONCURRENCY` | `1` | Keep at **1** — job state is in-process, so extra workers won't share it. |
