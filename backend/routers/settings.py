"""
Settings router - model configuration and test connection.
"""

import os
from fastapi import APIRouter
from models import ModelsConfig, TestConnectionRequest
from repositories.settings_repo import get_all_settings, set_setting

router = APIRouter()


def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return "****" if key else ""
    return key[:4] + "****" + key[-4:]


@router.get("/settings/models")
async def get_models_settings():
    """Get current model settings (API keys masked)."""
    all_settings = get_all_settings()

    llm_config = {
        "provider": all_settings.get("llm_provider", "openai"),
        "base_url": all_settings.get("llm_base_url", ""),
        "model": all_settings.get("llm_model", "gpt-4o"),
        "has_api_key": bool(all_settings.get("llm_api_key")),
        "masked_api_key": _mask_key(all_settings.get("llm_api_key", "")),
    }

    image_config = {
        "provider": all_settings.get("image_provider", "openai"),
        "base_url": all_settings.get("image_base_url", ""),
        "model": all_settings.get("image_model", "dall-e-3"),
        "has_api_key": bool(all_settings.get("image_api_key")),
        "masked_api_key": _mask_key(all_settings.get("image_api_key", "")),
        "image_size": all_settings.get("image_size", "1024x1024"),
        "num_inference_steps": int(all_settings.get("num_inference_steps", "20")),
        "guidance_scale": float(all_settings.get("guidance_scale", "7.5")),
    }

    video_config = {
        "provider": all_settings.get("video_provider", "vectorengine"),
        "base_url": all_settings.get("video_base_url", "https://api.vectorengine.ai"),
        "model": all_settings.get("video_model", "veo3.1-fast"),
        "has_api_key": bool(all_settings.get("video_api_key")),
        "masked_api_key": _mask_key(all_settings.get("video_api_key", "")),
        "aspect_ratio": all_settings.get("video_aspect_ratio", "16:9"),
    }

    google_config = {
        "project": all_settings.get("google_project", "") or os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
        "location": all_settings.get("google_location", "") or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
    }

    return {
        "llm": llm_config,
        "image": image_config,
        "video": video_config,
        "google": google_config,
        "video_generation_mode": all_settings.get("video_generation_mode", "manual"),
        "video_demo_mode": all_settings.get("video_demo_mode", "false") == "true",
        "image_demo_mode": all_settings.get("image_demo_mode", "false") == "true",
        "dubbing_test_mode": all_settings.get("dubbing_test_mode", "false") == "true",
        "dubbing_test_video_path": all_settings.get("dubbing_test_video_path", ""),
    }


@router.put("/settings/models")
async def update_models_settings(config: ModelsConfig):
    """Update model settings."""
    if config.llm:
        if config.llm.provider:
            set_setting("llm_provider", config.llm.provider)
        if config.llm.base_url is not None:
            set_setting("llm_base_url", config.llm.base_url)
        if config.llm.api_key:
            set_setting("llm_api_key", config.llm.api_key)
        if config.llm.model:
            set_setting("llm_model", config.llm.model)

    if config.image:
        if config.image.provider:
            set_setting("image_provider", config.image.provider)
        if config.image.base_url is not None:
            set_setting("image_base_url", config.image.base_url)
        if config.image.api_key:
            set_setting("image_api_key", config.image.api_key)
        if config.image.model:
            set_setting("image_model", config.image.model)
        if config.image.image_size:
            set_setting("image_size", config.image.image_size)
        set_setting("num_inference_steps", str(config.image.num_inference_steps))
        set_setting("guidance_scale", str(config.image.guidance_scale))

    if config.video:
        if config.video.provider:
            set_setting("video_provider", config.video.provider)
        if config.video.base_url is not None:
            set_setting("video_base_url", config.video.base_url)
        if config.video.api_key:
            set_setting("video_api_key", config.video.api_key)
        if config.video.model:
            set_setting("video_model", config.video.model)
        if config.video.aspect_ratio:
            set_setting("video_aspect_ratio", config.video.aspect_ratio)

    if config.google:
        if config.google.project:
            set_setting("google_project", config.google.project)
        if config.google.location:
            set_setting("google_location", config.google.location)

    if config.video_generation_mode:
        set_setting("video_generation_mode", config.video_generation_mode)

    if config.video_demo_mode is not None:
        set_setting("video_demo_mode", "true" if config.video_demo_mode else "false")

    if config.image_demo_mode is not None:
        set_setting("image_demo_mode", "true" if config.image_demo_mode else "false")

    if config.dubbing_test_mode is not None:
        set_setting("dubbing_test_mode", "true" if config.dubbing_test_mode else "false")

    if config.dubbing_test_video_path is not None:
        set_setting("dubbing_test_video_path", config.dubbing_test_video_path)

    return {"status": "ok"}


@router.post("/settings/test")
async def test_connection(request: TestConnectionRequest):
    """Test connection to LLM, image, or video provider."""
    all_settings = get_all_settings()

    if request.provider_type == "llm":
        from integrations.llm import test_llm_connection
        provider = all_settings.get("llm_provider", "openai")
        model = all_settings.get("llm_model", "gpt-4o")
        api_key = all_settings.get("llm_api_key", "")
        base_url = all_settings.get("llm_base_url", "")

        # Google Gen AI doesn't need API key (uses ADC)
        if provider == "google_genai":
            return test_llm_connection(provider, model)

        if not api_key:
            return {"success": False, "message": "LLM API key not configured"}
        return test_llm_connection(provider, model, api_key, base_url)

    elif request.provider_type == "image":
        import asyncio
        from integrations.image import test_image_connection
        provider = all_settings.get("image_provider", "openai")
        model = all_settings.get("image_model", "dall-e-3")
        api_key = all_settings.get("image_api_key", "")
        base_url = all_settings.get("image_base_url", "")

        # Google Gen AI doesn't need API key (uses ADC)
        if provider == "google_genai":
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: test_image_connection(provider, model)
            )

        if not api_key:
            return {"success": False, "message": "Image API key not configured"}
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: test_image_connection(provider, model, api_key, base_url)
        )

    elif request.provider_type == "video":
        from integrations.video import test_video_connection
        api_key = all_settings.get("video_api_key", "")
        base_url = all_settings.get("video_base_url", "")
        model = all_settings.get("video_model", "veo3.1-fast")
        if not api_key:
            return {"success": False, "message": "Video API key not configured"}
        return test_video_connection(api_key, base_url, model,
                                     provider=all_settings.get("video_provider", "vectorengine"))

    return {"success": False, "message": f"Unknown provider type: {request.provider_type}"}
