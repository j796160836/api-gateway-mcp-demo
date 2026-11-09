# 當 API Gateway 遇上 MCP｜訂單 Demo

[English](README.md)

MCP Client → FastMCP Gateway → FastAPI REST API → SQLite

Gateway 啟動時讀取 FastAPI 的 OpenAPI，依操作 ID 的允許清單產生工具。REST API 自行檢查金鑰、主管權限與訂單狀態。

| REST 操作 | 一般 Agent 的 MCP 工具 |
|---|---|
| GET /orders | `list_order` |
| POST /orders | `create_order` 僅供 REST 操作 |
| GET /orders/{order_id} | `get_order` |
| GET /inventory | `list_sku` |
| GET /inventory/{sku} | `check_inventory` |
| POST /shipments | `create_shipment` |
| POST /orders/{order_id}/cancel | `cancel_order` 僅供 REST 主管操作 |

## 本機啟動

使用 Python 3.11+。解壓後進入 `api-gateway-mcp-demo`，安裝依賴。

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

下列每個終端機都從專案目錄執行，並先啟用同一個虛擬環境。Windows PowerShell 使用 `.venv\Scripts\Activate.ps1`。

**終端機 A**

```sh
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

開啟 `http://127.0.0.1:8000/` 可查看服務資訊，或前往 `http://127.0.0.1:8000/docs` 可查看 REST 操作。

REST API 使用 Python 內建的 `sqlite3`。啟動時會在程式旁建立 `db.sqlite3`，訂單、庫存和出貨三張表都空時會加入兩筆訂單和一筆 SKU。重啟後會保留資料。可用 `SQLITE_PATH` 指定其他資料庫檔案，環境變數的預設值集中在 `config.py`。

**終端機 B**

```sh
python gateway.py
```

MCP 使用 Streamable HTTP，端點是 `http://127.0.0.1:9000/mcp`。

**終端機 C**

```sh
python client.py
python approve_shipment.py ORD-1001
```

第一支程式列出五個工具、查詢訂單和 SKU 清單，再查單筆訂單與庫存。執行第二支程式時可指定訂單 ID，確認畫面上的訂單後輸入 `YES` 才會送出出貨申請。省略 ID 時預設使用 `ORD-1001`。

## 建立示範訂單

到 `http://127.0.0.1:8000/docs` 展開 **POST /orders**，點選 **Try it out**，將 `x-api-key` 填為 `demo-rest-secret`（或自行設定的金鑰），並送出以下範例。

```json
{"sku": "SKU-A01", "quantity": 2}
```

成功時會回傳 HTTP 201、系統產生的 `orderId` 和狀態 `PAID`。複製訂單 ID，傳給 `python approve_shipment.py ORDER_ID` 就能示範出貨。庫存會在出貨時扣除。

## 展示取消訂單

以 `ORD-1002` 示範，避免與前一步已申請出貨的訂單混用。

```sh
curl -i http://127.0.0.1:8000/orders/ORD-1002/cancel \
  -H 'x-api-key: demo-rest-secret' \
  -H 'Content-Type: application/json' \
  -d '{"reason":"Customer requested cancellation"}'
```

只有服務金鑰時，REST API 回傳 HTTP 403。加上 `-H 'x-manager-key: demo-manager-secret'` 重試後，回傳 HTTP 200，訂單狀態變為 `CANCELLED` 並保存原因。用下列指令確認仍查得到訂單。

```sh
curl -s http://127.0.0.1:8000/orders/ORD-1002 \
  -H 'x-api-key: demo-rest-secret'
```

已取消的訂單申請出貨、重複取消，或取消已有出貨申請的訂單，都會回傳 HTTP 409。

## 重置範例資料庫

以和 REST 服務相同的 `SQLITE_PATH` 設定執行下列指令。腳本會在同一個交易中清除訂單、庫存和出貨紀錄，再還原範例資料。

```sh
python reset_demo_db.py
```

## 端到端測試

使用預設金鑰啟動兩個服務。若要隔離測試資料，可在啟動 REST 服務及執行重置腳本時，將 `SQLITE_PATH` 設為同一個測試專用檔案（例如 `test-demo.sqlite3`）。每次執行測試前先重置該資料庫。

```sh
python -m unittest -v test_demo
```

此範例使用本機服務與示範金鑰，MCP 端點供本機操作。`google-cloud-openapi-example.yaml` 是原專案附的 Google Cloud 設定示意，本機示範不依賴它。
