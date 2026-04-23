"""
Video generation integration - supports Seedance 2.0 and compatible providers.
"""

import json
from repositories.settings_repo import get_setting


def is_video_configured() -> bool:
    return bool(get_setting("video_api_key"))


def get_video_config() -> dict:
    return {
        "api_key": get_setting("video_api_key", ""),
        "base_url": get_setting("video_base_url", "https://api.seedance.com/v1"),
        "model": get_setting("video_model", "seedance-2.0"),
    }


async def generate_video(prompt: str, output_path: str,
                          reference_image: str | None = None,
                          duration_seconds: int = 5,
                          aspect_ratio: str = "16:9") -> str:
    """
    Generate a video using the configured video provider.
    Returns the output path.
    Raises RuntimeError if not configured.
    """
    config = get_video_config()
    if not config["api_key"]:
        raise RuntimeError("Video API key not configured. Please configure in Settings.")

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

    async with httpx.AsyncClient(timeout=300.0) as client:
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


import asyncio


def test_video_connection(api_key: str, base_url: str, model: str) -> dict:
    """Test video provider connection."""
    try:
        import httpx
        url = f"{(base_url or 'https://api.seedance.com/v1').rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = httpx.get(url, headers=headers, timeout=10.0)
        if resp.status_code == 200:
            return {"success": True, "message": f"Connected to {model}"}
        elif resp.status_code == 401:
            return {"success": False, "message": "Authentication failed - check API key"}
        else:
            return {"success": False, "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"success": False, "message": str(e)}
