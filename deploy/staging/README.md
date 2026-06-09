# Staging DRF on Hetzner Cloud

Target: `https://api.malagasyfishes.org` → Django + DRF + PostGIS + Redis behind Caddy on a single Hetzner Cloud VPS.

Decision context: `docs/planning/specs/gate-07-mvp-public-frontend-v2.md` §9 amendment "W3 staging DRF decision: Hetzner Cloud" (2026-04-17). EU-domiciled per architecture §8.

Target live: **2026-04-24** (end of W1).

---

## 1. Provision the VPS

1. Create a Hetzner Cloud account (<https://console.hetzner.cloud>). Verify email.
2. Create a project: `madagascarfish`.
3. Add your SSH public key under **Security → SSH Keys**.
4. Create a server:
   - Location: **Nuremberg** or **Falkenstein** (Germany).
   - Image: **Ubuntu 24.04**.
   - Type: **CX22** (2 vCPU / 4 GB / 40 GB — €4.51/mo).
   - SSH key: the one you just added.
   - Name: `mffcp-staging`.
5. Note the public IPv4 address (referred to below as `$SERVER_IP`).

## 2. Point DNS at the server

In Cloudflare (the domain is on Cloudflare per the `malagasyfishes.org` amendment):

1. **DNS → Records → Add record**:
   - Type: **A**
   - Name: `api`
   - IPv4: `$SERVER_IP`
   - Proxy status: **DNS only** (grey cloud). Keep grey through the workshop window to avoid CDN-in-front-of-origin surprises; revisit post-2026-06-05.
2. Verify from your laptop: `dig +short api.malagasyfishes.org` returns `$SERVER_IP`.

## 3. Prepare the server (one-time)

SSH in as root:

```bash
ssh root@$SERVER_IP
```

Create a non-root deploy user, install Docker, enable the firewall:

```bash
# Create user
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys

# Docker
apt-get update && apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | tee /etc/apt/keyrings/docker.asc >/dev/null
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker deploy

# Firewall
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Unattended security updates
apt-get install -y unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades
```

SSH in as `deploy` for everything below:

```bash
ssh deploy@$SERVER_IP
```

## 4. Clone and configure

```bash
git clone https://github.com/AlekseiSaunders/malagasyfishes.git
cd malagasyfishes/deploy/staging
cp .env.example .env
```

Edit `.env` and fill in the placeholders. Generate the two secrets:

```bash
# DJANGO_SECRET_KEY
coopython3 -c 'import secrets; print(secrets.token_urlsafe(64))' = nniuycQufdx4u3DMHOvMC8ScYuUoRUTBUjELrS_Yhs7A4qvmh6qKkEAI4zVN--VSnymL2BwK9xI8p5-HHZbIGA

# POSTGRES_PASSWORD — use the same value in both POSTGRES_PASSWORD and DATABASE_URL
openssl rand -base64 32 | tr -d '/+=' | head -c 32 = AjzF006zVdpuhkFIUIF51iG09fhb7TNFd
```

Verify `CADDY_DOMAIN=api.malagasyfishes.org` and `DJANGO_ALLOWED_HOSTS=api.malagasyfishes.org` are set.

## 5. Bring the stack up

```bash
docker compose up -d --build
docker compose logs -f caddy   # watch TLS cert issuance; Caddy gets a Let's Encrypt cert automatically once DNS resolves
```

Expect Caddy's log to show `certificate obtained successfully` within ~30s of first request.

Verify health:

```bash
curl -sI https://api.malagasyfishes.org/api/v1/schema/ | head -1
# → HTTP/2 200
```

## 6. Seed data

The repo's `data/` directory (reference shapefiles + seed CSVs) is bind-mounted read-only into the `web` container at `/data`. Run the consolidated seed command:

```bash
docker compose exec web python manage.py seed_all
```

This loads watersheds + protected areas, species, then localities in order. Idempotent — safe to re-run after a `git pull`.

Then create an admin user for `/admin/` access:

```bash
docker compose exec web python manage.py createsuperuser
```

To seed only part of the data (e.g. after bumping just the species CSV):

```bash
docker compose exec web python manage.py seed_all --skip-reference --skip-localities
```

Or call the underlying commands directly with explicit paths — see `backend/species/management/commands/{load_reference_layers,seed_species,seed_localities}.py`.

## 7. Point the frontend at staging

In Vercel (Project → Settings → Environment Variables → Production):

- Set `NEXT_PUBLIC_API_URL=https://api.malagasyfishes.org`.
- Redeploy (push a noop commit or click "Redeploy" on the latest deployment — env var changes require a fresh build).

Verify:

- `https://malagasyfishes.org/` — hero coverage-gap stat shows a real number.
- `https://malagasyfishes.org/species/` — directory lists real species.
- `https://malagasyfishes.org/species/{id}/` — profile renders.

## 8. Updating

```bash
ssh deploy@$SERVER_IP
cd madagascarfish
git pull
cd deploy/staging
docker compose up -d --build
```

The `web` service runs `migrate` on boot, so schema changes apply automatically.

## 9. Backups (lightweight)

Daily Postgres dump via cron on the host:

```bash
crontab -e
# add:
0 3 * * * cd /home/deploy/madagascarfish/deploy/staging && docker compose exec -T db pg_dump -U mffcp mffcp | gzip > /home/deploy/backups/mffcp-$(date +\%F).sql.gz
0 4 * * 0 find /home/deploy/backups -name 'mffcp-*.sql.gz' -mtime +14 -delete
```

```bash
mkdir -p /home/deploy/backups
```

## 10. Decommission (post-Gate-09 migration)

When the EU-domiciled migration (architecture §8) retargets production away from Vercel, this staging VPS can either become production or be destroyed. Either way:

- Snapshot the server in Hetzner console before destroying.
- Cloudflare DNS: repoint `api` at the new host or delete the record.

---

## Troubleshooting

- **Caddy can't get a cert**: DNS probably hasn't propagated. `dig +short api.malagasyfishes.org` must return `$SERVER_IP`. Caddy will keep retrying.
- **502 from Caddy**: `docker compose logs web` — likely a Django startup error (missing env var, migration failure).
- **CORS errors in browser**: add the origin to `CORS_ALLOWED_ORIGINS` in `.env` and `docker compose up -d web`.
- **`DisallowedHost` in Django logs**: `DJANGO_ALLOWED_HOSTS` doesn't include the hostname the request came in under. Caddy forwards `Host`, so set it to `api.malagasyfishes.org`.
