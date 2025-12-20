import sys
print("Starting import...", flush=True)
try:
    from weather_server import get_weather
    print("Imported.", flush=True)
    print(get_weather("Amsterdam"))
except Exception as e:
    print(f"Error: {e}", flush=True)
