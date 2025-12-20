import sys
from unittest.mock import MagicMock

# Mock mcp library
mcp_mock = MagicMock()
sys.modules["mcp"] = mcp_mock
sys.modules["mcp.server"] = mcp_mock
sys.modules["mcp.server.fastmcp"] = mcp_mock

# Mock FastMCP class
class MockFastMCP:
    def __init__(self, name):
        pass
    def tool(self):
        def decorator(f):
            return f
        return decorator
    def run(self):
        pass

mcp_mock.FastMCP = MockFastMCP

# Now import the server code
try:
    from weather_server import get_weather
    print(f"Testing execution: {get_weather('Amsterdam')}")
except ImportError as e:
    print(f"Import Error: {e}")
except Exception as e:
    print(f"Execution Error: {e}")
