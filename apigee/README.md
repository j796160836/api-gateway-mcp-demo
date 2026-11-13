# Apigee for the order demo

Language: [繁體中文](google-cloud-zh-tw.md) | [English](google-cloud.md)

`MCP client → Apigee MCP Discovery Proxy → Apigee REST proxy → IAM-protected Cloud Run → FastAPI → SQLite`

The Apigee-managed Discovery Proxy generates five tools from [the OpenAPI spec](order-mcp.yaml). The REST proxy is also available to REST clients at `/order-demo`. An Apigee developer app key authorizes both entry points. The REST proxy uses a Google ID token to reach Cloud Run. [Apigee MCP quickstart](https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/apigee-mcp-quickstart)

In this example, project `my-awesome-project` uses Apigee environment `eval` and environment group `eval-group`. Both the Apigee runtime and Cloud Run are in `us-east1`. With the placeholder hostname `xxx.xxx.xxx.xxx.nip.io`, the MCP path is `/mcp` and the REST orders path is `/order-demo/orders`. Replace these example values with your own deployment settings.

## 1. Prepare Apigee and Cloud Run

Use a provisioned **Apigee (Google Cloud)** organization with a **Comprehensive** environment attached to an environment group with a reachable HTTPS hostname. Provision an API hub instance and wait for it to become active. Verify the Apigee runtime project under **Settings → Project associations**. Enable the Apigee API and use an account with permission to import and deploy proxies and manage API products and apps. Use the environment-group hostname throughout this guide. [Apigee prerequisites](https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/apigee-mcp-quickstart#before-you-begin) · [API hub project associations](https://docs.cloud.google.com/apigee/docs/apihub/manage-project-associations)

For an evaluation organization, wait for the runtime instance to become `ACTIVE` and confirm that the evaluation environment is attached to it. In the provisioning wizard, use **Access routing** to give local clients an HTTPS entry point. The wizard supports a test hostname resolved by the third-party `nip.io` DNS service or a domain you control. With `nip.io`, Google manages the TLS certificate. A `dns-replaceme.example.com` hostname is a setup placeholder. [Evaluation access routing](https://docs.cloud.google.com/apigee/docs/api-platform/get-started/eval-orgs#access-routing)

### Configure external DNS and HTTPS

- **Test hostname.** Reserve a global external IPv4 address, connect the Apigee instance through a Private Service Connect NEG to a global external HTTPS load balancer, and use `<external-ip>.nip.io` as the hostname and certificate domain. The evaluation wizard can create the external routing for you. [Apigee external routing with PSC](https://docs.cloud.google.com/apigee/docs/api-platform/get-started/install-cli-eval#step_5_configure_routing)
- **Your own hostname.** Reserve or reuse the load balancer's global external IPv4 address. At your DNS provider, create a public **A** record for the full hostname, such as `mcp.example.com`, pointing to that address. In the wizard enter the same hostname, or attach a certificate for it to your existing HTTPS target proxy. Keep the existing certificate attached if its hostname is still in use. [Configure external access](https://docs.cloud.google.com/apigee/docs/api-platform/get-started/eval-orgs#access-routing) · [Google-managed TLS certificates](https://docs.cloud.google.com/load-balancing/docs/ssl-certificates/google-managed-certs)
- **Both options.** Add the exact hostname to the Apigee environment group attached to the runtime environment. Check that DNS resolves to the load balancer's public IP and the certificate is `ACTIVE`. Render the MCP spec with that hostname, deploy the revision, then use the same hostname in the client URL. [Environment groups](https://docs.cloud.google.com/apigee/docs/api-platform/fundamentals/environments-overview)

In your DNS provider’s dashboard, open the `example.com` zone and add an `A` record named `mcp` with the load balancer’s static IPv4 address as its value. If the provider offers a proxy mode, use DNS-only mode so public DNS returns the load balancer’s IP directly. Verify the result with `dig +short mcp.example.com A`. Use the same name for the TLS certificate, the environment group, and the rendered MCP spec.

For an existing evaluation runtime without external routing, these CLI steps create a dedicated global HTTPS load balancer and PSC NEG. Use the actual runtime region and a subnet in that region. For your own domain, set `APIGEE_HOST` to your chosen hostname after reserving the IP and publish its A record before creating the certificate.

```sh
APIGEE_ORG='my-awesome-project'
RUNTIME_REGION='us-east1'
INSTANCE='eval-instance'
ENV_GROUP='eval-group'
NETWORK='default'
SUBNET='default'
INGRESS='order-apigee-demo'

APIGEE_API="https://apigee.googleapis.com/v1/organizations/$APIGEE_ORG"
ACCESS_TOKEN="$(gcloud auth print-access-token)"
TARGET="$(curl -fsS -H "Authorization: Bearer $ACCESS_TOKEN" \
  "$APIGEE_API/instances/$INSTANCE" | jq -er 'select(.state == "ACTIVE") | .serviceAttachment')"

gcloud compute network-endpoint-groups create "$INGRESS-neg" \
  --network-endpoint-type=private-service-connect --psc-target-service="$TARGET" \
  --network="$NETWORK" --subnet="$SUBNET" --region="$RUNTIME_REGION" --project="$APIGEE_ORG"
gcloud compute addresses create "$INGRESS-ip" --global --ip-version=IPV4 --project="$APIGEE_ORG"
EXTERNAL_IP="$(gcloud compute addresses describe "$INGRESS-ip" \
  --global --project="$APIGEE_ORG" --format='value(address)')"
APIGEE_HOST="${APIGEE_HOST:-$EXTERNAL_IP.nip.io}"

gcloud compute backend-services create "$INGRESS-backend" \
  --load-balancing-scheme=EXTERNAL_MANAGED --protocol=HTTPS --global --project="$APIGEE_ORG"
gcloud compute backend-services add-backend "$INGRESS-backend" \
  --network-endpoint-group="$INGRESS-neg" --network-endpoint-group-region="$RUNTIME_REGION" \
  --global --project="$APIGEE_ORG"
gcloud compute url-maps create "$INGRESS-map" \
  --default-service="$INGRESS-backend" --global --project="$APIGEE_ORG"
gcloud compute ssl-certificates create "$INGRESS-cert" \
  --domains="$APIGEE_HOST" --global --project="$APIGEE_ORG"
gcloud compute target-https-proxies create "$INGRESS-https" \
  --url-map="$INGRESS-map" --ssl-certificates="$INGRESS-cert" --global --project="$APIGEE_ORG"
gcloud compute forwarding-rules create "$INGRESS-https" \
  --load-balancing-scheme=EXTERNAL_MANAGED --network-tier=PREMIUM --address="$INGRESS-ip" \
  --target-https-proxy="$INGRESS-https" --ports=443 --global --project="$APIGEE_ORG"

curl -fsS -H "Authorization: Bearer $ACCESS_TOKEN" "$APIGEE_API/envgroups/$ENV_GROUP" \
  | jq --arg host "$APIGEE_HOST" '{hostnames: ([.hostnames[] | select((. == "dns-replaceme.example.com" or endswith(".dns-replaceme.example.com")) | not)] + [$host] | unique)}' \
  | curl -fsS -X PATCH -H "Authorization: Bearer $ACCESS_TOKEN" \
      -H 'Content-Type: application/json' --data-binary @- \
      "$APIGEE_API/envgroups/$ENV_GROUP?updateMask=hostnames"
unset ACCESS_TOKEN
dig +short "$APIGEE_HOST"
gcloud compute ssl-certificates describe "$INGRESS-cert" \
  --global --project="$APIGEE_ORG" --format='yaml(managed.status,managed.domainStatus)'
```

Wait for the certificate to become `ACTIVE` and verify that HTTPS works before sending credentials. The load balancer, public IP, and PSC resources can incur Cloud charges.

Reuse a private deployment of the order REST backend, or follow only the Cloud Run setup and deployment steps in the [Google Cloud guide](../docs/google-cloud.md). The backend uses the [Cloud Run entry point](../google/cloud_run.py), which supplies the application's REST key after Cloud Run verifies IAM. Cloud Run's SQLite data is scoped to the running instance.

Create a proxy deployment service account in the Apigee project. The deployer needs `iam.serviceAccounts.actAs` on that identity, and the Apigee runtime needs permission to mint its Google ID tokens. Use the Apigee Google authentication setup for your organization to verify those permissions. Grant the proxy identity `roles/run.invoker` on the specific Cloud Run service. [Apigee Google authentication](https://docs.cloud.google.com/apigee/docs/api-platform/security/google-auth/overview)

```sh
APIGEE_HOST="${APIGEE_HOST:-api.example.com}"
APIGEE_ORG="${APIGEE_ORG:-my-awesome-project}"
APIGEE_ENV='eval'
APIGEE_SA="order-demo-apigee@$APIGEE_ORG.iam.gserviceaccount.com"
BACKEND_PROJECT="$APIGEE_ORG"
BACKEND_REGION='us-east1'
BACKEND_SERVICE='order-demo-rest'

gcloud iam service-accounts create order-demo-apigee --project="$APIGEE_ORG"
PROJECT_NUMBER="$(gcloud projects describe "$APIGEE_ORG" --format='value(projectNumber)')"
gcloud iam service-accounts add-iam-policy-binding "$APIGEE_SA" \
  --project="$APIGEE_ORG" --role=roles/iam.serviceAccountTokenCreator \
  --member="serviceAccount:service-$PROJECT_NUMBER@gcp-sa-apigee.iam.gserviceaccount.com"

gcloud run services add-iam-policy-binding "$BACKEND_SERVICE" \
  --project="$BACKEND_PROJECT" --region="$BACKEND_REGION" \
  --member="serviceAccount:$APIGEE_SA" --role=roles/run.invoker

CLOUD_RUN_URL="$(gcloud run services describe "$BACKEND_SERVICE" \
  --project="$BACKEND_PROJECT" --region="$BACKEND_REGION" --format='value(status.url)')"
OUTPUT_DIR="$(mktemp -d)"
python3 apigee/render.py --organization "$APIGEE_ORG" --hostname "$APIGEE_HOST" \
  --cloud-run-url "$CLOUD_RUN_URL" --output "$OUTPUT_DIR"
printf 'Upload files from %s\n' "$OUTPUT_DIR"
```

## 2. Import and configure both proxies

Import the two rendered bundles, then deploy their revisions with the service account selected. The native MCP bundle uses the `/mcp` base path and targets the organization's managed MCP endpoint. Its request PreFlow runs [ParsePayload](ParsePayload-MCP.xml) and [VerifyAPIKey](rest-proxy/apiproxy/policies/Verify-Order-Key.xml) in that order. The spec hostname must match the environment group exactly. [Proxy deployment API](https://docs.cloud.google.com/apigee/docs/reference/apis/apigee/rest/v1/organizations.environments.apis.revisions.deployments/deploy) · [MCP product and security policies](https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/manage-mcp-tool-access)

```sh
for PROXY in order-demo-rest order-demo-mcp; do
  REVISION="$(gcloud apigee apis import "$PROXY" --organization="$APIGEE_ORG" \
    --project="$APIGEE_ORG" --from-bundle="$OUTPUT_DIR/$PROXY.zip" \
    --format='value(revision)')" || break
  curl -fsS -X POST \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    "https://apigee.googleapis.com/v1/organizations/$APIGEE_ORG/environments/$APIGEE_ENV/apis/$PROXY/revisions/$REVISION/deployments?serviceAccount=$APIGEE_SA" \
    || break
done
```

Check **Apigee → API proxies** and wait for both revisions to show **Deployed**. If a prior revision of the same proxy is deployed, use the Console to deploy the replacement revision or add `override=true` to that proxy's deployment request after confirming the base path. [Deploy an API proxy](https://docs.cloud.google.com/apigee/docs/api-platform/deploy/ui-deploy-new)

Deploying the MCP Discovery Proxy also provisions a Google-managed MCP runtime. The `/mcp` route can be installed while the management API still reports `PROGRESSING`. Wait for `READY` (shown as **Deployed** in the console) before running the MCP tests. If you receive HTTP `503` with `protocol.http.NoResolvedHost` during provisioning, check the deployment status. [Apigee MCP deployment troubleshooting](https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/troubleshoot-mcp-deployments)

```sh
gcloud apigee deployments describe --api=order-demo-mcp --environment="$APIGEE_ENV" \
  --organization="$APIGEE_ORG" --project="$APIGEE_ORG" --format='yaml(revision,state,errors)'
```

## 3. Create the API product and developer app

In **Apigee → API products**, create an internal product named `order-demo` and select the same environment. In **Operations**, add these paths relative to the base path of `order-demo-rest`.

| Path | Methods |
|---|---|
| `/orders` | GET, POST |
| `/orders/*` | GET |
| `/inventory` | GET |
| `/inventory/*` | GET |
| `/shipments` | POST |

In **Payload Operations**, select proxy `order-demo-mcp` and protocol **MCP**. Add **List** and **Call** entries for `list_order`, `get_order`, `list_sku`, `check_inventory`, and `create_shipment`. If you configure the product through the API, the operation names are `tools/list` and `tools/call/<tool-name>`. The tool spec includes only those five operations. Order creation is available through REST. Manager cancellation stays outside this product. [Apigee API products](https://docs.cloud.google.com/apigee/docs/api-platform/publish/create-api-products)

In **Developers**, create or select a developer. In **Apps**, register an app for that developer and attach the `order-demo` product. Approve the product for the app if required. Copy the app credential's **Consumer Key** for the test. [Register apps and manage keys](https://docs.cloud.google.com/apigee/docs/api-platform/publish/creating-apps-surface-your-api)

You can also create the product and app through the management API using [product.json](product.json). If the developer or product already exists, reuse it and run only the remaining commands.

```sh
APIGEE_API="https://apigee.googleapis.com/v1/organizations/$APIGEE_ORG"
ACCESS_TOKEN="$(gcloud auth print-access-token)"
DEVELOPER_EMAIL='order-demo@example.com'
APP='order-demo-client'

jq --arg env "$APIGEE_ENV" '.environments = [$env]' apigee/product.json \
  | curl -fsS -H "Authorization: Bearer $ACCESS_TOKEN" -H 'Content-Type: application/json' \
      --data-binary @- "$APIGEE_API/apiproducts" | jq '{name}'
jq -n --arg email "$DEVELOPER_EMAIL" \
  '{email:$email,firstName:"Order",lastName:"Demo",userName:"order-demo"}' \
  | curl -fsS -H "Authorization: Bearer $ACCESS_TOKEN" -H 'Content-Type: application/json' \
      --data-binary @- "$APIGEE_API/developers" | jq '{email}'
jq -n --arg name "$APP" '{name:$name,apiProducts:["order-demo"]}' \
  | curl -fsS -H "Authorization: Bearer $ACCESS_TOKEN" -H 'Content-Type: application/json' \
      --data-binary @- "$APIGEE_API/developers/$DEVELOPER_EMAIL/apps" | jq '{name,status}'
unset ACCESS_TOKEN
```

To check a running environment, use the existing app's Consumer Key from **Apigee → Apps → order-demo-client → Credentials**.

## 4. Verify REST and MCP

Enter the Consumer Key at the prompt and run these commands in the same shell. The authenticated REST request should return the sample orders. The request without a key should be rejected.

```sh
BASE="https://$APIGEE_HOST"
printf 'Apigee Consumer Key: '
IFS= read -rs APIGEE_KEY
printf '\n'

curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/order-demo/orders"
curl -fsS "$BASE/order-demo/orders" -H "x-api-key: $APIGEE_KEY" | jq .

apigee_mcp() {
  curl -fsS "$BASE/mcp" -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -H 'MCP-Protocol-Version: 2025-11-25' -H "x-api-key: $APIGEE_KEY" -d "$1"
}

apigee_mcp '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"order-demo","version":"1"}}}' \
  | jq -e '.result.protocolVersion == "2025-11-25"'
apigee_mcp '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
apigee_mcp '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | jq -er '.result.tools[].name'
apigee_mcp '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_order","arguments":{"order_id":"ORD-1001"}}}' \
  | jq -e '.result | select(.isError != true)'
```

You should see five tools and the `ORD-1001` result. In a client that supports custom headers, such as `agy`, use `https://<APIGEE_HOST>/mcp` and send the Consumer Key as `x-api-key`. Use the returned tool schema for shipment arguments and approve the shipment before calling it. Check `result.isError` as well as HTTP status. [Apigee MCP errors](https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/troubleshoot-mcp-deployments)

## 5. Connect with Antigravity CLI (`agy`)

Merge this entry into `mcpServers` in `~/.gemini/config/mcp_config.json`. Copy the Consumer Key from **Apigee → Apps → order-demo-client → Credentials** and replace `YOUR_APIGEE_CONSUMER_KEY`. For your own deployment, use your environment-group hostname. Start `agy`, enter `/mcp`, and reload the server configuration to check the connection. [Antigravity MCP](https://antigravity.google/docs/mcp)

```json
{
  "mcpServers": {
    "order-demo-apigee": {
      "serverUrl": "https://xxx.xxx.xxx.xxx.nip.io/mcp",
      "headers": {
        "x-api-key": "YOUR_APIGEE_CONSUMER_KEY"
      }
    }
  }
}
```

## 6. Inspect telemetry and troubleshoot

- In **Apigee API hub → API insights**, filter **API style** to **MCP** and select a tool in **MCP tool name**. Use API performance, error analysis, and latency dashboards. This requires Apigee Analytics and a configured API hub Insights integration. [Apigee MCP analytics](https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/monitor-analyze-mcp-traffic)
- In the MCP proxy's **Debug** view, repeat a request and inspect `parsepayload.ParsePayload-MCP.operation`. For the sample call it should be `tools/call/get_order`. Follow the corresponding request in the REST proxy and Cloud Run request logs to inspect target status and latency. [Apigee Debug](https://docs.cloud.google.com/apigee/docs/api-platform/debug/trace)
- If discovery is empty, check the exact environment-group hostname and the app's approved payload operations. If the REST target returns 401 or 403, verify the Consumer Key and API product on Apigee, then the deployment service account, `roles/run.invoker`, and token audience on Cloud Run.

Use the Apigee Analytics API to check request and error counts for the two proxies. Replace the example UTC range with the time of your test. [Apigee Analytics API](https://docs.cloud.google.com/apigee/docs/reference/apis/apigee/rest/v1/organizations.environments.stats/get)

```sh
curl -fsS -G -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  --data-urlencode 'select=sum(message_count),sum(error_count)' \
  --data-urlencode 'timeRange=MM/DD/YYYY HH:MM~MM/DD/YYYY HH:MM' \
  --data-urlencode "filter=(apiproxy in 'order-demo-rest','order-demo-mcp')" \
  "https://apigee.googleapis.com/v1/organizations/$APIGEE_ORG/environments/$APIGEE_ENV/stats/apiproxy" | jq .environments
```

## 7. Clean up the demo

Replace the example values in this section with your deployment settings. Use the same shell for these commands and run only the steps that apply to your resources. Keep shared resources and remove only the demo's configuration from them.

### Undeploy the proxies and remove the app and API product

List deployments for both proxies across the organization before removing them.

```sh
APIGEE_ORG='my-awesome-project'
APIGEE_ENV='eval'
APIGEE_API="https://apigee.googleapis.com/v1/organizations/$APIGEE_ORG"
DEVELOPER_EMAIL='order-demo@example.com'
APP='order-demo-client'
PRODUCT='order-demo'

for PROXY in order-demo-mcp order-demo-rest; do
  gcloud apigee deployments list --api="$PROXY" \
    --organization="$APIGEE_ORG" --project="$APIGEE_ORG" || break
done
```

Undeploy each proxy from the demo environment. Skip a command if that proxy is already undeployed there.

```sh
gcloud apigee apis undeploy --api=order-demo-mcp --environment="$APIGEE_ENV" \
  --organization="$APIGEE_ORG" --project="$APIGEE_ORG"
gcloud apigee apis undeploy --api=order-demo-rest --environment="$APIGEE_ENV" \
  --organization="$APIGEE_ORG" --project="$APIGEE_ORG"
```

Use this command to delete the dedicated demo app. Its credentials are removed asynchronously. For a shared app, unlink the demo product under **Apigee → Apps → Credentials**. [Delete a developer app](https://docs.cloud.google.com/apigee/docs/reference/apis/apigee/rest/v1/organizations.developers.apps/delete)

```sh
curl -fsS -o /dev/null -X DELETE -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$APIGEE_API/developers/$DEVELOPER_EMAIL/apps/$APP"
```

Delete the API product after all apps are disassociated from it. Before deleting a proxy, confirm it is undeployed in every environment. [Delete an API proxy](https://docs.cloud.google.com/apigee/docs/api-platform/develop/ui-delete-proxy)

```sh
curl -fsS -o /dev/null -X DELETE -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$APIGEE_API/apiproducts/$PRODUCT" &&
gcloud apigee apis delete order-demo-mcp --organization="$APIGEE_ORG" --project="$APIGEE_ORG" &&
gcloud apigee apis delete order-demo-rest --organization="$APIGEE_ORG" --project="$APIGEE_ORG"
```

If you created the developer for the demo and it has no other apps, you can also delete it. [Delete a developer](https://docs.cloud.google.com/apigee/docs/reference/apis/apigee/rest/v1/organizations.developers/delete)

```sh
curl -fsS -o /dev/null -X DELETE -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$APIGEE_API/developers/$DEVELOPER_EMAIL"
```

### Remove the external hostname and dedicated load balancer

If the environment group has other hostnames, this update removes just the demo hostname. The command skips the update if the name is absent or is the group's only hostname. To keep the group when retiring its only hostname, configure a replacement hostname in **Apigee → Management → Environments → Environment groups**.

```sh
ENV_GROUP='eval-group'
APIGEE_HOST='xxx.xxx.xxx.xxx.nip.io'
ACCESS_TOKEN="$(gcloud auth print-access-token)"

HOST_UPDATE="$(curl -fsS -H "Authorization: Bearer $ACCESS_TOKEN" "$APIGEE_API/envgroups/$ENV_GROUP" |
  jq -ce --arg host "$APIGEE_HOST" \
    '.hostnames | select(index($host)) | map(select(. != $host)) | select(length > 0) | {hostnames: .}')" &&
curl -fsS -X PATCH -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' --data "$HOST_UPDATE" \
  "$APIGEE_API/envgroups/$ENV_GROUP?updateMask=hostnames"
unset ACCESS_TOKEN
```

For a custom hostname, remove the A record at your DNS provider before releasing the static IP. For Cloud DNS, set the project and managed zone that contain the record. With `nip.io`, DNS resolution is automatic.

```sh
DNS_PROJECT='my-dns-project'
DNS_ZONE='example-com'
gcloud dns record-sets delete mcp.example.com. --type=A --zone="$DNS_ZONE" --project="$DNS_PROJECT"
```

Use the following commands for the dedicated PSC and load balancer resources created in step 1. If one has already been deleted, resume from the next command. For a shared load balancer, remove the demo's hostname routing and any dedicated certificate through its existing configuration. [Apigee networking cleanup](https://docs.cloud.google.com/apigee/docs/api-platform/system-administration/delete-organization#follow_up_organizations_provisioned_without_vpc_peering)

```sh
INGRESS='order-apigee-demo'
RUNTIME_REGION='us-east1'

gcloud compute forwarding-rules delete "$INGRESS-https" --global --project="$APIGEE_ORG" &&
gcloud compute target-https-proxies delete "$INGRESS-https" --global --project="$APIGEE_ORG" &&
gcloud compute url-maps delete "$INGRESS-map" --global --project="$APIGEE_ORG" &&
gcloud compute backend-services delete "$INGRESS-backend" --global --project="$APIGEE_ORG" &&
gcloud compute network-endpoint-groups delete "$INGRESS-neg" \
  --region="$RUNTIME_REGION" --project="$APIGEE_ORG" &&
gcloud compute ssl-certificates delete "$INGRESS-cert" --global --project="$APIGEE_ORG" &&
gcloud compute addresses delete "$INGRESS-ip" --global --project="$APIGEE_ORG"
```

### Remove the Cloud Run binding and demo service account

If the deployment service account was created exclusively for this demo, remove its Cloud Run Invoker binding and then delete the account. Set `BACKEND_PROJECT` separately if Cloud Run is hosted in another project.

```sh
APIGEE_SA="order-demo-apigee@$APIGEE_ORG.iam.gserviceaccount.com"
BACKEND_PROJECT="$APIGEE_ORG"
BACKEND_REGION='us-east1'
BACKEND_SERVICE='order-demo-rest'

gcloud run services remove-iam-policy-binding "$BACKEND_SERVICE" \
  --project="$BACKEND_PROJECT" --region="$BACKEND_REGION" \
  --member="serviceAccount:$APIGEE_SA" --role=roles/run.invoker &&
gcloud iam service-accounts delete "$APIGEE_SA" --project="$APIGEE_ORG"
```

If you also created a dedicated Cloud Run service for this demo, delete it separately.

```sh
gcloud run services delete "$BACKEND_SERVICE" --region="$BACKEND_REGION" --project="$BACKEND_PROJECT"
```

### Optional removal of a dedicated evaluation organization

If the entire Apigee evaluation organization was created for this demo and you want to retire it, the following request deletes the organization and its contents. For API Hub deprovisioning or additional network resources created by the setup wizard, follow the corresponding procedure. [Delete an Apigee organization](https://docs.cloud.google.com/apigee/docs/api-platform/system-administration/delete-organization) · [Deprovision API Hub](https://docs.cloud.google.com/apigee/docs/apihub/deprovision)

```sh
curl -fsS -X DELETE -H "Authorization: Bearer $(gcloud auth print-access-token)" "$APIGEE_API"
```
