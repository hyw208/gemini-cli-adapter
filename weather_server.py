from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather")

@mcp.tool()
def get_weather(city: str) -> str:
    """Get the weather for a city."""
    import sys
    sys.stderr.write(f"DEBUG: get_weather called for {city}\n")
    return f"The weather in {city} is Sunny, 25°C"

if __name__ == "__main__":
    mcp.run()
