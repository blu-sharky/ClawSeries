"""
LLM integration - supports OpenAI-compatible APIs and Google Gen AI SDK (Vertex AI).
"""

from __future__ import annotations

import json
import os
from repositories.settings_repo import get_setting


def is_llm_configured() -> bool:
    provider = get_setting("llm_provider", "openai")
    if _is_google_genai(provider):
        return _is_google_genai_available()
    return bool(get_setting("llm_api_key"))


def get_llm_config() -> dict:
    return {
        "provider": get_setting("llm_provider", "openai"),
        "api_key": get_setting("llm_api_key", ""),
        "base_url": get_setting("llm_base_url", "https://api.openai.com/v1"),
        "model": get_setting("llm_model", "gpt-4o"),
    }


def _is_google_genai(provider: str) -> bool:
    return provider == "google_genai"


def _is_google_genai_available() -> bool:
    """Check if Google Gen AI (Vertex AI) is available via ADC or env vars."""
    return bool(os.environ.get("GOOGLE_CLOUD_PROJECT") or get_setting("google_project"))


def _get_google_client():
    """Create a Google Gen AI client using Vertex AI (ADC auth, project/location from env or settings)."""
    from google import genai
    from google.genai import types

    project = get_setting("google_project") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    location = get_setting("google_location") or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

    if not project:
        raise RuntimeError(
            "Google Cloud project not configured. "
            "Set GOOGLE_CLOUD_PROJECT env var or configure in Settings."
        )

    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
    )


async def call_llm(messages: list[dict], temperature: float = 0.7,
                    max_tokens: int = 4096) -> str:
    """
    Call LLM with chat messages. Returns the assistant content.
    Supports OpenAI-compatible and Google Gen AI (Vertex AI) providers.
    """
    config = get_llm_config()
    provider = config["provider"]

    if _is_google_genai(provider):
        return await _call_google_genai(config, messages, temperature, max_tokens)

    if not config["api_key"]:
        raise RuntimeError("LLM API key not configured. Please configure in Settings.")

    return await _call_openai_compatible(config, messages, temperature, max_tokens)


async def _call_openai_compatible(config: dict, messages: list[dict],
                                   temperature: float, max_tokens: int) -> str:
    import httpx
    url = f"{config['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    async with httpx.AsyncClient(timeout=300.0, trust_env=False) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _call_google_genai(config: dict, messages: list[dict],
                              temperature: float, max_tokens: int) -> str:
    import asyncio
    from google.genai import types

    client = _get_google_client()

    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.models.generate_content(
            model=config["model"],
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
    )
    return response.text


async def stream_llm(messages: list[dict], temperature: float = 0.7,
                      max_tokens: int = 4096):
    """
    Stream LLM response. Yields content chunks.
    """
    config = get_llm_config()
    provider = config["provider"]

    if _is_google_genai(provider):
        async for chunk in _stream_google_genai(config, messages, temperature, max_tokens):
            yield chunk
        return

    if not config["api_key"]:
        raise RuntimeError("LLM API key not configured. Please configure in Settings.")

    import httpx
    url = f"{config['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    async with httpx.AsyncClient(timeout=300.0, trust_env=False) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        # For reasoning models (DeepSeek-R1 etc):
                        # reasoning_content = internal thinking, NOT for user display
                        # content = actual output, stream to user
                        content = delta.get("content") or ""
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue


async def _stream_google_genai(config: dict, messages: list[dict],
                                temperature: float, max_tokens: int):
    import asyncio
    from google.genai import types

    client = _get_google_client()

    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    loop = asyncio.get_event_loop()

    def _sync_stream():
        for chunk in client.models.generate_content_stream(
            model=config["model"],
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        ):
            if chunk.text:
                yield chunk.text

    # Run the sync generator in a thread and yield results
    queue = asyncio.Queue()

    def _producer():
        try:
            for text in _sync_stream():
                loop.call_soon_threadsafe(queue.put_nowait, text)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # Sentinel

    loop.run_in_executor(None, _producer)

    while True:
        text = await queue.get()
        if text is None:
            break
        yield text

def test_llm_connection(provider: str, model: str,
                        api_key: str = "", base_url: str = "") -> dict:
    """Test LLM connection."""
    if _is_google_genai(provider):
        return _test_google_genai(model)
    return _test_openai_compatible(api_key, base_url, model)


def _test_google_genai(model: str) -> dict:
    try:
        client = _get_google_client()
        response = client.models.generate_content(
            model=model,
            contents="Reply with: OK",
            config={"max_output_tokens": 10},
        )
        return {"success": True, "message": f"Connected to Vertex AI ({model})"}
    except ImportError:
        return {"success": False, "message": "google-genai not installed. Run: pip install google-genai"}
    except RuntimeError as e:
        return {"success": False, "message": str(e)}
    except Exception as e:
        return {"success": False, "message": f"Vertex AI error: {str(e)}"}


def _test_openai_compatible(api_key: str, base_url: str, model: str) -> dict:
    try:
        import httpx
        url = f"{(base_url or 'https://api.openai.com/v1').rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = httpx.get(url, headers=headers, timeout=10.0, trust_env=False)
        if resp.status_code == 200:
            return {"success": True, "message": f"Connected to {model}"}
        else:
            return {"success": False, "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"success": False, "message": str(e)}
