from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any, Dict, Optional

from openai import OpenAI

OLLAMA_BASE_URL_ENV = "OLLAMA_BASE_URL"
OLLAMA_API_KEY_ENV = "OLLAMA_API_KEY"

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_OLLAMA_API_KEY = "ollama"
DEFAULT_VISION_MODEL = "llama3.2-vision:11b"

UPLOADS_DIR = Path("uploads").resolve()


def _get_client() -> OpenAI:
    base_url = os.getenv(OLLAMA_BASE_URL_ENV, DEFAULT_OLLAMA_BASE_URL)
    api_key = os.getenv(OLLAMA_API_KEY_ENV, DEFAULT_OLLAMA_API_KEY)
    return OpenAI(base_url=base_url, api_key=api_key)


class VisionAnalysisTool:
    """
    Tool for analyzing images using a multimodal model exposed via Ollama.
    """

    @staticmethod
    def analyze_image(
        image_path: str,
        prompt: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> str:
        """
        Analyze an image and return a textual description.

        :param image_path: Absolute or relative path to the image file (must reside under uploads/).
        :param prompt: Optional analysis instruction (e.g. 'Describe the chart trends.').
        :param model_name: Optional override of the vision model name.
        """
        # Security: only allow images that live within the uploads directory.
        img_path = Path(image_path).resolve()
        if not str(img_path).startswith(str(UPLOADS_DIR)):
            raise ValueError("Image path is not within the allowed uploads directory.")
        if not img_path.is_file():
            raise FileNotFoundError(f"Image not found at {img_path}")

        with img_path.open("rb") as f:
            img_bytes = f.read()
        b64 = base64.b64encode(img_bytes).decode("utf-8")

        ext = img_path.suffix.lower().lstrip(".") or "png"
        data_url = f"data:image/{ext};base64,{b64}"

        user_prompt = prompt or "Describe this image in detail, focusing on any data, patterns, or key elements."

        client = _get_client()

        # OpenAI-compatible vision message format
        response = client.chat.completions.create(
            model=model_name or DEFAULT_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
        )

        content = response.choices[0].message.content or ""
        return content

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Return the tool schema in OpenAI/Ollama function-calling format.
        """
        return {
            "name": "analyze_image",
            "description": (
                "Analyze an uploaded image and return a detailed natural language description "
                "of its contents, including any data, charts, or notable visual patterns."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": (
                            "Server-side path of the uploaded image file. "
                            "The front-end should upload the image first and then pass this path."
                        ),
                    },
                    "prompt": {
                        "type": "string",
                        "description": (
                            "Optional instruction for how to analyze the image "
                            "(e.g. 'Summarize the chart trends', 'Describe objects in the scene')."
                        ),
                    },
                },
                "required": ["image_path"],
            },
        }


