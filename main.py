from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx
import yaml
from typing import Optional, Dict, Any
import os

app = FastAPI(title="VektorFlow BYOK Gateway")

with open("config/models.yaml") as f:
    config = yaml.safe_load(f)

PROVIDERS = {}
for provider_name, provider_info in config["providers"].items():
    for model in provider_info["models"]:
        PROVIDERS[model] = provider_info["base_url"]

class ChatRequest(BaseModel):
    model: str
    messages: list
    stream: Optional[bool] = False
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatRequest,
    authorization: str = Header(..., alias="Authorization")
):
    if request.model not in PROVIDERS:
        raise HTTPException(404, f"Model {request.model} not found")
    
    api_key = authorization.replace("Bearer ", "")
    target_base = PROVIDERS[request.model]
    url = f"{target_base}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        if request.stream:
            return StreamingResponse(
                _stream_request(client, "POST", url, headers, request.dict()),
                media_type="text/event-stream"
            )
        else:
            resp = await client.post(url, json=request.dict(), headers=headers)
            return resp.json()

async def _stream_request(client, method, url, headers, json_data):
    async with client.stream(method, url, headers=headers, json=json_data) as resp:
        async for chunk in resp.aiter_bytes():
            yield chunk

@app.get("/v1/models")
async def list_models(authorization: Optional[str] = Header(None)):
    return {
        "object": "list",
        "data": [{"id": m, "object": "model"} for m in PROVIDERS.keys()]
    }