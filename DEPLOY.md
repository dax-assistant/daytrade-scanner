# Deploy

## Current production target

- Host: Tower (`10.1.1.235`)
- App path: `/mnt/user/appdata/daytrade-scanner`
- Health URL: `http://10.1.1.235:8081/api/health`
- Image: `ghcr.io/dax-assistant/daytrade-scanner:latest`

## Production layout on Tower

```text
/mnt/user/appdata/daytrade-scanner/
├── docker-compose.yml
├── config/
│   └── config.yaml
├── data/
│   └── scanner.db
└── logs/
```

## Deploy flow

1. Push changes to `main`
2. GitHub Actions builds and pushes a new image to GHCR
3. Tower's global Watchtower sees the new image
4. Tower restarts the `daytrade-scanner` container

## First-time setup

### 1. Log in Tower to GHCR

```bash
docker login ghcr.io -u dax-assistant
```

### 2. Create app directories

```bash
mkdir -p /mnt/user/appdata/daytrade-scanner/config
mkdir -p /mnt/user/appdata/daytrade-scanner/data
mkdir -p /mnt/user/appdata/daytrade-scanner/logs
```

### 3. Copy runtime config

Copy the real config to:

- `/mnt/user/appdata/daytrade-scanner/config/config.yaml`

### 4. Copy compose file

Copy:

- `deploy/tower/docker-compose.yml`

into:

- `/mnt/user/appdata/daytrade-scanner/docker-compose.yml`

### 5. Start the app

```bash
cd /mnt/user/appdata/daytrade-scanner
docker-compose up -d
```

## Verify

```bash
curl http://10.1.1.235:8081/api/health
docker logs --tail 100 daytrade-scanner
```

## Roll back

```bash
docker image ls | grep daytrade-scanner
# pick a prior image digest/tag, edit docker-compose.yml, then:
docker-compose up -d
```

## Notes

- `config.example.yaml` is safe for GitHub
- the real `config.yaml` stays off-repo
- production state lives in `data/scanner.db`
- Watchtower watches Docker image updates, not git commits directly
