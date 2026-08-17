# Temporary Cloudflare stand

`temporary-tunnel.sh` starts an isolated test stand with three containers:

- `devboard-api` — FastAPI without a published host port;
- `devboard-web` — frontend with Basic Auth and API reverse proxy;
- `devboard-tunnel` — Cloudflare Quick Tunnel with a temporary HTTPS URL.

Server-only state must exist before the first start:

```text
/opt/DevBoard/runtime/.env
/opt/DevBoard/runtime/storage/
```

Set `DEVBOARD_COOKIE_SECURE=true` in the server `.env`. Application secrets and
attachments remain on the VPS and are never passed through GitHub Actions.

Start or rebuild the stand:

```bash
cd /opt/DevBoard
./deploy/temporary-tunnel.sh
```

The script prints the new `trycloudflare.com` URL. Basic Auth uses login
`devboard`; its generated password stays in `/opt/DevBoard/runtime/access.txt`.
The `/api/` route uses DevBoard's own cookie or Bearer-token authentication so
the coding-agent CLI remains usable through the tunnel.

The Cloudflare URL changes whenever the tunnel container is recreated.

The GitHub Actions workflow is manual until the repository has the five VPS
secrets documented in `.github/workflows/deploy-main.yml`. After that, push to
`main` can be enabled as the deployment trigger.
