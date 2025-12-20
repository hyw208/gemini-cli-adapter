from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather")

@mcp.tool()
def get_weather(city: str) -> str:
    """Get the weather for a city."""
    print(f"DEBUG: get_weather called for {city}")
    return f"The weather in {city} is Sunny, 25°C"

if __name__ == "__main__":
    mcp.run()
