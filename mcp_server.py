"""VektorFlow 15XR stdio MCP server for Hermes and other MCP clients."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import httpx
from mcp.server import MCPServer

from agents import run_agent_task
from external_tools import tool_status, brave_search, tavily_search, apify_actor, webscraping_ai

logger = logging.getLogger("vektorflow.mcp")

server = MCPServer(
    "vektorflow",
    title="VektorFlow 15XR",
    description="VektorFlow 15XR agent orchestration with native Gemini generation.",
    instructions="Use VektorFlow agent tools for orchestration; use Gemini only for generative content.",
    version="15.0XR",
)


def _text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _gemini_key() -> str | None:
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = os.getenv(name, "").strip()
        if value and not (value.startswith(") and value.endswith(")):
            return value
    return None


async def _gemini(prompt: str, model: str) -> dict[str, Any]:
    key = _gemini_key()
    if not key:
        return {"success": False, "error": "Gemini is not configured. Set GEMINI_API_KEY in the MCP server environment."}
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", model):
        return {"success": False, "error": "Gemini model name is invalid."}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.7},
                },
            )
        if response.status_code != 200:
            return {"success": False, "error": f"Gemini request failed (HTTP {response.status_code})."}
        data = response.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        answer = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
        return {"success": True, "response": answer} if answer else {
            "success": False, "error": "Gemini returned no text response."
        }
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        return {"success": False, "error": "Gemini request failed before a response was received."}


@server.tool(title="VektorFlow integration status", annotations={"readOnlyHint": True})
def vektorflow_status() -> str:
    return _text({
        "status": "ready",
        "vektorflow_version": "15.0XR",
        "transport": "stdio",
        "gemini": {
            "configured": bool(_gemini_key()),
            "model": os.getenv("VEKTORFLOW_GEMINI_MODEL", "gemini-3.5-flash"),
            "authentication": "GEMINI_API_KEY (preferred) or GOOGLE_API_KEY",
        },
    })


@server.tool(title="Research a product with the VektorFlow team", annotations={"readOnlyHint": True})
async def vektorflow_research_product(
    product_name: str,
    category: str = "general",
    keywords: list[str] | None = None,
) -> str:
    if not product_name.strip():
        raise ValueError("product_name must not be empty")
    result = await run_agent_task(
        "commander@vektorflow.com",
        "Scout",
        f"Research product: {product_name.strip()} in category {category.strip() or 'general'}. Keywords: {keywords or []}",
        {"product_name": product_name.strip(), "category": category.strip() or "general", "keywords": keywords or []},
    )
    return _text(result if isinstance(result, dict) else {"result": result})


@server.tool(title="Run the VektorFlow 15-agent mission", annotations={"readOnlyHint": True})
async def vektorflow_run_mission(
    product_name: str,
    category: str = "general",
    selling_price: float = 39.0,
    product_cost: float | None = None,
    ad_budget: float = 100.0,
    keywords: list[str] | None = None,
    features: list[str] | None = None,
) -> str:
    if not product_name.strip():
        raise ValueError("product_name must not be empty")
    if selling_price < 0 or ad_budget < 0 or (product_cost is not None and product_cost < 0):
        raise ValueError("prices and budget must be non-negative")
    params = {
        "product_name": product_name.strip(),
        "category": category.strip() or "general",
        "selling_price": selling_price,
        "product_cost": product_cost,
        "ad_budget": ad_budget,
        "keywords": keywords or [],
        "features": features or [],
    }
    result = await run_agent_task(
        "commander@vektorflow.com",
        "Vektor",
        f"Run a complete 15-agent launch mission for {product_name.strip()}.",
        params,
    )
    return _text(result if isinstance(result, dict) else {"result": result})


@server.tool(title="Generate content with Gemini", annotations={"readOnlyHint": True})
async def vektorflow_gemini_generate(prompt: str, model: str | None = None) -> str:
    if not prompt.strip():
        raise ValueError("prompt must not be empty")
    return _text(await _gemini(
        prompt.strip(),
        model or os.getenv("VEKTORFLOW_GEMINI_MODEL", "gemini-3.5-flash"),
    ))


def main() -> None:
    logging.basicConfig(
        stream=__import__("sys").stderr,
        level=os.getenv("VEKTORFLOW_LOG_LEVEL", "INFO").upper(),
    )
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
