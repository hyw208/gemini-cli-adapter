#!/usr/bin/env python3
import os
import litellm
from dotenv import load_dotenv

load_dotenv()

# Enable debug mode
litellm.set_verbose = True

token = os.getenv('GITHUB_API_KEY')
print(f"GITHUB_API_KEY found: {bool(token)}")
print(f"Token length: {len(token) if token else 0}")

try:
    response = litellm.completion(
        model="github/gpt-4o",  # Try a different GitHub model
        messages=[{"role": "user", "content": "Say hello in 3 words"}],
        api_key=token  # Explicitly pass the token
    )
    print("\nSuccess!")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"\nError: {type(e).__name__}: {e}")
