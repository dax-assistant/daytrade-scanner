# Tower rollout

Use `deploy/tower/rollout.sh` on Tower to manage the per-environment Daytrade Scanner containers.

## Services
- dev -> `daytrade-scanner-dev` -> port `8082`
- uat -> `daytrade-scanner-uat` -> port `8083`
- prod -> `daytrade-scanner-prod` -> port `8081`

## Prereqs
- `deploy/tower/.env.dev`, `.env.uat`, `.env.prod` present
- config files mounted at:
  - `/mnt/user/appdata/daytrade-scanner/dev/config/config.yaml`
  - `/mnt/user/appdata/daytrade-scanner/uat/config/config.yaml`
  - `/mnt/user/appdata/daytrade-scanner/prod/config/config.yaml`
- Docker logged into GHCR on Tower

## Commands
```bash
cd /mnt/user/appdata/daytrade-scanner/deploy/tower
bash rollout.sh dev pull-up
bash rollout.sh uat pull-up
bash rollout.sh prod pull-up
```

Pin a specific image tag:
```bash
bash rollout.sh dev pull-up sha-80812b0
bash rollout.sh uat pin sha-80812b0
bash rollout.sh prod pin sha-80812b0
```

Other actions:
```bash
bash rollout.sh dev restart
bash rollout.sh uat logs
bash rollout.sh prod ps
```

## Recommended promotion flow
1. Update dev config and deploy `dev`
2. Verify UI, broker status, reconciliation behavior, and open-order controls on `:8082`
3. Promote the exact same image tag to `uat` and verify on `:8083`
4. Promote the same pinned tag to `prod` only after UAT passes

## Post-deploy checks
- `docker compose -f docker-compose.yml ps`
- dashboard loads
- `/api/trading/status`
- `/api/broker/account`
- `/api/broker/orders/open`
- broker reconcile button completes without error
