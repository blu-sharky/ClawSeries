"""
Image generation integration - multi-provider support.
Providers: siliconflow, openai, google_genai, stability, custom
"""

from __future__ import annotations

import base64
import os
import requests
from repositories.settings_repo import get_setting


IMAGE_NO_TEXT_OVERLAY_SUFFIX = " No text overlay, no title text, no large centered text, no subtitles, no captions, no logo, no watermark."

def _get_provider() -> str:
    return get_setting("image_provider", "openai")


def is_image_configured() -> bool:
    provider = _get_provider()
    if provider == "google_genai":
        return bool(os.environ.get("GOOGLE_CLOUD_PROJECT") or get_setting("google_project"))
    return bool(get_setting("image_api_key"))


def is_image_demo_mode() -> bool:
    """Check if image demo mode is enabled (returns placeholder images)."""
    return get_setting("image_demo_mode") == "true"


def get_image_config() -> dict:
    return {
        "provider": _get_provider(),
        "model": get_setting("image_model", "dall-e-3"),
        "api_key": get_setting("image_api_key", ""),
        "base_url": get_setting("image_base_url", ""),
        "image_size": get_setting("image_size", "1024x1024"),
        "num_inference_steps": int(get_setting("num_inference_steps", "20")),
        "guidance_scale": float(get_setting("guidance_scale", "7.5")),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_image(prompt: str, output_path: str,
                         reference_images: list[str] | None = None,
                         aspect_ratio: str = "1:1",
                         max_retries: int | None = None) -> str:
    """Generate an image. Routes to the configured provider.

    max_retries=None or <=0 means unlimited retries.
    Retries transient/provider failures with backoff until success or a non-retryable error occurs.
    """
    import asyncio
    import time
    from pathlib import Path

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Demo mode: create a placeholder image
    if is_image_demo_mode():
        _create_demo_image(output_path, text=prompt[:30])
        return output_path

    config = get_image_config()
    provider = config["provider"]
    model = config.get("model", "?")
    timeout_sec = 300  # 5 minutes max per attempt
    effective_prompt = f"{prompt.rstrip().rstrip('.')}" + IMAGE_NO_TEXT_OVERLAY_SUFFIX

    retry_label = "unbounded" if not max_retries or max_retries <= 0 else str(max_retries)
    print(f"[ImageGen] START provider={provider} model={model} aspect={aspect_ratio} refs={len(reference_images or [])} prompt_len={len(effective_prompt)} retries={retry_label}")

    attempt = 0
    while True:
        attempt += 1
        t0 = time.monotonic()
        last_error = None
        try:
            if provider == "siliconflow":
                image_bytes = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, lambda: _siliconflow_generate(effective_prompt, config)
                    ),
                    timeout=timeout_sec,
                )
            elif provider == "google_genai":
                image_bytes = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, lambda p=effective_prompt, c=config, ar=aspect_ratio, ri=reference_images: _google_generate(p, c, ar, ri)
                    ),
                    timeout=timeout_sec,
                )
            elif provider == "openai":
                image_bytes = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, lambda: _openai_generate(effective_prompt, config)
                    ),
                    timeout=timeout_sec,
                )
            else:
                image_bytes = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, lambda: _openai_generate(effective_prompt, config)
                    ),
                    timeout=timeout_sec,
                )

            elapsed = time.monotonic() - t0
            print(f"[ImageGen] DONE provider={provider} attempt={attempt} elapsed={elapsed:.1f}s size={len(image_bytes) if image_bytes else 0}")

            if not image_bytes:
                raise RuntimeError(f"Image generation returned no data (provider: {provider})")

            with open(output_path, "wb") as f:
                f.write(image_bytes)

            return output_path

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - t0
            last_error = f"Timed out after {elapsed:.0f}s"
        except Exception as e:
            elapsed = time.monotonic() - t0
            last_error = str(e)

        lower_error = last_error.lower()
        if any(token in lower_error for token in ("api key not configured", "authentication failed", "invalid api key", "permission denied")) or "401" in last_error or "403" in last_error:
            print(f"[ImageGen] NON-RETRYABLE failure on attempt={attempt}: {last_error[:200]}")
            raise RuntimeError(last_error)

        if max_retries and max_retries > 0 and attempt >= max_retries:
            print(f"[ImageGen] FAILED after {attempt} attempts. Last error: {last_error[:200]}")
            raise RuntimeError(f"Image generation failed after {attempt} attempts: {last_error}")

        is_rate_limit = "429" in last_error or "resource_exhausted" in lower_error or "rate" in lower_error
        delay = min(300, 30 * (2 ** min(attempt - 1, 3))) if is_rate_limit else min(30, 10 * attempt)
        print(f"[ImageGen] RETRY attempt={attempt} failed: {last_error[:120]} — waiting {delay}s before retry...")
        await asyncio.sleep(delay)


# ---------------------------------------------------------------------------
# SiliconFlow
# ---------------------------------------------------------------------------

def _siliconflow_generate(prompt: str, config: dict) -> bytes:
    """Generate image via SiliconFlow API (OpenAI-compatible /images/generations)."""
    import time
    print(f"[ImageGen] SiliconFlow model={config.get('model', '?')} size={config.get('image_size', '?')}")
    t0 = time.monotonic()
    url = config.get("base_url") or "https://api.siliconflow.cn/v1"
    if not url.endswith("/images/generations"):
        url = url.rstrip("/") + "/images/generations"

    payload = {
        "model": config["model"],
        "prompt": prompt,
        "image_size": config["image_size"],
        "batch_size": 1,
        "num_inference_steps": config["num_inference_steps"],
        "guidance_scale": config["guidance_scale"],
    }

    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()

    # Response contains images list with b64_json or url
    images = data.get("images", data.get("data", []))
    if not images:
        raise RuntimeError("SiliconFlow returned no images")

    first = images[0]
    if "b64_json" in first:
        return base64.b64decode(first["b64_json"])
    if "url" in first:
        img_resp = requests.get(first["url"], timeout=60)
        img_resp.raise_for_status()
        return img_resp.content

    raise RuntimeError("SiliconFlow response missing image data")


# ---------------------------------------------------------------------------
# OpenAI (DALL-E)
# ---------------------------------------------------------------------------

def _openai_generate(prompt: str, config: dict) -> bytes:
    """Generate image via OpenAI-compatible API."""
    import time
    print(f"[ImageGen] OpenAI model={config.get('model', '?')} size={config.get('image_size', '?')}")
    t0 = time.monotonic()
    url = config.get("base_url") or "https://api.openai.com/v1"
    if not url.endswith("/images/generations"):
        url = url.rstrip("/") + "/images/generations"

    payload = {
        "model": config["model"],
        "prompt": prompt,
        "n": 1,
        "size": config["image_size"],
        "response_format": "b64_json",
    }

    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()

    images = data.get("data", [])
    if not images:
        raise RuntimeError("OpenAI returned no images")

    if "b64_json" in images[0]:
        return base64.b64decode(images[0]["b64_json"])
    if "url" in images[0]:
        img_resp = requests.get(images[0]["url"], timeout=60)
        img_resp.raise_for_status()
        return img_resp.content

    raise RuntimeError("OpenAI response missing image data")


# ---------------------------------------------------------------------------
# Google GenAI (Gemini / Imagen)
# ---------------------------------------------------------------------------

def _resolve_google_location(model: str | None = None) -> str:
    configured = get_setting("google_location") or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    if model and model.endswith("-image-preview") and configured != "global":
        print(f"[ImageGen] overriding Google location {configured} -> global for preview image model {model}")
        return "global"
    return configured


def _get_google_client(model: str | None = None):
    from google import genai

    project = get_setting("google_project") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    location = _resolve_google_location(model)

    if not project:
        raise RuntimeError(
            "Google Cloud project not configured. "
            "Set GOOGLE_CLOUD_PROJECT env var or configure in Settings."
        )

    return genai.Client(vertexai=True, project=project, location=location)


def _google_generate(prompt: str, config: dict, aspect_ratio: str = "1:1", reference_images: list[str] | None = None) -> bytes:
    import time
    from google.genai import types
    from pathlib import Path

    model = config["model"]
    client = _get_google_client(model)

    ar_map = {"1:1": "1:1", "16:9": "16:9", "9:16": "9:16", "3:4": "3:4", "4:3": "4:3"}
    # Unsupported ratios map to closest supported: 2:1 -> 16:9, 1:2 -> 9:16
    imagen_ar = ar_map.get(aspect_ratio, "16:9" if aspect_ratio not in ar_map else aspect_ratio)
    print(f"[ImageGen] Google GenAI model={model} aspect={aspect_ratio}->{imagen_ar} refs={len(reference_images or [])}")

    parts = [types.Part(text=prompt)]

    # Add reference images if provided
    if reference_images:
        for img_path in reference_images[:3]:  # Max 3 reference images
            p = Path(img_path)
            if p.exists():
                img_data = p.read_bytes()
                ext = p.suffix.lstrip('.').lower()
                mime_type = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'webp': 'image/webp'}.get(ext, 'image/png')
                parts.append(types.Part(
                    inline_data=types.Blob(data=img_data, mime_type=mime_type)
                ))

    contents = [types.Content(role="user", parts=parts)]
    gen_config = types.GenerateContentConfig(
        temperature=1,
        top_p=0.95,
        max_output_tokens=8192,
        response_modalities=["IMAGE"],
        safety_settings=[
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
        ],
        image_config=types.ImageConfig(
            aspect_ratio=imagen_ar,
            image_size="1K",
            output_mime_type="image/png",
        ),
    )

    t0 = time.monotonic()
    response = client.models.generate_content(model=model, contents=contents, config=gen_config)
    response_parts = getattr(response, "parts", None) or []
    if response_parts:
        for part in response_parts:
            if hasattr(part, "inline_data") and part.inline_data:
                print(f"[ImageGen] Google got image data after {time.monotonic()-t0:.1f}s")
                return part.inline_data.data

    if hasattr(response, "candidates") and response.candidates:
        for candidate in response.candidates:
            if hasattr(candidate, "content") and candidate.content:
                for part in candidate.content.parts or []:
                    if hasattr(part, "inline_data") and part.inline_data:
                        print(f"[ImageGen] Google got image data after {time.monotonic()-t0:.1f}s via candidates")
                        return part.inline_data.data

    print(f"[ImageGen] Google response ended with no image after {time.monotonic()-t0:.1f}s")
    return None


# ---------------------------------------------------------------------------
# Demo mode
# ---------------------------------------------------------------------------

def _create_demo_image(output_path: str, text: str = "Demo") -> None:
    """Create a placeholder PNG for demo/testing."""
    from pathlib import Path
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Try PIL first for a nicer placeholder
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (512, 512), color=(45, 55, 72))
        draw = ImageDraw.Draw(img)
        # Truncate text to fit
        display_text = text[:40] if text else "Demo"
        draw.text((20, 240), display_text, fill=(200, 200, 200))
        img.save(output_path, "PNG")
        return
    except ImportError:
        pass

    # Fallback: write a minimal 1x1 PNG
    import struct
    import zlib
    width, height = 1, 1
    raw = b'\x00\x00\x00'  # 1 pixel, black
    compressed = zlib.compress(raw)
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', compressed)
    png += chunk(b'IEND', b'')
    with open(output_path, 'wb') as f:
        f.write(png)


# ---------------------------------------------------------------------------
# Test connection
# ---------------------------------------------------------------------------

def test_image_connection(provider: str, model: str,
                          api_key: str = "", base_url: str = "") -> dict:
    """Test image generation connection for the given provider."""
    try:
        if provider == "google_genai":
            return _test_google(model)
        if provider in ("siliconflow", "openai", "custom", "stability"):
            return _test_openai_compatible(provider, model, api_key, base_url)
        return {"success": False, "message": f"Unknown image provider: {provider}"}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}


def _test_google(model: str) -> dict:
    try:
        from google.genai import types

        client = _get_google_client(model)
        contents = [types.Content(role="user", parts=[types.Part(text="A small blue dot")])]
        gen_config = types.GenerateContentConfig(
            temperature=1,
            max_output_tokens=1024,
            response_modalities=["IMAGE"],
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
            ],
        )
        response = client.models.generate_content(model=model, contents=contents, config=gen_config)
        has_image = any(
            getattr(part, "inline_data", None)
            for part in (getattr(response, "parts", None) or [])
        )
        if not has_image and hasattr(response, "candidates") and response.candidates:
            for c in response.candidates:
                if hasattr(c, "content") and c.content:
                    for part in c.content.parts or []:
                        if hasattr(part, "inline_data") and part.inline_data:
                            has_image = True
                            break
                if has_image:
                    break
        if has_image:
            return {"success": True, "message": f"Gemini OK ({model})"}
        return {"success": False, "message": f"Connected but no image ({model})"}
    except ImportError:
        return {"success": False, "message": "google-genai not installed"}
    except RuntimeError as e:
        return {"success": False, "message": str(e)}


def _test_openai_compatible(provider: str, model: str,
                             api_key: str, base_url: str) -> dict:
    label = provider.capitalize()
    if provider == "siliconflow":
        default_url = "https://api.siliconflow.cn/v1"
    elif provider == "stability":
        default_url = "https://api.stability.ai/v1"
    else:
        default_url = "https://api.openai.com/v1"

    url = base_url or default_url
    endpoint = url.rstrip("/") + "/images/generations"

    payload = {"model": model, "prompt": "A small blue dot", "n": 1, "size": "1024x1024"}
    if provider == "siliconflow":
        payload["image_size"] = "1024x1024"
        payload["batch_size"] = 1
        payload["num_inference_steps"] = 20
        payload["guidance_scale"] = 7.5

    resp = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )

    if resp.status_code == 200:
        return {"success": True, "message": f"{label} OK ({model})"}
    return {"success": False, "message": f"{label} error: {resp.status_code} - {resp.text[:200]}"}
