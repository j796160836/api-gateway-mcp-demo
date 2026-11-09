# Google Cloud API Gateway for the order demo

[繁體中文](google-cloud-zh-tw.md)

`MCP or REST client → Google Cloud API Gateway → IAM-protected Cloud Run → FastAPI → SQLite`

API Gateway generates the remote `/mcp` endpoint from [the OpenAPI template](../google-cloud-openapi-example.yaml). The cloud path runs the REST service in Cloud Run. Google documents native MCP as **Public Preview** and supports tool discovery and invocation over HTTP POST, with short-lived calls. This path exposes `list_order`, `get_order`, `list_sku`, `check_inventory`, and `create_shipment`. Order creation is available over REST. Manager cancellation is outside the public Gateway configuration. [MCP overview](https://docs.cloud.google.com/api-gateway/docs/mcp-overview) · [Configure MCP](https://docs.cloud.google.com/api-gateway/docs/mcp-configure)

Use sample data in this environment. Cloud Run stores SQLite in the container's writable filesystem. A new instance or revision can start with a fresh database, and the instance limit below does not guarantee data durability. Use a persistent datastore such as Cloud SQL if you adapt the service for durable orders or multiple replicas. [Cloud Run filesystem](https://docs.cloud.google.com/run/docs/container-contract) · [Instance limits](https://docs.cloud.google.com/run/docs/configuring/max-instances)

## 1. Prepare a project

Run the commands from the repository root in Bash or Zsh. Install a current `gcloud` CLI, `curl`, and `jq`. Use a Google Cloud project with billing enabled and permissions to enable services, deploy Cloud Run and API Gateway, manage service accounts and the Cloud Run IAM policy, and create API keys. The deployer needs permission to act as the build, runtime, and Gateway service accounts. Source deployment also requires a build identity with `roles/run.builder` or the equivalent permissions. These steps can incur charges. [Cloud Run source deployment and IAM](https://docs.cloud.google.com/run/docs/deploying-source-code) · [API Gateway setup](https://docs.cloud.google.com/api-gateway/docs/get-started-cloud-run)

```sh
gcloud version
gcloud run deploy --help | grep -E 'build-service-account|invoker-iam-check'
```

Check that the help output includes both flags before deploying. If either flag is missing, update the CLI using your installation method and check again. If you are resuming this demo in the same project, reuse the service accounts you already created. [Install or update the Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk)

```sh
gcloud auth login
PROJECT_ID='your-google-cloud-project-id'
BACKEND_REGION='us-west2'
GATEWAY_REGION='us-west2'
SERVICE='order-demo-rest'
API_ID='order-demo-api'
CONFIG_ID='order-demo-v1'
GATEWAY_ID='order-demo-gateway'
KEY_ID='order-demo-client'
BUILD_SA="order-demo-build@${PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME_SA="order-demo-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
GATEWAY_SA="order-demo-gateway@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud billing projects describe "$PROJECT_ID" --format='value(billingEnabled)'
```

Continue only after the billing check returns `True`. If it returns `False`, link an active billing account before retrying. Cloud Build can upload the source before a billing problem surfaces when it pushes the image to Artifact Registry. [Verify project billing](https://docs.cloud.google.com/billing/docs/how-to/verify-billing-enabled)

```sh
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com apigateway.googleapis.com \
  servicemanagement.googleapis.com servicecontrol.googleapis.com \
  apikeys.googleapis.com iam.googleapis.com --project="$PROJECT_ID"

gcloud iam service-accounts create order-demo-build --project="$PROJECT_ID"
gcloud iam service-accounts create order-demo-runtime --project="$PROJECT_ID"
gcloud iam service-accounts create order-demo-gateway --project="$PROJECT_ID"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$BUILD_SA" --role=roles/run.builder
```

The example colocates Cloud Run and API Gateway in `us-west2`. Cloud Run can use `us-west1`, while API Gateway’s location list does not include it. The runtime account needs no application-specific Google Cloud roles for this demo. The separate Gateway account gets invocation access on this one service. [API Gateway locations](https://docs.cloud.google.com/api-gateway/docs/deployment-model#choose_a_google_cloud_region) · [Build service account](https://docs.cloud.google.com/run/docs/configuring/services/build-service-account)

### Set optional gcloud defaults

Set these defaults in the active gcloud configuration if you regularly work on this project. `core/project` selects the project containing the resources. `billing/quota_project` selects the project whose quota is used for the API request. This setting does not change the project's linked Cloud Billing account. [gcloud configuration](https://docs.cloud.google.com/sdk/gcloud/reference/config/set) · [Quota project settings](https://docs.cloud.google.com/docs/quotas/set-quota-project)

```sh
gcloud config set core/project "$PROJECT_ID"
gcloud config set billing/quota_project "$PROJECT_ID"
gcloud config get-value core/project
gcloud config get-value billing/quota_project
```

You can then omit `--project` and `--billing-project` when the defaults match the intended projects. The examples keep both flags where needed so they also work with other configurations. To remove either default, run `gcloud config unset core/project` or `gcloud config unset billing/quota_project`.

## 2. Deploy the REST backend to Cloud Run

The staging directory includes only the required application sources. The Cloud Run entry point translates the upstream request to the local REST service's key convention after Cloud Run IAM admits the caller. Keep the Cloud Run Invoker IAM check enabled and avoid public Invoker bindings. The Google API key belongs at the public Gateway boundary. [Cloud Run invocation policy](https://docs.cloud.google.com/run/docs/authenticating/public)

```sh
BUILD_DIR="$(mktemp -d)"
cp api.py config.py database.py requirements.txt google/cloud_run.py google/Dockerfile "$BUILD_DIR/"

gcloud run deploy "$SERVICE" --project="$PROJECT_ID" --region="$BACKEND_REGION" \
  --source="$BUILD_DIR" --service-account="$RUNTIME_SA" \
  --build-service-account="projects/$PROJECT_ID/serviceAccounts/$BUILD_SA" \
  --invoker-iam-check --no-allow-unauthenticated --max-instances=1

gcloud run services add-iam-policy-binding "$SERVICE" \
  --project="$PROJECT_ID" --region="$BACKEND_REGION" \
  --member="serviceAccount:$GATEWAY_SA" --role=roles/run.invoker

CLOUD_RUN_URL="$(gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" --region="$BACKEND_REGION" --format='value(status.url)')"
curl -sS -o /dev/null -w '%{http_code}\n' "$CLOUD_RUN_URL/orders"
```

The last request should be denied because it omits Cloud Run IAM credentials. Check the service's IAM settings if it returns HTTP 200.

### Build locally if you cannot grant the Cloud Build role

If your account cannot change project IAM, use Docker and Artifact Registry with an account that can create the repository and push images. Skip creation of the build service account and its `roles/run.builder` binding. Stage the sources as above, replace the source deployment command with the following, then continue with the Cloud Run Invoker binding and anonymous request check. [Build a Cloud Run image locally](https://docs.cloud.google.com/run/docs/building/containers#build_locally_and_push_using_docker)

```sh
REGISTRY="$BACKEND_REGION-docker.pkg.dev"
IMAGE_REPO='order-demo-images'
IMAGE="$REGISTRY/$PROJECT_ID/$IMAGE_REPO/$SERVICE:v1"

gcloud artifacts repositories create "$IMAGE_REPO" --repository-format=docker \
  --location="$BACKEND_REGION" --project="$PROJECT_ID"
gcloud auth configure-docker "$REGISTRY"
docker build --platform linux/amd64 -t "$IMAGE" "$BUILD_DIR"
docker push "$IMAGE"

gcloud run deploy "$SERVICE" --project="$PROJECT_ID" --region="$BACKEND_REGION" \
  --image="$IMAGE" --service-account="$RUNTIME_SA" \
  --invoker-iam-check --no-allow-unauthenticated --max-instances=1
```

## 3. Deploy API Gateway and restrict the client key

The first config creation also creates the API if it does not exist. The template uses the canonical Cloud Run URL as both the backend address and the audience of the ID token minted by Gateway. REST methods and MCP tool calls require the Google API key. The template also protects tool discovery with that same key. Protocol initialization is public by design. [OpenAPI extensions](https://docs.cloud.google.com/api-gateway/docs/oasv3-extensions) · [MCP authentication](https://docs.cloud.google.com/api-gateway/docs/mcp-configure#authentication_model)

```sh
API_SPEC="$BUILD_DIR/openapi-gateway.yaml"
sed "s|https://replace-with-your-cloud-run-url.run.app|$CLOUD_RUN_URL|g" \
  google-cloud-openapi-example.yaml > "$API_SPEC"

gcloud api-gateway api-configs create "$CONFIG_ID" \
  --api="$API_ID" --project="$PROJECT_ID" --openapi-spec="$API_SPEC" \
  --backend-auth-service-account="$GATEWAY_SA"

gcloud api-gateway gateways create "$GATEWAY_ID" \
  --api="$API_ID" --api-config="$CONFIG_ID" --location="$GATEWAY_REGION" --project="$PROJECT_ID"

MANAGED_SERVICE="$(gcloud api-gateway apis describe "$API_ID" \
  --project="$PROJECT_ID" --format='value(managedService)')"
gcloud services enable "$MANAGED_SERVICE" --project="$PROJECT_ID"
gcloud services api-keys create --key-id="$KEY_ID" --display-name="Order demo gateway" \
  --api-target="service=$MANAGED_SERVICE" --project="$PROJECT_ID" >/dev/null 2>&1

GATEWAY_KEY="$(gcloud services api-keys get-key-string "$KEY_ID" \
  --project="$PROJECT_ID" --billing-project="$PROJECT_ID" --format='value(keyString)')"
GATEWAY_HOST="$(gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$GATEWAY_REGION" --project="$PROJECT_ID" --format='value(defaultHostname)')"
GATEWAY_URL="https://$GATEWAY_HOST"
```

Wait until the Gateway is active and the managed service and key are ready. Key creation output is suppressed because the CLI can print the key in the operation result. If key creation fails, diagnose it in a private terminal. Keep the key out of source control. This demo uses an API key for shared access to sample data. For workloads with sensitive data or distinct user permissions, Google recommends stronger authentication. [API keys on Gateway](https://docs.cloud.google.com/api-gateway/docs/authenticate-api-keys) · [Restrict a CLI-created key](https://docs.cloud.google.com/sdk/gcloud/reference/services/api-keys/create)

### Find the Key ID for an existing deployment

List the Demo keys by display name. This command shows IDs and display names without returning key strings.

```sh
gcloud services api-keys list \
  --project="$PROJECT_ID" --billing-project="$PROJECT_ID" \
  --filter='displayName="Order demo gateway"' \
  --format='table(name.basename():label=KEY_ID,displayName)'
```

Use the value in `KEY_ID` as the argument to `gcloud services api-keys get-key-string`. For the deployed `flutter-markdown-drive` demo, the current ID is `order-demo-client-v2`. If several keys share a display name, check their API restrictions with `gcloud services api-keys describe KEY_ID` and select the one restricted to your Gateway's managed service. [Get a key string](https://docs.cloud.google.com/sdk/gcloud/reference/services/api-keys/get-key-string)

## 4. Smoke-test REST and create a fresh order

```sh
curl -sS -o /dev/null -w '%{http_code}\n' "$GATEWAY_URL/orders"
curl -fsS -H "x-api-key: $GATEWAY_KEY" "$GATEWAY_URL/orders" | jq .

ORDER_ID="$(curl -fsS -X POST "$GATEWAY_URL/orders" \
  -H "x-api-key: $GATEWAY_KEY" -H 'Content-Type: application/json' \
  -d '{"sku":"SKU-A01","quantity":2}' | jq -er '.orderId')"
printf 'New order: %s\n' "$ORDER_ID"
```

The anonymous request should be denied. The authenticated list should show sample orders on a fresh instance. Order creation returns HTTP 201 and a paid order. Check inventory before shipping it.

## 5. Smoke-test native MCP

Send JSON-RPC to the public Gateway URL after its state is `ACTIVE`. During provisioning, REST can start responding while `POST /mcp` still returns 404. The initialized notification normally returns HTTP 202. Use the negotiated protocol version for subsequent requests. Google Gateway expects REST path and query arguments at the top level, and a REST request body under `arguments.body`. [MCP handshake and arguments](https://docs.cloud.google.com/api-gateway/docs/mcp-configure#verify-mcp-support)

```sh
MCP_URL="$GATEWAY_URL/mcp"
MCP_VERSION="$(curl -fsS "$MCP_URL" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"order-demo","version":"1.0.0"}}}' \
  | jq -er '.result.protocolVersion')"

mcp_post() {
  curl -fsS "$MCP_URL" \
    -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -H "MCP-Protocol-Version: $MCP_VERSION" -H "x-api-key: $GATEWAY_KEY" \
    -d "$1"
}

mcp_post '{"jsonrpc":"2.0","method":"notifications/initialized"}'
mcp_post '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | jq -er '.result.tools[].name'
mcp_post "$(jq -nc --arg id "$ORDER_ID" \
  '{jsonrpc:"2.0",id:3,method:"tools/call",params:{name:"get_order",arguments:{order_id:$id}}}')" \
  | jq -e '.result | select(.isError != true)'
mcp_post '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"check_inventory","arguments":{"sku":"SKU-A01"}}}' \
  | jq -e '.result | select(.isError != true)'
```

Expect the five tools listed above. To try discovery without credentials, repeat the `tools/list` POST with the protocol and content headers and omit `x-api-key`. The response should deny discovery. To ship the new order, check the order and available quantity, then approve explicitly. A tool description alone does not enforce human approval, and an API-key holder can invoke the shipment operation.

```sh
printf 'Ship order %s? Type YES to approve: ' "$ORDER_ID"
read -r approval
if [ "$approval" = YES ]; then
  mcp_post "$(jq -nc --arg id "$ORDER_ID" \
    '{jsonrpc:"2.0",id:5,method:"tools/call",params:{name:"create_shipment",arguments:{body:{order_id:$id}}}}')" \
    | jq -e '.result | select(.isError != true)'
fi
```

A successful call returns a created shipment. Repeat `check_inventory` to confirm that stock dropped by two. The repository's local FastMCP CLI uses a different shipment argument shape. Use the requests above when demonstrating the Google-managed MCP endpoint.

## 6. Connect with Google Antigravity CLI (`agy`)

On macOS, copy the restricted API key to your clipboard. This command uses the key for the deployed `flutter-markdown-drive` demo. For your own deployment, substitute your project and key IDs. [Google Cloud CLI key retrieval](https://docs.cloud.google.com/sdk/gcloud/reference/services/api-keys/get-key-string)

```sh
gcloud services api-keys get-key-string order-demo-client-v2 \
  --project=flutter-markdown-drive \
  --billing-project=flutter-markdown-drive \
  --format='value(keyString)' --quiet | pbcopy
```

Open or create `~/.gemini/config/mcp_config.json`. Add `order-demo` under `mcpServers`, keeping any existing entries. Paste the key in place of `YOUR_GATEWAY_API_KEY`. For a different deployment, use its Gateway URL followed by `/mcp`. The global config is outside the repository. [Antigravity MCP configuration](https://antigravity.google/docs/mcp)

```json
{
  "mcpServers": {
    "order-demo": {
      "serverUrl": "https://order-demo-gateway-5p0lq3db.wl.gateway.dev/mcp",
      "headers": {
        "x-api-key": "YOUR_GATEWAY_API_KEY"
      }
    }
  }
}
```

Start `agy` and enter `/mcp` to check the connection or reload the configuration. Once `order-demo` is connected, try a read-only prompt. [Antigravity interactive MCP manager](https://antigravity.google/docs/mcp)

> Use `order-demo` to look up `ORD-1001` with `get_order`, then check the available stock for its SKU with `check_inventory`.

## Troubleshoot, update, and clean up

- **The Gateway rejects a key.** Confirm that the managed service is enabled in the key's project, the key's API restriction matches that exact managed service, and the request includes the `x-api-key` header. Wait for provisioning to propagate.
- **Backend 401 or 403.** Check the Gateway config's backend service account, its `roles/run.invoker` binding on the Cloud Run service, and the rendered `jwtAudience`. An anonymous request to Cloud Run should still fail.
- **Route or tool missing.** Confirm the active API config and use `POST /mcp` for MCP. To roll out changes, create a config with a new ID, then run `gcloud api-gateway gateways update "$GATEWAY_ID" --api="$API_ID" --api-config="$NEW_CONFIG_ID" --location="$GATEWAY_REGION" --project="$PROJECT_ID"`. [Gateway troubleshooting](https://docs.cloud.google.com/api-gateway/docs/troubleshoot) · [Update MCP tools](https://docs.cloud.google.com/api-gateway/docs/mcp-configure#update-exposed-mcp-tools)
- **Preview unavailable.** For a REST-only Gateway, remove the `mcp` block under `x-google-api-management` and all `x-google-mcp-tool` lines from the rendered spec before creating the API config. Use the repository's [local MCP demo](../README.md) to demonstrate MCP separately.

When the demo is over, delete the dedicated resources in dependency order. If you created more API configs, delete those before deleting the API. Cloud Build may also have created an Artifact Registry repository. Review its images and remove only artifacts dedicated to this demo.

```sh
gcloud services api-keys delete "$KEY_ID" --project="$PROJECT_ID"
gcloud api-gateway gateways delete "$GATEWAY_ID" --location="$GATEWAY_REGION" --project="$PROJECT_ID"
gcloud api-gateway api-configs delete "$CONFIG_ID" --api="$API_ID" --project="$PROJECT_ID"
gcloud api-gateway apis delete "$API_ID" --project="$PROJECT_ID"
gcloud run services delete "$SERVICE" --region="$BACKEND_REGION" --project="$PROJECT_ID"
gcloud iam service-accounts delete "$GATEWAY_SA" --project="$PROJECT_ID"
gcloud iam service-accounts delete "$RUNTIME_SA" --project="$PROJECT_ID"
gcloud projects remove-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$BUILD_SA" --role=roles/run.builder
gcloud iam service-accounts delete "$BUILD_SA" --project="$PROJECT_ID"
unset GATEWAY_KEY
```
