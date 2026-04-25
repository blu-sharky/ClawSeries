"""
Video generation integration - supports Seedance, VectorEngine, and OpenAI Sora providers.
"""

import asyncio
import base64
import json
import struct
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
        "provider": get_setting("video_provider", "seedance"),
        "api_key": get_setting("video_api_key", ""),
        "base_url": get_setting("video_base_url", "https://api.seedance.com/v1"),
        "model": get_setting("video_model", "seedance-2.0"),
        "aspect_ratio": get_setting("video_aspect_ratio", "16:9"),
    }


async def _generate_openai_video(config, prompt, output_path, reference_image, duration_seconds, aspect_ratio):
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

    # If reference_image provided, encode as base64 data URL
    if reference_image:
        img_path = Path(reference_image)
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

    async with httpx.AsyncClient(timeout=300.0, trust_env=False) as client:
        # Submit
        resp = await client.post(f'{base}/videos', headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        video_id = data['id']

        # Poll for completion
        for _ in range(120):
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

        raise RuntimeError('Video generation timed out')

async def _generate_vectorengine_video(config, prompt, output_path, reference_image, duration_seconds, aspect_ratio):
    """Generate video via VectorEngine API (POST /v1/video/create, poll GET /v1/video/query)."""
    import httpx
    base = config['base_url'].rstrip('/')

    payload = {
        'model': config['model'],
        'prompt': prompt,
        'aspect_ratio': aspect_ratio,
        'enhance_prompt': True,
    }
    if reference_image:
        payload['images'] = [reference_image]

    headers = {
        'Authorization': f"Bearer {config['api_key']}",
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    async with httpx.AsyncClient(timeout=300.0, trust_env=False) as client:
        # Submit
        resp = await client.post(f'{base}/v1/video/create', headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        task_id = data.get('id')
        if not task_id:
            raise RuntimeError(f'VectorEngine did not return task id: {data}')

        # Poll for completion
        for _ in range(120):
            await asyncio.sleep(5)
            status_resp = await client.get(
                f'{base}/v1/video/query?id={task_id}', headers=headers,
            )
            status_resp.raise_for_status()
            status_data = status_resp.json()

            if status_data.get('status') == 'completed':
                video_url = status_data.get('video_url')
                if video_url:
                    vid_resp = await client.get(video_url, follow_redirects=True)
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, 'wb') as f:
                        f.write(vid_resp.content)
                    return output_path
                raise RuntimeError('Video completed but no URL returned')

            if status_data.get('status') == 'failed':
                raise RuntimeError(f'VectorEngine generation failed: {status_data}')

        raise RuntimeError('VectorEngine video generation timed out')


async def generate_video(prompt: str, output_path: str,
                          reference_image: str | None = None,
                          duration_seconds: int = 5,
                          aspect_ratio: str = "16:9") -> str:
    """
    Generate a video using the configured video provider.
    Returns the output path.
    Raises RuntimeError if not configured.
    """
    # Demo mode: return a blank black video
    if is_demo_mode():
        import asyncio
        await asyncio.sleep(0.1)
        _create_demo_video(output_path, duration_seconds=duration_seconds)
        return output_path

    config = get_video_config()
    if not config['api_key']:
        raise RuntimeError('Video API key not configured. Please configure in Settings.')

    # Append language emphasis to prompt
    prompt = f"{prompt}. The dialogue and any on-screen text must be in Chinese (中文)."

    # Route to provider-specific implementation
    provider = config.get('provider', 'seedance').lower()
    if provider in ('openai', 'sora'):
        return await _generate_openai_video(config, prompt, output_path, reference_image, duration_seconds, aspect_ratio)
    if provider == 'vectorengine':
        return await _generate_vectorengine_video(config, prompt, output_path, reference_image, duration_seconds, aspect_ratio)


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
    if reference_image:
        payload["reference_image"] = reference_image

    async with httpx.AsyncClient(timeout=300.0, trust_env=False) as client:
        # Submit generation request
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        task_id = data.get("task_id") or data.get("id")

        # Poll for completion
        status_url = f"{config['base_url'].rstrip('/')}/video/status/{task_id}"
        for _ in range(120):  # Max 10 minutes
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

        raise RuntimeError("Video generation timed out")

    return output_path


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
