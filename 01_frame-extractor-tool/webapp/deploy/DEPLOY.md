# Deploy runbook — VPS steps

Everything here is a step you run yourself on a VPS you've provisioned (account creation and payment
aren't automated by anything in this repo). See `../README.md`'s "Deploying it publicly" section for
the reasoning behind each choice; this file is just the ordered command list.

## 1. Provision the VPS

DigitalOcean or Vultr, Singapore region. 4 GB RAM / 2 vCPU / 80 GB SSD tier. Ubuntu 24.04 LTS. No GPU
needed. Point a domain's A record at the new server's IP now — Caddy (step 5) needs that to already
be resolving before it can get a certificate.

## 2. Base packages + firewall

```bash
sudo apt update && sudo apt install -y python3.12-venv python3-pip git tesseract-ocr rsync
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable
sudo adduser deploy   # non-root user the app runs as
```

Caddy isn't in the default Ubuntu repos at a current version — add its official repo before
installing (see https://caddyserver.com/docs/install#debian-ubuntu-raspbian for the exact commands),
then `sudo apt install caddy`.

## 3. Copy the app code

From your machine (not the VPS), one-time transfer — `git clone`/`pull` won't have uncommitted local
work, and `-a` is required so model file mtimes survive the copy (the default-model picker sorts by
mtime):

```bash
rsync -a --exclude='.venv' --exclude='data' --exclude='state.json*' \
  01_frame-extractor-tool/ deploy@<vps-ip>:/opt/frame-extractor/
```

Do **not** copy `01_frame-extractor-tool/webapp/data/` — start the public instance's data directory
empty (see README's "Data" note). The `models/*.pt` files under `01_frame-extractor-tool/models/` are
included by the rsync above and are needed.

## 4. App setup on the VPS

```bash
python3 -m venv /opt/frame-extractor/webapp/.venv
/opt/frame-extractor/webapp/.venv/bin/pip install \
  -r /opt/frame-extractor/requirements.txt \
  -r /opt/frame-extractor/webapp/requirements.txt
```

Create `/opt/frame-extractor/webapp/.env` (copy `.env.example`, do not commit it) with at minimum:

```
DATA_DIR=/opt/frame-extractor/webapp/data
MAX_UPLOAD_SIZE_MB=1024
MAX_TOTAL_UPLOAD_MB=8192
MAX_CONCURRENT_JOBS=1
```

The rest of `.env.example`'s defaults (disk floor, rate limits, body-size cap) are fine as shipped for
a first deploy; tune later against real traffic.

Install and start the service:

```bash
sudo cp /opt/frame-extractor/webapp/deploy/frame-extractor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now frame-extractor
```

## 5. Caddy

```bash
sudo cp /opt/frame-extractor/webapp/deploy/Caddyfile /etc/caddy/Caddyfile
# edit /etc/caddy/Caddyfile: replace your-domain.example.com with the real domain
sudo systemctl reload caddy
```

## 6. Verify

```bash
systemctl status frame-extractor caddy         # both active (running)
curl -I https://<your-domain>/api/health       # 200, real cert, no -k needed
```

Then in a browser: confirm the page loads straight into the Extract tab with no login prompt, and
that Detect's default-loaded model is `ssid9_960px_150ep_20260813_map50-716.pt` (not one of the
5-class `ssid_v6i_*` models — that would mean the mtime-based picker fix didn't make it into the
transferred copy).
