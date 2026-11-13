# 用 Google Cloud API Gateway 串接訂單範例

語言：[繁體中文](google-cloud-zh-tw.md) | [English](google-cloud.md)

`MCP 或 REST 客戶端 → Google Cloud API Gateway → 受 IAM 保護的 Cloud Run → FastAPI → SQLite`

API Gateway 依照 [OpenAPI 範本](../google-cloud-openapi-example.yaml) 產生遠端 `/mcp`，由 Cloud Run 執行 REST 服務。Google 的原生 MCP 目前是**公開預覽**，支援透過 HTTP POST 探索與呼叫短時間執行的工具。本範例公開 `list_order`、`get_order`、`list_sku`、`check_inventory` 和 `create_shipment`。新增訂單走 REST，主管取消訂單保留在 Gateway 公開路由之外。 [MCP 概覽](https://docs.cloud.google.com/api-gateway/docs/mcp-overview) · [MCP 設定](https://docs.cloud.google.com/api-gateway/docs/mcp-configure)

請使用範例資料。Cloud Run 把 SQLite 存在容器的可寫檔案系統，新執行個體或修訂版本可能會從初始資料開始。下方的執行個體數量限制也無法提供資料持久性。若要保存訂單或部署多個副本，可將服務改接 Cloud SQL 等持久資料庫。 [Cloud Run 檔案系統](https://docs.cloud.google.com/run/docs/container-contract) · [執行個體數量上限](https://docs.cloud.google.com/run/docs/configuring/max-instances)

## 1. 準備 Google Cloud 專案

從專案根目錄用 Bash 或 Zsh 執行下列指令。請先安裝最新版 `gcloud` CLI、`curl` 和 `jq`，並使用已啟用帳單的 Google Cloud 專案。執行者需要啟用 API、部署 Cloud Run 與 API Gateway、管理服務帳戶及 Cloud Run IAM 政策，以及建立 API 金鑰的權限。執行者也需要代表建置、執行和 Gateway 服務帳戶行事的權限。從原始碼部署時，建置帳戶需要 `roles/run.builder` 或等效權限。這些操作可能產生費用。 [Cloud Run 從原始碼部署及 IAM](https://docs.cloud.google.com/run/docs/deploying-source-code) · [API Gateway 設定](https://docs.cloud.google.com/api-gateway/docs/get-started-cloud-run)

```sh
gcloud version
gcloud run deploy --help | grep -E 'build-service-account|invoker-iam-check'
```

部署前請確認說明輸出包含這兩個旗標。若缺少任一個，請依原本的安裝方式更新 CLI，再重新檢查。若在同一個專案接續部署，可沿用已建立的服務帳戶。 [安裝或更新 Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk)

```sh
gcloud auth login
PROJECT_ID='your-google-cloud-project-id'
BACKEND_REGION='us-east1'
GATEWAY_REGION='us-east1'
SERVICE='order-demo-rest'
API_ID='order-demo-api'
CONFIG_ID='order-demo-east-v1'
GATEWAY_ID='order-demo-gateway'
KEY_ID='order-demo-client'
BUILD_SA="order-demo-build@${PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME_SA="order-demo-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
GATEWAY_SA="order-demo-gateway@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud billing projects describe "$PROJECT_ID" --format='value(billingEnabled)'
```

確認計費查詢回傳 `True` 再繼續。如果回傳 `False`，請先連結有效的計費帳戶。Cloud Build 可能先成功上傳原始碼，直到將映像推送至 Artifact Registry 時才因計費問題中斷。 [確認專案計費狀態](https://docs.cloud.google.com/billing/docs/how-to/verify-billing-enabled)

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

範例將 Cloud Run 和 API Gateway 都放在 `us-east1`。Cloud Run 可以用 `us-west1`，但 API Gateway 的支援區域清單未包含該區。本範例的執行帳戶無需額外的 Google Cloud 應用程式角色，Gateway 帳戶則只會取得呼叫這個 Cloud Run 服務的權限。 [API Gateway 支援區域](https://docs.cloud.google.com/api-gateway/docs/deployment-model#choose_a_google_cloud_region) · [建置服務帳戶](https://docs.cloud.google.com/run/docs/configuring/services/build-service-account)

### 設定 gcloud 的預設專案

如果經常操作這個專案，可以在目前使用的 gcloud 設定檔中設定預設值。`core/project` 指定資源所在的專案，`billing/quota_project` 指定 API 請求使用哪個專案的配額。這項設定不會變更專案連結的 Cloud Billing 帳戶。 [gcloud 設定](https://docs.cloud.google.com/sdk/gcloud/reference/config/set) · [設定配額專案](https://docs.cloud.google.com/docs/quotas/set-quota-project)

```sh
gcloud config set core/project "$PROJECT_ID"
gcloud config set billing/quota_project "$PROJECT_ID"
gcloud config get-value core/project
gcloud config get-value billing/quota_project
```

預設值符合目標專案時，就可以省略 `--project` 和 `--billing-project`。文件仍在需要的地方明確指定旗標，方便使用不同的設定檔。若要移除預設值，可執行 `gcloud config unset core/project` 或 `gcloud config unset billing/quota_project`。

## 2. 把 REST 後端部署到 Cloud Run

先將必要的程式複製到暫存目錄，避免把整個工作目錄上傳。Cloud Run 的入口程式在 IAM 放行後，將請求的金鑰標頭換成現有 REST 服務使用的金鑰。請啟用 Cloud Run Invoker IAM 檢查，並避免授予公開呼叫權限。Google API 金鑰由公開的 Gateway 驗證。 [Cloud Run 呼叫權限](https://docs.cloud.google.com/run/docs/authenticating/public)

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

最後一個請求沒有附 Cloud Run IAM 憑證，應該會被拒絕。如果收到 HTTP 200，請檢查 Cloud Run 的 IAM 設定。

### 無法授予 Cloud Build 角色時，改用本機建置

若無法修改專案的 IAM 政策，可用 Docker 在本機建置，再用有權限建立存放區及推送映像的帳號上傳至 Artifact Registry。略過建置服務帳戶及其 `roles/run.builder` 綁定。先依上方指令準備來源檔案，再以這組指令取代從原始碼部署的指令。完成後，接續設定 Cloud Run Invoker 和測試匿名請求。 [在本機建置 Cloud Run 映像](https://docs.cloud.google.com/run/docs/building/containers#build_locally_and_push_using_docker)

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

## 3. 部署 API Gateway 並限制客戶端金鑰

如果 API 尚不存在，第一次建立 API config 時會一併建立。範本會把 Cloud Run 的正式服務 URL 設為後端位址和 Gateway 簽發 ID token 時使用的 audience。REST 和 MCP 工具呼叫都需要 Google API 金鑰，工具探索也使用相同金鑰保護。MCP 初始化依協定設計可公開呼叫。 [OpenAPI 擴充設定](https://docs.cloud.google.com/api-gateway/docs/oasv3-extensions) · [MCP 驗證規則](https://docs.cloud.google.com/api-gateway/docs/mcp-configure#authentication_model)

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

等 Gateway 啟用且受管服務和金鑰設定生效後再測試。建立金鑰的指令會隱藏輸出，因為 CLI 可能在作業結果中印出金鑰。如果建立失敗，請在私人終端機排查。請勿將金鑰提交到 Git。本範例使用 API 金鑰共享存取範例資料。若服務涉及敏感資料或需要區分使用者權限，Google 建議使用更強的身分驗證。 [Gateway API 金鑰](https://docs.cloud.google.com/api-gateway/docs/authenticate-api-keys) · [用 CLI 建立並限制金鑰](https://docs.cloud.google.com/sdk/gcloud/reference/services/api-keys/create)

### 查找既有部署的 Key ID

用顯示名稱篩選 Demo 金鑰。下列指令只列出 ID 和顯示名稱。

```sh
gcloud services api-keys list \
  --project="$PROJECT_ID" --billing-project="$PROJECT_ID" \
  --filter='displayName="Order demo gateway"' \
  --format='table(name.basename():label=KEY_ID,displayName)'
```

將 `KEY_ID` 欄位的值傳給 `gcloud services api-keys get-key-string`。目前部署在 `my-awesome-project` 的 Demo 使用 `order-demo-client-v2`。如果有多把金鑰使用相同顯示名稱，可用 `gcloud services api-keys describe KEY_ID` 檢查 API 限制，選擇只允許呼叫該 Gateway 受管服務的金鑰。 [取得金鑰值](https://docs.cloud.google.com/sdk/gcloud/reference/services/api-keys/get-key-string)

## 4. 測試 REST 並建立示範訂單

```sh
curl -sS -o /dev/null -w '%{http_code}\n' "$GATEWAY_URL/orders"
curl -fsS -H "x-api-key: $GATEWAY_KEY" "$GATEWAY_URL/orders" | jq .

ORDER_ID="$(curl -fsS -X POST "$GATEWAY_URL/orders" \
  -H "x-api-key: $GATEWAY_KEY" -H 'Content-Type: application/json' \
  -d '{"sku":"SKU-A01","quantity":2}' | jq -er '.orderId')"
printf 'New order: %s\n' "$ORDER_ID"
```

匿名查詢應被拒絕。附上金鑰後，在新執行個體上可查到預載的訂單。成功新增訂單時會回傳 HTTP 201，訂單狀態為 `PAID`。出貨前先確認庫存。

## 5. 測試原生 MCP

等 Gateway 狀態變為 `ACTIVE`，再把 JSON-RPC 請求送到公開網址。佈建期間，REST 可能已開始回應，但 `POST /mcp` 仍回傳 404。`notifications/initialized` 正常會回傳 HTTP 202，後續請求要使用握手協商出的版本。Google Gateway 的 MCP 工具把 REST 路徑和查詢參數放在 `arguments` 的第一層，而 REST 請求本文放在 `arguments.body`。 [MCP 握手與參數格式](https://docs.cloud.google.com/api-gateway/docs/mcp-configure#verify-mcp-support)

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

應該會列出前述五個工具。若要驗證未授權的探索，使用相同的協定和內容標頭重送 `tools/list`，並省略 `x-api-key`。Gateway 應拒絕回傳工具清單。確認訂單和庫存後，再明確核准出貨。工具說明本身不會強制人工審核，持有 API 金鑰的客戶端可以呼叫出貨操作。

```sh
printf 'Ship order %s? Type YES to approve: ' "$ORDER_ID"
read -r approval
if [ "$approval" = YES ]; then
  mcp_post "$(jq -nc --arg id "$ORDER_ID" \
    '{jsonrpc:"2.0",id:5,method:"tools/call",params:{name:"create_shipment",arguments:{body:{order_id:$id}}}}')" \
    | jq -e '.result | select(.isError != true)'
fi
```

成功時會回傳出貨紀錄。再次呼叫 `check_inventory` 可以確認庫存減少兩件。專案內的 FastMCP 本機腳本使用不同的出貨參數格式。示範 Google 受管的 MCP 端點時請使用上述請求。

## 6. 用 Google Antigravity CLI（`agy`）連線

在 macOS 上，執行下列指令把受限制的 API 金鑰複製到剪貼簿。這組指令使用已部署在 `my-awesome-project` 的 Demo 金鑰。若使用自己的部署，請換成對應的專案 ID 和金鑰 ID。 [Google Cloud CLI 取得金鑰](https://docs.cloud.google.com/sdk/gcloud/reference/services/api-keys/get-key-string)

```sh
gcloud services api-keys get-key-string order-demo-client-v2 \
  --project=my-awesome-project \
  --billing-project=my-awesome-project \
  --format='value(keyString)' --quiet | pbcopy
```

開啟或建立 `~/.gemini/config/mcp_config.json`。在 `mcpServers` 下加入 `order-demo`，保留原有設定，並用剪貼簿裡的金鑰取代 `YOUR_GATEWAY_API_KEY`。若使用自己的部署，請改用該 Gateway 網址並加上 `/mcp`。全域設定檔位於 Git 儲存庫之外。 [Antigravity MCP 設定](https://antigravity.google/docs/mcp)

```json
{
  "mcpServers": {
    "order-demo": {
      "serverUrl": "https://order-demo-gateway-5p0lq3db.ue.gateway.dev/mcp",
      "headers": {
        "x-api-key": "YOUR_GATEWAY_API_KEY"
      }
    }
  }
}
```

啟動 `agy` 後輸入 `/mcp`，查看連線狀態或重新載入設定。確認 `order-demo` 已連線後，可用下列提示測試唯讀工具。 [Antigravity MCP 管理介面](https://antigravity.google/docs/mcp)

> 請用 `order-demo` 的 `get_order` 查詢 `ORD-1001`，再用 `check_inventory` 查詢該訂單 SKU 的可用庫存。

## 7. 用 Cloud Logging 和 Cloud Monitoring 觀察流量

API Gateway 會自動記錄請求日誌與指標。先執行上方的 REST 和 MCP 測試產生流量，再用有 Cloud Logging 讀取權限的帳戶，從專案根目錄執行以下指令。腳本會列出最近一小時內最多 30 筆 Gateway 請求，顯示 HTTP 狀態、延遲、操作名稱，以及日誌提供的追蹤 ID。 [監控 API Gateway](https://docs.cloud.google.com/api-gateway/docs/monitoring)

```sh
bash google/gateway-telemetry.sh "$PROJECT_ID" "$GATEWAY_ID"
```

在 **Logging → Logs Explorer** 選取該 Gateway 的 API Gateway 資源。若只想看 MCP 流量，可在請求日誌的篩選條件加上 `httpRequest.requestUrl:"/mcp"`。JSON-RPC 工具呼叫失敗仍可能回傳 HTTP 200，請查看 MCP 回應中的 `error` 或 `result.isError`。 [MCP 觀測與錯誤處理](https://docs.cloud.google.com/api-gateway/docs/mcp-configure#observability)

在 **Monitoring → Metrics Explorer** 選擇 **API Gateway → Proxy → Request Count**（`apigateway.googleapis.com/proxy/request_count`），依 Gateway ID 和區域篩選，再依 HTTP 狀態碼類別分組查看流量和錯誤。延遲可看 API **Overview** 頁籤的圖表，或查看單筆請求日誌的 `httpRequest.latency`。指標可能要等幾分鐘才會出現。 [API Gateway 指標與日誌](https://docs.cloud.google.com/api-gateway/docs/monitoring)

## 排查問題、更新及清理資源

- **Gateway 拒絕金鑰。** 確認已在金鑰所屬專案啟用受管服務，金鑰的 API 限制指向該服務，並且請求帶有 `x-api-key`。新設定可能需要時間生效。
- **後端回傳 HTTP 401 或 403。** 檢查 Gateway config 的後端服務帳戶、Cloud Run 服務上的 `roles/run.invoker` 綁定，以及範本產生的 `jwtAudience`。匿名請求 Cloud Run 仍應被拒絕。
- **找不到路由或工具。** 確認目前啟用的 API config，並使用 `POST /mcp` 呼叫 MCP。更新時先建立新 ID 的 config，再執行 `gcloud api-gateway gateways update "$GATEWAY_ID" --api="$API_ID" --api-config="$NEW_CONFIG_ID" --location="$GATEWAY_REGION" --project="$PROJECT_ID"`。 [Gateway 疑難排解](https://docs.cloud.google.com/api-gateway/docs/troubleshoot) · [更新 MCP 工具](https://docs.cloud.google.com/api-gateway/docs/mcp-configure#update-exposed-mcp-tools)
- **無法使用預覽功能。** 如果要先部署 REST Gateway，請在產生的 OpenAPI 檔案移除 `x-google-api-management` 下的 `mcp` 區塊和所有 `x-google-mcp-tool` 設定，再建立 API config。MCP 可用專案的[本機方式](../README-zh-tw.md)另外展示。

示範完成後，可依順序刪除專用資源。若建立過多份 API config，請在刪除 API 前先刪除其餘 config。Cloud Build 也可能建立 Artifact Registry 存放區，請確認其中的映像後，只清理本次示範專用的資源。

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
