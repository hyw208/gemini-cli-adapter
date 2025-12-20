import subprocess
import json
import sys
import os

def test_mcp_server():
    print("🚀 Launching weather_server.py as a subprocess...")
    process = subprocess.Popen(
        [sys.executable, "weather_server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr, # Let stderr flow through to see debug messages
        text=True,
        bufsize=0 # Unbuffered
    )

    print("📧 Sending JSON-RPC initialize request...")
    # JSON-RPC 2.0 request to list tools (or initialize)
    # FastMCP typically handles 'tools/list' or standard MCP 'initialize'
    # Let's try a simple 'initialize' first as per MCP spec
    
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"}
        }
    }
    
    try:
        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()
        print("⏳ Waiting for response...")
        
        response_line = process.stdout.readline()
        if response_line:
            print(f"✅ Received response: {response_line.strip()}")
            response = json.loads(response_line)
            print("🎉 Server is responding!")
        else:
            print("❌ No response received (process exited or closed stdout).")
            
    except Exception as e:
        print(f"❌ Error during communication: {e}")
    finally:
        print("🛑 Terminating server...")
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()

if __name__ == "__main__":
    test_mcp_server()
