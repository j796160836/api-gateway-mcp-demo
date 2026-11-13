# 用 Apigee 串接訂單範例

語言：[繁體中文](google-cloud-zh-tw.md) | [English](google-cloud.md)

`MCP 客戶端 → Apigee MCP Discovery Proxy → Apigee REST Proxy → 受 IAM 保護的 Cloud Run → FastAPI → SQLite`

Apigee 受管的 Discovery Proxy 會從 [OpenAPI 規格](order-mcp.yaml) 產生五個工具。REST 客戶端也可從 `/order-demo` 使用同一個後端。兩個入口都使用 Apigee 開發者應用程式的金鑰，REST Proxy 則使用 Google ID token 呼叫 Cloud Run。 [Apigee MCP 快速入門](https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/apigee-mcp-quickstart)

本指南以 `my-awesome-project` 為範例專案，Apigee 環境為 `eval`，環境群組為 `eval-group`。範例中的 Apigee runtime 與 Cloud Run 都位於 `us-east1`。以 `xxx.xxx.xxx.xxx.nip.io` 為主機名稱範例，MCP 路徑為 `/mcp`，REST 訂單路徑為 `/order-demo/orders`。部署時請換成自己的設定。

## 1. 準備 Apigee 與 Cloud Run

使用已佈建的 **Apigee（Google Cloud）** 組織，以及加入環境群組的 **Comprehensive** 環境。環境群組要有可連線的 HTTPS 主機名稱。先在 API hub 建立執行個體並等候啟用，再到 **Settings → Project associations** 確認已關聯 Apigee runtime 專案。啟用 Apigee API 並使用有權匯入與部署 Proxy、管理 API 產品及應用程式的帳號。以下步驟使用該環境群組的主機名稱。 [Apigee 前置條件](https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/apigee-mcp-quickstart#before-you-begin) · [API hub 專案關聯](https://docs.cloud.google.com/apigee/docs/apihub/manage-project-associations)

若使用評估組織，先等 runtime 執行個體成為 `ACTIVE`，並確認評估環境已掛載到該執行個體。要讓本機客戶端連入，可在佈建精靈的 **Access routing** 設定 HTTPS 入口，選用第三方 `nip.io` 測試網域或自有網域。使用 `nip.io` 時由 Google 管理 TLS 憑證。`dns-replaceme.example.com` 是設定過程中的預留主機名稱。 [評估環境入口設定](https://docs.cloud.google.com/apigee/docs/api-platform/get-started/eval-orgs#access-routing)

### 設定外部 DNS 與 HTTPS

- **測試網域。** 保留全域外部 IPv4 位址，用 Private Service Connect NEG 把 Apigee 執行個體接到全域外部 HTTPS 負載平衡器，並以 `<外部 IP>.nip.io` 作為主機名稱和憑證網域。評估精靈也可以自動建立外部路由。 [Apigee 外部 PSC 路由](https://docs.cloud.google.com/apigee/docs/api-platform/get-started/install-cli-eval#step_5_configure_routing)
- **自有網域。** 保留或沿用負載平衡器的全域外部 IPv4 位址。在 DNS 代管平台新增公開 **A 記錄**，例如將 `mcp.example.com` 指到該位址。可在精靈輸入同一主機名稱，或把涵蓋該名稱的憑證掛到既有 HTTPS target proxy。若原網域仍在使用，請保留它的憑證。 [設定外部存取](https://docs.cloud.google.com/apigee/docs/api-platform/get-started/eval-orgs#access-routing) · [Google 管理的 TLS 憑證](https://docs.cloud.google.com/load-balancing/docs/ssl-certificates/google-managed-certs)
- **共通步驟。** 在 runtime 環境所屬的 Apigee 環境群組加入完全相符的主機名稱，確認 DNS 指到負載平衡器的公開 IP 且憑證為 `ACTIVE`。以該主機名稱產生 MCP 規格並部署修訂版，再把客戶端指到相同的主機名稱。 [環境群組](https://docs.cloud.google.com/apigee/docs/api-platform/fundamentals/environments-overview)

在外部 DNS 管理介面（例如 Cloudflare 或網域註冊商），選取 `example.com` 的 DNS 區域，新增名稱 `mcp`、類型 `A`、值為負載平衡器靜態 IP 的記錄。若 DNS 供應商提供代理模式，設定為僅 DNS，讓公開查詢直接回傳負載平衡器 IP。執行 `dig +short mcp.example.com A` 核對。接著用同一個名稱建立 TLS 憑證、設定環境群組，並以新名稱產生和部署 MCP 規格。

若評估 runtime 已存在但尚未設定外部路由，可以用以下指令建立 Demo 專用的全域 HTTPS 負載平衡器和 PSC NEG。請使用 runtime 的實際區域和同區域的子網路。若使用自有網域，保留 IP 後把 `APIGEE_HOST` 改成你的主機名稱，並在建立憑證前發布 A 記錄。

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

請等憑證變為 `ACTIVE`，並確認 HTTPS 可連線，再送出 API 金鑰。負載平衡器、公開 IP 和 PSC 資源可能產生 Google Cloud 費用。

可以沿用既有的私有訂單後端，或只執行 [Google Cloud 指南](../docs/google-cloud-zh-tw.md)中的 Cloud Run 準備及部署步驟。後端使用 [Cloud Run 進入點](../google/cloud_run.py)，在 Cloud Run 驗證 IAM 後帶入應用程式的 REST 金鑰。Cloud Run 上的 SQLite 資料隨執行個體存續。

在 Apigee 專案建立 Proxy 部署服務帳戶。部署者需要對該帳戶具備 `iam.serviceAccounts.actAs`，Apigee runtime 也需要權限替它產生 Google ID token。請依組織的 Google 驗證設定確認權限，再將該帳戶的 `roles/run.invoker` 授予指定的 Cloud Run 服務。 [Apigee Google 驗證設定](https://docs.cloud.google.com/apigee/docs/api-platform/security/google-auth/overview)

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

## 2. 匯入並設定兩個 Proxy

匯入產生的兩個 ZIP，再以服務帳戶部署對應的修訂版。原生 MCP 匯入包的 base path 是 `/mcp`，target 指向該組織的受管 MCP 端點。request PreFlow 會依序執行 [ParsePayload](ParsePayload-MCP.xml) 和 [VerifyAPIKey](rest-proxy/apiproxy/policies/Verify-Order-Key.xml)。規格的主機名稱必須與環境群組完全相符。 [Proxy 部署 API](https://docs.cloud.google.com/apigee/docs/reference/apis/apigee/rest/v1/organizations.environments.apis.revisions.deployments/deploy) · [MCP 產品與驗證政策](https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/manage-mcp-tool-access)

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

到 **Apigee → API proxies** 等兩個修訂版顯示 **Deployed**。若同一 Proxy 已有部署中的修訂版，可用 Console 部署替換版本，或確認 base path 後對該 Proxy 的部署請求加上 `override=true`。 [部署 API Proxy](https://docs.cloud.google.com/apigee/docs/api-platform/deploy/ui-deploy-new)

MCP Discovery Proxy 部署會另外佈建 Google 管理的 MCP runtime。`/mcp` 已有路由、管理 API 顯示 `PROGRESSING` 時，請等狀態變為 `READY`（Console 顯示 **Deployed**）再執行 MCP 測試。如果這段時間收到 `503` 和 `protocol.http.NoResolvedHost`，先查部署狀態。 [Apigee MCP 部署排查](https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/troubleshoot-mcp-deployments)

```sh
gcloud apigee deployments describe --api=order-demo-mcp --environment="$APIGEE_ENV" \
  --organization="$APIGEE_ORG" --project="$APIGEE_ORG" --format='yaml(revision,state,errors)'
```

## 3. 建立 API 產品與開發者應用程式

在 **Apigee → API products** 建立名為 `order-demo` 的內部產品，選擇同一環境。在 **Operations** 為 `order-demo-rest` 新增下列相對於 base path 的路徑。

| 路徑 | 方法 |
|---|---|
| `/orders` | GET、POST |
| `/orders/*` | GET |
| `/inventory` | GET |
| `/inventory/*` | GET |
| `/shipments` | POST |

在 **Payload Operations** 選擇 `order-demo-mcp` 與 **MCP** 協定，加入 **List**，並為 `list_order`、`get_order`、`list_sku`、`check_inventory` 和 `create_shipment` 各加入一個 **Call**。透過 API 設定產品時，對應名稱為 `tools/list` 和 `tools/call/<tool-name>`。工具規格只包含這五項。新增訂單走 REST，主管取消訂單不在這個產品的授權範圍內。 [Apigee API 產品](https://docs.cloud.google.com/apigee/docs/api-platform/publish/create-api-products)

在 **Developers** 建立或選擇開發者，再到 **Apps** 註冊開發者應用程式並加入 `order-demo` 產品。若產品需要審核，先核准該應用程式的存取權。從應用程式憑證取得 **Consumer Key**，供下一步測試。 [註冊應用程式與管理金鑰](https://docs.cloud.google.com/apigee/docs/api-platform/publish/creating-apps-surface-your-api)

也可以使用 [product.json](product.json)，透過管理 API 建立產品與應用程式。若開發者或產品已存在，沿用既有資源並執行剩餘指令即可。

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

要測試既有環境，可到 **Apigee → Apps → order-demo-client → Credentials** 查看 Consumer Key。

## 4. 驗證 REST 與 MCP

在同一個終端機執行下列指令，看到提示時輸入 Consumer Key。帶金鑰的 REST 請求應回傳範例訂單，未帶金鑰的請求應被拒絕。

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

應能看到五個工具及 `ORD-1001` 的查詢結果。若使用 `agy` 等支援自訂標頭的客戶端，把伺服器網址設為 `https://<APIGEE_HOST>/mcp`，並透過 `x-api-key` 傳送 Consumer Key。出貨參數依工具回傳的 schema 填寫，取得人工核准後再呼叫。判斷工具是否成功時，同時查看 HTTP 狀態及 `result.isError`。 [Apigee MCP 錯誤排查](https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/troubleshoot-mcp-deployments)

## 5. 使用 Antigravity CLI（`agy`）

將下列項目合併到 `~/.gemini/config/mcp_config.json` 的 `mcpServers`，保留原有的設定。從 **Apigee → Apps → order-demo-client → Credentials** 複製 Consumer Key，填入 `YOUR_APIGEE_CONSUMER_KEY`。使用自己的部署時，換成環境群組的主機名稱。開啟 `agy` 後輸入 `/mcp`，重新載入設定並確認連線。 [Antigravity MCP](https://antigravity.google/docs/mcp)

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

## 6. 查看 telemetry 與排查問題

- 在 **Apigee API hub → API insights** 將 **API style** 篩選為 **MCP**，再用 **MCP tool name** 選擇工具。可查看 API 效能、錯誤分析及延遲圖表。這些圖表需要啟用 Apigee Analytics 並設定 API hub Insights。 [Apigee MCP 分析](https://docs.cloud.google.com/apigee/docs/api-platform/apigee-mcp/monitor-analyze-mcp-traffic)
- 在 MCP Proxy 的 **Debug** 頁面重送請求，查看 `parsepayload.ParsePayload-MCP.operation`。上述範例應為 `tools/call/get_order`。也可在 REST Proxy 的 Debug 和 Cloud Run 請求日誌檢查後端狀態及延遲。 [Apigee Debug](https://docs.cloud.google.com/apigee/docs/api-platform/debug/trace)
- 若工具清單為空，確認環境群組主機名稱完全相符，並確認應用程式已獲准呼叫產品的 Payload Operations。若 REST target 回傳 401 或 403，先查 Apigee 的 Consumer Key 和產品，再確認 Cloud Run 的部署服務帳戶、`roles/run.invoker` 與 token audience。

可用 Apigee Analytics API 查看這兩個 Proxy 的請求和錯誤計數。請把下列時段換成剛完成測試的 UTC 時間。 [Apigee Analytics API](https://docs.cloud.google.com/apigee/docs/reference/apis/apigee/rest/v1/organizations.environments.stats/get)

```sh
curl -fsS -G -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  --data-urlencode 'select=sum(message_count),sum(error_count)' \
  --data-urlencode 'timeRange=MM/DD/YYYY HH:MM~MM/DD/YYYY HH:MM' \
  --data-urlencode "filter=(apiproxy in 'order-demo-rest','order-demo-mcp')" \
  "https://apigee.googleapis.com/v1/organizations/$APIGEE_ORG/environments/$APIGEE_ENV/stats/apiproxy" | jq .environments
```

## 7. 清除 Demo

先把下方的範例值換成部署時使用的設定。請在同一個終端機執行適用於你部署的步驟。若資源由其他服務共用，只移除 Demo 的設定。

### 取消部署 Proxy 並移除應用程式與 API 產品

先列出組織內這兩個 Proxy 在各環境的部署。

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

在 Demo 環境取消部署兩個 Proxy。已取消部署的 Proxy 可跳過對應指令。

```sh
gcloud apigee apis undeploy --api=order-demo-mcp --environment="$APIGEE_ENV" \
  --organization="$APIGEE_ORG" --project="$APIGEE_ORG"
gcloud apigee apis undeploy --api=order-demo-rest --environment="$APIGEE_ENV" \
  --organization="$APIGEE_ORG" --project="$APIGEE_ORG"
```

使用以下指令刪除 Demo 專用的開發者應用程式。其憑證會一併非同步移除。共用的應用程式則到 **Apigee → Apps → Credentials** 解除與 Demo 產品的關聯。 [刪除開發者應用程式](https://docs.cloud.google.com/apigee/docs/reference/apis/apigee/rest/v1/organizations.developers.apps/delete)

```sh
curl -fsS -o /dev/null -X DELETE -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$APIGEE_API/developers/$DEVELOPER_EMAIL/apps/$APP"
```

確認 API 產品已無關聯的應用程式後即可刪除。刪除 Proxy 前，先確認該 Proxy 已在所有環境取消部署。 [刪除 API Proxy](https://docs.cloud.google.com/apigee/docs/api-platform/develop/ui-delete-proxy)

```sh
curl -fsS -o /dev/null -X DELETE -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$APIGEE_API/apiproducts/$PRODUCT" &&
gcloud apigee apis delete order-demo-mcp --organization="$APIGEE_ORG" --project="$APIGEE_ORG" &&
gcloud apigee apis delete order-demo-rest --organization="$APIGEE_ORG" --project="$APIGEE_ORG"
```

若開發者也是為 Demo 建立，且已沒有其他應用程式，可一併刪除。 [刪除開發者](https://docs.cloud.google.com/apigee/docs/reference/apis/apigee/rest/v1/organizations.developers/delete)

```sh
curl -fsS -o /dev/null -X DELETE -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$APIGEE_API/developers/$DEVELOPER_EMAIL"
```

### 移除外部主機名稱和專用負載平衡器

環境群組還有其他主機名稱時，下列指令只移除 Demo 的名稱。如果找不到該名稱，或它是群組中唯一的名稱，指令會跳過更新。若要保留只設定一個名稱的環境群組，請在 **Apigee → Management → Environments → Environment groups** 設定替代名稱。

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

若使用自有網域，先在 DNS 供應商移除 A 記錄，再釋放靜態 IP。若由 Cloud DNS 代管，請填入記錄所在的專案和受管區域。使用 `nip.io` 時會自動解析。

```sh
DNS_PROJECT='my-dns-project'
DNS_ZONE='example-com'
gcloud dns record-sets delete mcp.example.com. --type=A --zone="$DNS_ZONE" --project="$DNS_PROJECT"
```

以下指令適用於步驟 1 建立的專用 PSC 和負載平衡器資源。若某項資源已刪除，可從下一條指令繼續。若負載平衡器由其他服務共用，請從既有設定移除 Demo 的主機路由及專用憑證。 [Apigee 網路資源清理](https://docs.cloud.google.com/apigee/docs/api-platform/system-administration/delete-organization#follow_up_organizations_provisioned_without_vpc_peering)

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

### 移除 Cloud Run 的權限綁定與 Demo 服務帳戶

若部署用服務帳戶是 Demo 專用，先移除它在 Cloud Run 服務上的 Invoker 權限，再刪除帳戶。若 Cloud Run 位於不同專案，請另外設定 `BACKEND_PROJECT`。

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

若也為 Demo 建了專用的 Cloud Run 服務，可另外刪除。

```sh
gcloud run services delete "$BACKEND_SERVICE" --region="$BACKEND_REGION" --project="$BACKEND_PROJECT"
```

### 選用步驟：移除專用評估組織

只有整個 Apigee 評估組織都是為了 Demo 建立，而且確定要退役時，才執行下列指令。此指令會刪除組織及其內容。如需移除 API Hub，或清理由設定精靈建立的額外網路資源，請依對應流程操作。 [刪除 Apigee 組織](https://docs.cloud.google.com/apigee/docs/api-platform/system-administration/delete-organization) · [移除 API Hub](https://docs.cloud.google.com/apigee/docs/apihub/deprovision)

```sh
curl -fsS -X DELETE -H "Authorization: Bearer $(gcloud auth print-access-token)" "$APIGEE_API"
```
