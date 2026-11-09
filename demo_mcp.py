"""FastMCP imports and client error handling for the demo."""
import asyncio
import warnings

import httpx
from authlib.deprecate import AuthlibDeprecationWarning

from config import MCP_URL

# FastMCP 2.x triggers these upstream warnings while importing its auth providers.
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=r"authlib\.jose module is deprecated",
        category=AuthlibDeprecationWarning,
        module=r"fastmcp\.server\.auth\.providers\.jwt$",
    )
    warnings.filterwarnings(
        "ignore",
        message=r"The httpx module is deprecated",
        category=AuthlibDeprecationWarning,
        module=r"authlib\.integrations\.httpx_client\.assertion_client$",
    )
    from fastmcp import Client as Client
    from fastmcp import FastMCP as FastMCP
    from fastmcp.exceptions import McpError, ToolError


def run_client(main):
    try:
        asyncio.run(main())
    except (McpError, ToolError) as exc:
        raise SystemExit(f"MCP request failed: {exc}") from None
    except (httpx.HTTPError, TimeoutError, RuntimeError):
        raise SystemExit(
            f"MCP connection failed ({MCP_URL}). "
            "Check that the REST API is running, then start the gateway with python gateway.py."
        ) from None
