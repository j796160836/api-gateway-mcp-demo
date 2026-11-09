"""Local teaching adapter: OpenAPI -> MCP. NOT Google Cloud API Gateway.

Auto-generates tools from the existing FastAPI OpenAPI document.
No hand-written per-endpoint MCP tools.
"""
import asyncio

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import MCP_HOST, REST_API_KEY, REST_URL
from demo_mcp import FastMCP


async def main():
    try:
        async with httpx.AsyncClient(timeout=15) as spec_client:
            resp = await spec_client.get(f"{REST_URL}/openapi.json")
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SystemExit(
            f"REST API returned HTTP {exc.response.status_code} for /openapi.json. "
            "Check that REST_URL points to the demo REST service."
        ) from None
    except (httpx.RequestError, httpx.InvalidURL):
        raise SystemExit(
            "Could not connect to the REST API. Check REST_URL and start the REST service "
            "with python -m uvicorn api:app."
        ) from None

    try:
        spec = resp.json()
    except ValueError:
        raise SystemExit("The REST API returned invalid JSON for /openapi.json.") from None
    if not isinstance(spec, dict) or not isinstance(spec.get("paths"), dict):
        raise SystemExit("The REST API returned an invalid OpenAPI document.")

    # Publish only explicitly approved operations and keep service credentials internal.
    allowlist = {"list_order", "get_order", "list_sku", "check_inventory", "create_shipment"}
    paths = {}
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            if operation.get("operationId") in allowlist:
                operation["parameters"] = [
                    parameter for parameter in operation.get("parameters", [])
                    if parameter.get("in") != "header"
                ]
                paths.setdefault(path, {})[method] = operation
    spec["paths"] = paths
    async with httpx.AsyncClient(
        base_url=REST_URL,
        headers={"x-api-key": REST_API_KEY},
        timeout=15,
    ) as api_client:
        mcp = FastMCP.from_openapi(
            openapi_spec=spec,
            client=api_client,
            name="Order API MCP Gateway (local demo)",
        )

        @mcp.custom_route("/", methods=["GET"])
        async def service_info(_request: Request):
            return JSONResponse(
                {"service": mcp.name, "transport": "Streamable HTTP", "mcp": "/mcp"}
            )

        await mcp.run_async(transport="http", host=MCP_HOST, port=9000, path="/mcp")

if __name__ == "__main__":
    asyncio.run(main())
