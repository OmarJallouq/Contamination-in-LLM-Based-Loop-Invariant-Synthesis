import os

import requests
import json

response = requests.get(
  url="https://openrouter.ai/api/v1/key",
  headers={
    "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"
  }
)

print(json.dumps(response.json(), indent=2))