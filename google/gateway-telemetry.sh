#!/usr/bin/env bash
# Read recent Gateway request telemetry without printing request URLs or headers.
set -euo pipefail

if [[ $# -ne 2 || ! ${2:-} =~ ^[a-z][a-z0-9-]*$ ]]; then
  printf 'Usage: bash google/gateway-telemetry.sh PROJECT_ID GATEWAY_ID\n' >&2
  exit 2
fi

project_id=$1
gateway_id=$2
filter='log_id("apigateway.googleapis.com/requests")'
filter+=" AND resource.labels.gateway_id=\"$gateway_id\""

gcloud logging read "$filter" --project="$project_id" --quiet \
  --freshness=1h --limit=30 \
  --format='table(timestamp,httpRequest.requestMethod,httpRequest.status,httpRequest.latency,jsonPayload.apiMethod,trace)'
