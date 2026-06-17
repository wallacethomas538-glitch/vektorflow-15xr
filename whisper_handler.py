"""
Whisper Handler - Free voice input for VektorFlow
"""

import os
import httpx
import base64
from typing import Dict, Optional

WHISPER_URL = os.environ.get("WHISPER_URL", "https://whisper.onrender.com")

async def transcribe_audio(audio_base64: str) -> Dict:
    """
    Send audio to Whisper server and get transcription.
    """
    try:
        # Decode base64 to bytes
        audio_bytes = base64.b64decode(audio_base64)
        
        # Send to Whisper server
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{WHISPER_URL}/transcribe",
                files={"audio": ("recording.wav", audio_bytes, "audio/wav")}
            )
            if response.status_code == 200:
                data = response.json()
                return {"success": True, "text": data.get("text", "")}
            return {"success": False, "error": f"Whisper API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Whisper request failed: {str(e)}"}

async def transcribe_url(audio_url: str) -> Dict:
    """
    Transcribe audio from a URL.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{WHISPER_URL}/transcribe_url",
                json={"url": audio_url}
            )
            if response.status_code == 200:
                data = response.json()
                return {"success": True, "text": data.get("text", "")}
            return {"success": False, "error": f"Whisper API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Whisper request failed: {str(e)}"}
