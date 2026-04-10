# Day Trade Scanner

Momentum scanner and paper-trading simulator for small-cap trading setups.

## Implementation checklist

- [x] Split the app into a standalone deployable project
- [x] Remove live secrets from tracked config
- [x] Add a Dockerfile and `.dockerignore`
- [x] Add GitHub Actions to build and push `ghcr.io/<owner>/daytrade-scanner`
- [x] Add Tower deployment files with persistent config, data, and logs
- [x] Add a dedicated Watchtower sidecar scoped to this app
- [ ] Create the GitHub repository
- [ ] Push the standalone project to GitHub
- [ ] Let GitHub Actions publish the first container image
- [ ] Copy real config to Tower
- [ ] Deploy the stack on Tower
- [ ] Verify health and auto-update behavior

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py --config config.yaml
```

## Container runtime

The image expects the runtime config to be mounted at:

- `/app/config/config.yaml`

Persistent paths:

- `/app/data`
- `/app/logs`

Health endpoint:

- `GET /api/health`

## Tower deployment

Files for Tower live under `deploy/tower/`.

Expected layout on Tower:

```text
/mnt/user/appdata/daytrade-scanner/
├── docker-compose.yml
├── .env
├── config/
│   └── config.yaml
├── data/
└── logs/
```

Deploy with:

```bash
docker-compose up -d
```

## GitHub and auto-deploy flow

1. Push to `main`
2. GitHub Actions builds and publishes `ghcr.io/dax-assistant/daytrade-scanner:latest`
3. Tower Watchtower detects the updated image
4. Tower pulls and restarts the scanner container

## Config

- `config.example.yaml` is the safe template for GitHub
- the real `config.yaml` stays off-repo and gets mounted on Tower
