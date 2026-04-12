#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-}"
ACTION="${2:-pull-up}"
IMAGE_TAG="${3:-${DAYTRADE_SCANNER_IMAGE_TAG:-latest}}"
COMPOSE_FILE="$(cd "$(dirname "$0")" && pwd)/docker-compose.yml"

if [[ -z "$ENV_NAME" ]]; then
  echo "Usage: $0 <dev|uat|prod> [pull-up|restart|logs|ps] [image-tag]" >&2
  exit 1
fi

case "$ENV_NAME" in
  dev) SERVICE="daytrade-scanner-dev" ;;
  uat) SERVICE="daytrade-scanner-uat" ;;
  prod) SERVICE="daytrade-scanner-prod" ;;
  *) echo "Invalid env: $ENV_NAME" >&2; exit 1 ;;
esac

run_compose() {
  DAYTRADE_SCANNER_IMAGE_TAG="$IMAGE_TAG" docker compose -f "$COMPOSE_FILE" "$@"
}

printf 'Using image tag: %s\n' "$IMAGE_TAG"

case "$ACTION" in
  pull-up)
    run_compose pull "$SERVICE"
    run_compose up -d "$SERVICE"
    run_compose ps "$SERVICE"
    ;;
  pin)
    run_compose up -d "$SERVICE"
    run_compose ps "$SERVICE"
    ;;
  restart)
    run_compose restart "$SERVICE"
    run_compose ps "$SERVICE"
    ;;
  logs)
    run_compose logs --tail=150 "$SERVICE"
    ;;
  ps)
    run_compose ps "$SERVICE"
    ;;
  *)
    echo "Invalid action: $ACTION (expected pull-up|pin|restart|logs|ps)" >&2
    exit 1
    ;;
esac
