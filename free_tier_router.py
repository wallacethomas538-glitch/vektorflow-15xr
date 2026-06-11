import httpx
import os
from typing import Dict

class FreeTierRouter:
    def __init__(self):
        self.providers = [
            {"name": "groq", "url": "https://api.groq.com/openai/v1/chat/completions", "key": os.environ.get("GROQ_API_KEY")},
            {"name": "huggingface", "url": "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3", "key": os.environ.get("HF_API_KEY")},
        ]
    
    async def call(self, prompt: str, fallback: bool = True) -> Dict:
        for provider in self.providers:
            if not provider["key"]:
                continue
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        provider["url"],
                        headers={"Authorization": f"Bearer {provider['key']}"},
                        json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 500}
                    )
                    if resp.status_code == 200:
                        return {"provider": provider["name"], "success": True, "data": resp.json()}
            except Exception:
                continue
        return {"success": False, "error": "All providers failed"}
