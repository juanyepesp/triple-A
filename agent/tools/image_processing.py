from __future__ import annotations

import os
import base64
import hashlib
from html import escape
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def load_screenshot(
    screenshot_path: str,
    runtime_dir: str | Path | None = None,
) -> tuple[Path, Any]:
    """Resolve and load a screenshot as a BGR OpenCV image."""
    
    resolved_path = screenshot_path
    image = cv2.imread(str(resolved_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(
            f"OpenCV could not read screenshot {resolved_path}. "
            "Check that the VM shares the JavaScript screenshot directory."
        )

    return resolved_path, image


def apply_impairment(image: Any, impairment: str | None) -> Any:
    """Apply a named visual-impairment simulation to a BGR image."""
    impairment_name = (impairment or "none").lower().replace("-", "_").replace(" ", "_")

    if impairment_name in {"none", "original"}:
        return image.copy()
    if impairment_name in {"blur", "low_vision"}:
        return cv2.GaussianBlur(image, (0, 0), sigmaX=5)
    if impairment_name in {"protanopia", "deuteranopia", "tritanopia"}:
        matrices = {
            "protanopia": (
                (0.567, 0.433, 0.000),
                (0.558, 0.442, 0.000),
                (0.000, 0.242, 0.758),
            ),
            "deuteranopia": (
                (0.625, 0.375, 0.000),
                (0.700, 0.300, 0.000),
                (0.000, 0.300, 0.700),
            ),
            "tritanopia": (
                (0.950, 0.050, 0.000),
                (0.000, 0.433, 0.567),
                (0.000, 0.475, 0.525),
            ),
        }
        # The matrices are RGB; OpenCV stores channels as BGR.
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype("float32")
        transformed = cv2.transform(rgb, np.array(matrices[impairment_name], dtype=np.float32))
        return cv2.cvtColor(transformed.clip(0, 255).astype("uint8"), cv2.COLOR_RGB2BGR)
    if impairment_name == "tunnel_vision":
        height, width = image.shape[:2]
        mask = np.zeros((height, width), dtype="uint8")
        cv2.ellipse(mask, (width // 2, height // 2), (width // 3, height // 3), 0, 0, 360, 255, -1)
        return cv2.bitwise_and(image, image, mask=mask)

    raise ValueError(
        f"Unsupported impairment {impairment!r}. "
        "Use none, blur, low_vision, protanopia, deuteranopia, tritanopia, or tunnel_vision."
    )


# TODO ver si encontramos alguno de los motores de renderizado open sourced

def image_hash(image: Any) -> str:
    """Return a stable token for comparing screenshots in graph state."""
    return hashlib.sha256(image.tobytes()).hexdigest()


def image_changed(image: Any, previous_hash: str | None) -> bool:
    """Determine whether an image differs from the previously processed image."""
    return previous_hash is None or image_hash(image) != previous_hash


def encode_jpeg(image: Any) -> str:
    """Encode an OpenCV image as a data URI for a multimodal model."""
    success, encoded = cv2.imencode(".jpg", image)
    if not success:
        raise ValueError("OpenCV could not encode the transformed screenshot as JPEG.")
    payload = base64.b64encode(encoded).decode("ascii")
    return f"data:image/jpeg;base64,{payload}"


def save_vision_report(
    image: Any,
    description: str,
    output_dir: str | Path,
    screenshot_path: str | Path,
    impairment: str,
    screenshot_hash: str,
) -> Path:
    """Save the transformed image and description as one self-contained HTML file."""
    report_dir = Path(output_dir).expanduser()
    report_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = Path(screenshot_path)
    report_path = report_dir / f"{screenshot_path.stem}-{screenshot_hash[:12]}.html"

    image_data_uri = encode_jpeg(image)
    escaped_description = escape(description).replace("\n", "<br>\n")
    report_path.write_text(
    f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Vision inspection: {escape(screenshot_path.name)}</title>
    <style>
        body {{ font-family: sans-serif; margin: 2rem; max-width: 70rem; }}
        img {{ display: block; max-width: 100%; height: auto; border: 1px solid #ccc; }}
        .metadata {{ color: #555; }}
        .description {{ white-space: normal; line-height: 1.5; }}
    </style>
</head>
<body>
    <h1>Vision inspection</h1>
    <p class="metadata">Source: {escape(str(screenshot_path))}<br>
    Impairment: {escape(impairment)}<br>
    Screenshot hash: {escape(screenshot_hash)}</p>
    <img src="{image_data_uri}" alt="Transformed screenshot">
    <h2>Description</h2>
    <p class="description">{escaped_description}</p>
</body>
</html>
""",
        encoding="utf-8",
    )
    return report_path


