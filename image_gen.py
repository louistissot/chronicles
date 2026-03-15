"""Gemini image generation via google-genai SDK (gemini-2.5-flash-image)."""
import base64
from pathlib import Path
from typing import Callable, Optional

from log import get_logger

_log = get_logger("image_gen")

_MODEL = "gemini-2.5-flash-image"


def generate_illustration(
    prompt,           # type: str
    api_key,          # type: str
    output_path,      # type: str
    stop_check=None,  # type: Optional[Callable[[], bool]]
):
    # type: (...) -> bool
    """Generate an image using Gemini 2.5 Flash and save to output_path.

    Uses the generate_content API with response_modalities=["TEXT", "IMAGE"].
    The 16:9 aspect ratio is requested in the text prompt.

    Args:
        prompt: The image generation prompt.
        api_key: Google Gemini API key.
        output_path: Where to save the resulting image.
        stop_check: Optional callable returning True if we should abort.

    Returns:
        True if image was generated and saved, False otherwise.
    """
    if stop_check and stop_check():
        _log.info("generate_illustration: stop requested before API call")
        return False

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError(
            "google-genai package not installed. "
            "Run: python3.9 -m pip install google-genai"
        )

    client = genai.Client(api_key=api_key)

    # Wrap the prompt to request a 16:9 landscape image
    full_prompt = (
        "Generate a 16:9 landscape illustration in epic fantasy art style. "
        "Do not include any text or labels in the image.\n\n" + prompt
    )

    _log.info(
        "Calling Gemini generate_content (model=%s, prompt_len=%d)",
        _MODEL, len(full_prompt),
    )

    try:
        response = client.models.generate_content(
            model=_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )
    except Exception as e:
        _log.error("Gemini content API error: %s", e)
        raise RuntimeError("Gemini image generation failed: {}".format(e)) from e

    if stop_check and stop_check():
        _log.info("generate_illustration: stop requested after API call")
        return False

    # Extract image from response parts
    image_bytes = None  # type: Optional[bytes]
    if response.candidates:
        for part in response.candidates[0].content.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                data = part.inline_data.data
                if isinstance(data, str):
                    image_bytes = base64.b64decode(data)
                else:
                    image_bytes = data
                break

    if not image_bytes:
        _log.error("No image data in Gemini response")
        raise RuntimeError("Gemini returned no image data")

    # Save
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image_bytes)
    _log.info("Illustration saved to %s (%d bytes)", out, out.stat().st_size)
    return True


def generate_portrait(
    prompt,           # type: str
    api_key,          # type: str
    output_path,      # type: str
    stop_check=None,  # type: Optional[Callable[[], bool]]
):
    # type: (...) -> bool
    """Generate a photorealistic character portrait. Does NOT wrap with fantasy style.

    Unlike generate_illustration(), this sends the prompt as-is to ensure
    the photorealistic instructions are preserved exactly.
    """
    if stop_check and stop_check():
        return False

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError(
            "google-genai package not installed. "
            "Run: python3.9 -m pip install google-genai"
        )

    client = genai.Client(api_key=api_key)

    # Send prompt directly — no fantasy art wrapper
    full_prompt = (
        "Generate a 1:1 square portrait photograph. "
        "Do not include any text, labels, or watermarks.\n\n" + prompt
    )

    _log.info(
        "Calling Gemini generate_content for portrait (model=%s, prompt_len=%d)",
        _MODEL, len(full_prompt),
    )

    try:
        response = client.models.generate_content(
            model=_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )
    except Exception as e:
        _log.error("Gemini portrait API error: %s", e)
        raise RuntimeError("Gemini portrait generation failed: {}".format(e)) from e

    if stop_check and stop_check():
        return False

    image_bytes = None  # type: Optional[bytes]
    if response.candidates:
        for part in response.candidates[0].content.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                data = part.inline_data.data
                if isinstance(data, str):
                    image_bytes = base64.b64decode(data)
                else:
                    image_bytes = data
                break

    if not image_bytes:
        _log.error("No image data in Gemini portrait response")
        raise RuntimeError("Gemini returned no portrait image data")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image_bytes)
    _log.info("Portrait saved to %s (%d bytes)", out, out.stat().st_size)
    return True


def generate_fullbody(
    prompt,           # type: str
    api_key,          # type: str
    output_path,      # type: str
    stop_check=None,  # type: Optional[Callable[[], bool]]
):
    # type: (...) -> bool
    """Generate a photorealistic full-body character image.

    Uses 2:3 portrait orientation. Sends prompt as-is (no fantasy wrapper).
    """
    if stop_check and stop_check():
        return False

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError(
            "google-genai package not installed. "
            "Run: python3.9 -m pip install google-genai"
        )

    client = genai.Client(api_key=api_key)

    full_prompt = (
        "Generate a 2:3 portrait-orientation full-body photograph showing the "
        "subject from head to toe. Do not include any text, labels, or watermarks.\n\n"
        + prompt
    )

    _log.info(
        "Calling Gemini generate_content for fullbody (model=%s, prompt_len=%d)",
        _MODEL, len(full_prompt),
    )

    try:
        response = client.models.generate_content(
            model=_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )
    except Exception as e:
        _log.error("Gemini fullbody API error: %s", e)
        raise RuntimeError("Gemini fullbody generation failed: {}".format(e)) from e

    if stop_check and stop_check():
        return False

    image_bytes = None  # type: Optional[bytes]
    if response.candidates:
        for part in response.candidates[0].content.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                data = part.inline_data.data
                if isinstance(data, str):
                    image_bytes = base64.b64decode(data)
                else:
                    image_bytes = data
                break

    if not image_bytes:
        _log.error("No image data in Gemini fullbody response")
        raise RuntimeError("Gemini returned no fullbody image data")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image_bytes)
    _log.info("Fullbody saved to %s (%d bytes)", out, out.stat().st_size)
    return True
