"""FastAPI Application - VektorFlow AI System."""

import logging
import os
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles

from src.config import get_settings
from src.serper import SerperClient
from src.pollinations import PollinationsClient
from src.integrations import ShopifyIntegration, WordPressIntegration
from src.analytics import AnalyticsClient
from src.deepseek_client import get_deepseek_client

settings = get_settings()

serper = SerperClient()
pollinations = PollinationsClient()
analytics = AnalyticsClient()
deepseek = get_deepseek_client()

app = FastAPI(
    title="VektorFlow AI System",
    description="AI-powered dropshipping automation system",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/", StaticFiles(directory="static", html=True), name="static")


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "2.0.0", "app": "VektorFlow"}


@app.post("/api/images/generate")
async def generate_image(prompt: str, width: int = 1024, height: int = 1024):
    try:
        analytics.increment_metric("api_calls")
        analytics.increment_metric("images_generated")
        image_bytes, content_type = await pollinations.generate_image(prompt, width, height)
        return Response(content=image_bytes, media_type=content_type)
    except Exception as e:
        analytics.increment_metric("errors")
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")


@app.post("/api/deepseek/generate")
async def deepseek_generate(prompt: str, system_prompt: str = None):
    try:
        analytics.increment_metric("api_calls")
        text = await deepseek.generate_text(prompt, system_prompt)
        return JSONResponse(status_code=200, content={"response": text})
    except Exception as e:
        analytics.increment_metric("errors")
        raise HTTPException(status_code=500, detail=f"DeepSeek generation failed: {str(e)}")


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    logging.error(f"Error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "timestamp": datetime.utcnow().isoformat()}
    )