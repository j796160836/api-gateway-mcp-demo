"""Environment settings for the local demo."""
import os
from pathlib import Path

REST_URL = os.getenv("REST_URL", "http://127.0.0.1:8000")
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:9000/mcp")
REST_API_KEY = os.getenv("REST_API_KEY", "demo-rest-secret")
MANAGER_KEY = os.getenv("MANAGER_KEY", "demo-manager-secret")
SQLITE_PATH = Path(os.getenv("SQLITE_PATH", str(Path(__file__).with_name("db.sqlite3"))))
