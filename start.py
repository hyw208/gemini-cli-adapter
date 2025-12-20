#!/usr/bin/env python3
import os
import sys
import subprocess
from dotenv import load_dotenv

def main():
    # Load environment variables from .env file
    load_dotenv()
    
    print("🚀 Starting Gemini-LiteLLM Adapter...")
    print("----------------------------------------")
    
    # Check for API keys
    keys = [
        "GEMINI_API_KEY", 
        "OPENAI_API_KEY", 
        "DEEPSEEK_API_KEY", 
        "ANTHROPIC_API_KEY", 
        "GROQ_API_KEY", 
        "TOGETHER_API_KEY"
    ]
    
    found_keys = [key for key in keys if os.getenv(key)]
    
    if not found_keys:
        print("❌ No API keys found in environment or .env file!")
        print("   Please edit .env and add at least one API key.")
        sys.exit(1)
        
    print(f"✅ Found API keys for: {', '.join([k.split('_')[0] for k in found_keys])}")
    
    # Path to the adapter script
    adapter_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adapter.py")
    
    # Run the adapter
    # We use os.execv to replace the current process with the adapter process.
    # This ensures that the PID tracked by manage_adapter.sh is the actual adapter.
    cmd_args = [sys.executable, "-u", adapter_script]
    
    print(f"🚀 Launching adapter: {' '.join(cmd_args)}")
    try:
        os.execv(sys.executable, cmd_args)
    except Exception as e:
        print(f"\n❌ Error launching adapter: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
