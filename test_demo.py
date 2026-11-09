"""End-to-end checks against freshly started local REST and MCP servers."""
import asyncio
import unittest

import httpx
from demo_mcp import Client

from config import MANAGER_KEY, MCP_URL, REST_API_KEY, REST_URL


class DemoTest(unittest.TestCase):
    def test_demo(self):
        asyncio.run(self.run_scenarios())

    async def run_scenarios(self):
        headers = {"x-api-key": REST_API_KEY}
        manager = {**headers, "x-manager-key": MANAGER_KEY}
        reason = {"reason": "Customer requested cancellation"}
        async with (
            httpx.AsyncClient(base_url=REST_URL) as rest,
            Client(MCP_URL) as mcp,
        ):
            home = await rest.get("/")
            self.assertEqual(home.status_code, 200)
            self.assertEqual(home.json()["docs"], "/docs")

            tools = await mcp.list_tools()
            self.assertEqual(
                {tool.name for tool in tools},
                {"list_order", "get_order", "list_sku", "check_inventory", "create_shipment"},
            )
            orders = await mcp.call_tool("list_order", {})
            self.assertEqual(
                [order["orderId"] for order in orders.structured_content["orders"]],
                ["ORD-1001", "ORD-1002"],
            )
            skus = await mcp.call_tool("list_sku", {})
            self.assertEqual(skus.structured_content["skus"], [{"sku": "SKU-A01", "available": 8}])
            order = await mcp.call_tool("get_order", {"order_id": "ORD-1001"})
            self.assertEqual(order.structured_content["status"], "PAID")
            stock = await mcp.call_tool("check_inventory", {"sku": "SKU-A01"})
            self.assertEqual(stock.structured_content["available"], 8)
            shipment = await mcp.call_tool("create_shipment", {"order_id": "ORD-1001"})
            self.assertEqual(shipment.structured_content["status"], "CREATED")

            duplicate = await rest.post("/shipments", headers=headers, json={"order_id": "ORD-1001"})
            self.assertEqual(duplicate.status_code, 409)
            skus = await mcp.call_tool("list_sku", {})
            self.assertEqual(skus.structured_content["skus"][0]["available"], 6)

            shipped = await rest.post("/orders/ORD-1001/cancel", headers=manager, json=reason)
            self.assertEqual(shipped.status_code, 409)

            path = "/orders/ORD-1002/cancel"
            denied = await rest.post(path, headers=headers, json=reason)
            self.assertEqual(denied.status_code, 403)
            blank = await rest.post(path, headers=manager, json={"reason": "  "})
            self.assertEqual(blank.status_code, 422)
            cancelled = await rest.post(path, headers=manager, json=reason)
            self.assertEqual(cancelled.status_code, 200)
            retained = await mcp.call_tool("get_order", {"order_id": "ORD-1002"})
            self.assertEqual(retained.structured_content["status"], "CANCELLED")
            self.assertEqual(retained.structured_content["cancellationReason"], reason["reason"])
            repeat = await rest.post(path, headers=manager, json=reason)
            self.assertEqual(repeat.status_code, 409)
            blocked = await rest.post("/shipments", headers=headers, json={"order_id": "ORD-1002"})
            self.assertEqual(blocked.status_code, 409)


if __name__ == "__main__":
    unittest.main()
