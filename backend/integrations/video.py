"""
Video generation integration - supports Seedance, VectorEngine, and OpenAI Sora providers.
"""

import asyncio
import base64
import json
import struct
import mimetypes
import re
from pathlib import Path
from repositories.settings_repo import get_setting



def parse_duration_seconds(value, fallback: int = 10) -> int:
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    if match:
        seconds = float(match.group())
        if "分" in str(value):
            seconds *= 60
        if seconds > 0:
            return int(seconds)
    return fallback

def is_video_configured() -> bool:
    if get_setting("video_demo_mode") == "true":
        return True
    return bool(get_setting("video_api_key"))


def is_demo_mode() -> bool:
    return get_setting("video_demo_mode") == "true"


def _create_demo_video(output_path: str, duration_seconds: int = 3,
                       width: int = 640, height: int = 360) -> None:
    """Create a minimal valid black MP4 file using ffmpeg, falling back to raw bytes."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Try ffmpeg first for a proper playable video
    import subprocess
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:d={duration_seconds}:r=24",
                "-c:v", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", output_path,
            ],
            capture_output=True, timeout=30,
        )
        if out.exists() and out.stat().st_size > 0:
            return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: write a minimal valid MP4 (black frame, ~1s)
    _write_minimal_mp4(output_path)


def _write_minimal_mp4(output_path: str) -> None:
    """Write the smallest valid MP4 file possible."""
    # Minimal ftyp + moov box for a zero-length video
    ftyp = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom'
    # Minimal moov box
    mvhd = (
        b'\x00\x00\x00\x6C' + b'moov' +
        b'\x00\x00\x00\x6C' + b'mvhd' +
        b'\x00' +                              # version
        b'\x00' * 3 +                          # flags
        b'\x00\x00\x00\x00' +                  # creation time
        b'\x00\x00\x00\x00' +                  # modification time
        b'\x00\x00\x03\xE8' +                  # timescale = 1000
        b'\x00\x00\x00\x01' +                  # duration = 1ms
        b'\x00\x01\x00\x00' +                  # rate = 1.0
        b'\x01\x00' +                          # volume = 1.0
        b'\x00' * 10 +                         # reserved
        b'\x00\x01\x00\x00' + b'\x00' * 4 + b'\x00' * 4 +  # matrix row 1
        b'\x00' * 4 + b'\x00\x01\x00\x00' + b'\x00' * 4 +  # matrix row 2
        b'\x00' * 4 + b'\x00' * 4 + b'\x40\x00\x00\x00' +  # matrix row 3
        b'\x00' * 24 +                         # pre-defined
        b'\x00\x00\x00\x02'                    # next track id
    )
    with open(output_path, 'wb') as f:
        f.write(ftyp + mvhd)


def get_video_config() -> dict:
    return {
        "provider": get_setting("video_provider", "vectorengine"),
        "api_key": get_setting("video_api_key", ""),
        "base_url": get_setting("video_base_url", "https://api.vectorengine.ai"),
        "model": get_setting("video_model", "veo3.1-fast"),
        "aspect_ratio": get_setting("video_aspect_ratio", "16:9"),
    }

def _is_veo_model(config: dict) -> bool:
    return "veo" in str(config.get("model", "")).lower()


def _is_audio_filtered_error(message: str) -> bool:
    lower = str(message or "").lower()
    return any(token in lower for token in (
        "public_error_audio_filtered",
        "audio_filtered",
        "audio for your prompt",
        "raimediafilteredreasons",
    ))


def _make_veo_audio_safe_prompt(prompt: str) -> str:
    sanitized = re.sub(r"spoken dialogue\s*:\s*[^\n,.]+", "", prompt, flags=re.IGNORECASE)
    sanitized = re.sub(r"\s+,", ",", sanitized)
    sanitized = re.sub(r"\s{2,}", " ", sanitized).strip(" ,.")
    return (
        f"{sanitized}. "
        "No audible dialogue, no voiceover, no lyrics, no singing. "
        "Ambient scene sound only. Characters may emote and move, but do not speak audibly. "
        "Any visible on-screen text must be in Chinese (中文)."
    )


async def _generate_openai_video(config, prompt, output_path, ref_list, duration_seconds, aspect_ratio):
    """Generate video via OpenAI Sora API (POST /videos, poll, download)."""
    import httpx
    base = config['base_url'].rstrip('/')

    # Convert aspect_ratio to size string
    ar_to_size = {
        '16:9': '1280x720', '9:16': '720x1280', '1:1': '720x720',
    }
    size = ar_to_size.get(aspect_ratio, '1280x720')

    payload = {
        'model': config['model'],
        'prompt': prompt,
        'size': size,
        'seconds': str(duration_seconds),
    }

    # If reference images provided, encode first one as base64 data URL
    if ref_list:
        img_path = Path(ref_list[0])
        if img_path.exists():
            img_data = base64.b64encode(img_path.read_bytes()).decode()
            ext = img_path.suffix.lstrip('.')
            mime = {
                'png': 'image/png', 'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg', 'webp': 'image/webp',
            }.get(ext, 'image/png')
            payload['input_reference'] = {'image_url': f'data:{mime};base64,{img_data}'}

    headers = {
        'Authorization': f"Bearer {config['api_key']}",
        'Content-Type': 'application/json',
    }

    async with httpx.AsyncClient(timeout=None, trust_env=False) as client:
        # Submit
        resp = await client.post(f'{base}/videos', headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        video_id = data['id']

        # Poll for completion
        while True:
            await asyncio.sleep(5)
            status_resp = await client.get(f'{base}/videos/{video_id}', headers=headers)
            status_resp.raise_for_status()
            status_data = status_resp.json()

            if status_data.get('status') == 'completed':
                # Download video content
                content_resp = await client.get(
                    f'{base}/videos/{video_id}/content',
                    headers=headers, follow_redirects=True,
                )
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(content_resp.content)
                return output_path

            if status_data.get('status') == 'failed':
                error = status_data.get('error', {})
                msg = error.get('message', 'Unknown error') if isinstance(error, dict) else str(error)
                raise RuntimeError(f'Video generation failed: {msg}')


async def _upload_vectorengine_image(client, image_path: str) -> str:
    path = Path(image_path)
    if not path.exists():
        raise RuntimeError(f'VectorEngine reference image not found: {image_path}')
    mime = mimetypes.guess_type(path.name)[0] or 'image/png'
    with path.open('rb') as f:
        resp = await client.post(
            'https://imageproxy.zhongzhuan.chat/api/upload',
            files={'file': (path.name, f, mime)},
        )
    resp.raise_for_status()
    data = resp.json()
    url = data.get('url')
    if not url:
        raise RuntimeError(f'VectorEngine image upload returned no url: {data}')
    return url

async def _generate_vectorengine_video(config, prompt, output_path, ref_list, duration_seconds, aspect_ratio):
    """Generate video via VectorEngine API (POST /v1/video/create, poll GET /v1/video/query)."""
    import httpx
    base = config['base_url'].rstrip() or 'https://api.vectorengine.ai'

    payload = {
        'model': config['model'],
        'prompt': prompt,
        'aspect_ratio': aspect_ratio,
        'enhance_prompt': True,
        'enable_upsample': True,
    }

    headers = {
        'Authorization': f"Bearer {config['api_key']}",
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    async with httpx.AsyncClient(timeout=None, trust_env=False) as client:
        if ref_list:
            uploaded = []
            for img_path in ref_list:
                try:
                    url = await _upload_vectorengine_image(client, img_path)
                    uploaded.append(url)
                except Exception as e:
                    print(f"[Video] Failed to upload reference image {img_path}: {e}")
            if uploaded:
                payload['images'] = uploaded

        # Submit
        resp = await client.post(f'{base}/v1/video/create', headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        task_id = data.get('id')
        if not task_id:
            raise RuntimeError(f'VectorEngine did not return task id: {data}')

        # Poll for completion
        while True:
            await asyncio.sleep(5)
            status_resp = await client.get(
                f'{base}/v1/video/query', headers=headers, params={'id': task_id},
            )
            status_resp.raise_for_status()
            status_data = status_resp.json()

            if status_data.get('status') == 'completed':
                video_url = status_data.get('video_url') or status_data.get('detail', {}).get('video_url')
                if video_url:
                    vid_resp = await client.get(video_url, follow_redirects=True)
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, 'wb') as f:
                        f.write(vid_resp.content)
                    return output_path
                raise RuntimeError('Video completed but no URL returned')

            if status_data.get('status') == 'failed':
                raise RuntimeError(f'VectorEngine generation failed: {status_data}')


async def generate_video(prompt: str, output_path: str,
                          reference_image: str | None = None,
                          reference_images: list[str] | None = None,
                          duration_seconds: int = 5,
                          aspect_ratio: str = "16:9") -> str:
    """
    Generate a video using the configured video provider.
    Returns the output path.
    Raises RuntimeError if not configured.

    reference_image: single image path (backward compat)
    reference_images: list of image paths (preferred, supports multiple)
    """
    # Normalize to list
    ref_list = []
    if reference_images:
        ref_list = [p for p in reference_images if p]
    elif reference_image:
        ref_list = [reference_image]

    # Demo mode: return a blank black video
    if is_demo_mode():
        await asyncio.sleep(0.1)
        _create_demo_video(output_path, duration_seconds=duration_seconds)
        return output_path

    config = get_video_config()
    if not config['api_key']:
        raise RuntimeError('Video API key not configured. Please configure in Settings.')

    if _is_veo_model(config):
        prompt = _make_veo_audio_safe_prompt(prompt)
    else:
        prompt = f"{prompt}. The dialogue and any on-screen text must be in Chinese (中文)."

    attempt = 0
    while True:
        attempt += 1
        try:
            return await _generate_video_inner(config, prompt, output_path, ref_list, duration_seconds, aspect_ratio)
        except Exception as e:
            if _is_veo_model(config) and _is_audio_filtered_error(str(e)):
                print(f"[Video] Veo audio filter hit on attempt {attempt}; retrying with audio-safe prompt")
                prompt = _make_veo_audio_safe_prompt(prompt)
            wait = min(30, 10 * attempt)  # 10s, 20s, 30s, 30s, ...
            print(f"[Video] attempt {attempt} failed: {e}. Retrying in {wait}s...")
            await asyncio.sleep(wait)


async def _generate_video_inner(config, prompt, output_path, ref_list, duration_seconds, aspect_ratio):
    """Inner implementation — called with retry by generate_video."""
    # Route to provider-specific implementation
    provider = config.get('provider', 'seedance').lower()
    if provider in ('openai', 'sora'):
        return await _generate_openai_video(config, prompt, output_path, ref_list, duration_seconds, aspect_ratio)
    if provider == 'vectorengine':
        return await _generate_vectorengine_video(config, prompt, output_path, ref_list, duration_seconds, aspect_ratio)


    import httpx
    url = f"{config['base_url'].rstrip('/')}/video/generate"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
        "prompt": prompt,
        "duration": duration_seconds,
        "aspect_ratio": aspect_ratio,
    }
    if ref_list:
        payload["reference_image"] = ref_list[0]

    async with httpx.AsyncClient(timeout=None, trust_env=False) as client:
        # Submit generation request
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        task_id = data.get("task_id") or data.get("id")

        # Poll for completion
        status_url = f"{config['base_url'].rstrip('/')}/video/status/{task_id}"
        while True:
            await asyncio.sleep(5)
            status_resp = await client.get(status_url, headers=headers)
            status_resp.raise_for_status()
            status_data = status_resp.json()

            if status_data.get("status") == "completed":
                video_url = status_data.get("video_url") or status_data.get("output", {}).get("video_url")
                if video_url:
                    # Download video
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    vid_resp = await client.get(video_url)
                    with open(output_path, "wb") as f:
                        f.write(vid_resp.content)
                    return output_path
                raise RuntimeError("Video completed but no URL returned")

            if status_data.get("status") == "failed":
                error = status_data.get("error", "Unknown error")
                raise RuntimeError(f"Video generation failed: {error}")


def test_video_connection(api_key: str, base_url: str, model: str,
                          provider: str = "seedance") -> dict:
    """Test video provider connection."""
    try:
        import httpx

        if provider == "vectorengine":
            url = f"{(base_url or 'https://api.vectorengine.ai').rstrip('/')}/v1/video/create"
            headers = {"Authorization": f"Bearer {api_key}"}
            # Just verify auth works — don't actually create a video
            resp = httpx.post(url, headers=headers, json={}, timeout=10.0, trust_env=False)
            # Expected: 400/422 (validation error means auth passed)
            if resp.status_code in (400, 422):
                return {"success": True, "message": f"Connected to VectorEngine ({model})"}
            if resp.status_code == 401:
                return {"success": False, "message": "Authentication failed - check API key"}
            if resp.status_code == 200:
                return {"success": True, "message": f"Connected to VectorEngine ({model})"}
            return {"success": False, "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}

        url = f"{(base_url or 'https://api.seedance.com/v1').rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = httpx.get(url, headers=headers, timeout=10.0, trust_env=False)
        if resp.status_code == 200:
            return {"success": True, "message": f"Connected to {model}"}
        elif resp.status_code == 401:
            return {"success": False, "message": "Authentication failed - check API key"}
        else:
            return {"success": False, "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"success": False, "message": str(e)}
