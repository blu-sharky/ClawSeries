"""
Image generation integration - Gemini native image generation via google-genai SDK.
"""

from __future__ import annotations

import os
from repositories.settings_repo import get_setting


def is_image_configured() -> bool:
    return bool(os.environ.get("GOOGLE_CLOUD_PROJECT") or get_setting("google_project"))


def get_image_config() -> dict:
    return {
        "model": get_setting("image_model", "gemini-2.5-flash-image"),
    }


def _get_google_client():
    """Create a Google Gen AI client using Vertex AI (ADC auth)."""
    from google import genai

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


async def generate_image(prompt: str, output_path: str,
                         reference_images: list[str] | None = None,
                         aspect_ratio: str = "1:1") -> str:
    """Generate an image using Gemini native image generation. Returns the output path."""
    import asyncio
    from google.genai import types

    config = get_image_config()
    model = config["model"]
    client = _get_google_client()

    ar_map = {
        "1:1": "1:1", "16:9": "16:9", "9:16": "9:16",
        "3:4": "3:4", "4:3": "4:3",
    }
    imagen_ar = ar_map.get(aspect_ratio, "1:1")

    contents = [
        types.Content(
            role="user",
            parts=[types.Part(text=prompt)]
        )
    ]

    generate_content_config = types.GenerateContentConfig(
        temperature=1,
        top_p=0.95,
        max_output_tokens=8192,
        response_modalities=["TEXT", "IMAGE"],
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

    loop = asyncio.get_event_loop()
    image_bytes = await loop.run_in_executor(
        None,
        lambda: _collect_image(client, model, contents, generate_content_config)
    )

    if not image_bytes:
        raise RuntimeError("Gemini image generation returned no image data")

    with open(output_path, "wb") as f:
        f.write(image_bytes)

    return output_path


def _collect_image(client, model: str, contents, config) -> bytes | None:
    """Collect image bytes from Gemini streaming response."""
    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=config,
    ):
        if hasattr(chunk, "candidates") and chunk.candidates:
            for candidate in chunk.candidates:
                if hasattr(candidate, "content") and candidate.content:
                    for part in candidate.content.parts or []:
                        if hasattr(part, "inline_data") and part.inline_data:
                            return part.inline_data.data
    return None


def test_image_connection(model: str) -> dict:
    """Test Gemini image generation connection."""
    try:
        from google.genai import types

        client = _get_google_client()

        contents = [
            types.Content(
                role="user",
                parts=[types.Part(text="A small blue dot on white background")]
            )
        ]
        generate_content_config = types.GenerateContentConfig(
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

        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )

        has_image = False
        if hasattr(response, "candidates") and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, "content") and candidate.content:
                    for part in candidate.content.parts or []:
                        if hasattr(part, "inline_data") and part.inline_data:
                            has_image = True

        if has_image:
            return {"success": True, "message": f"Gemini image generation OK ({model})"}
        return {"success": False, "message": f"Connected but no image returned ({model})"}

    except ImportError:
        return {"success": False, "message": "google-genai not installed. Run: pip install google-genai"}
    except RuntimeError as e:
        return {"success": False, "message": str(e)}
    except Exception as e:
        return {"success": False, "message": f"Gemini error: {str(e)}"}
