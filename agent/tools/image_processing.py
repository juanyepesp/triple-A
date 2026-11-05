from __future__ import annotations

import base64
import hashlib
from html import escape
from pathlib import Path
from typing import Any

import cv2

VISION_REPORTS_DIR = Path(__file__).resolve().parents[1] / "vision_outputs"


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


# TODO ver si encontramos alguno de los motores de renderizado de un browser open sourced

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
    """Save the rendered image and description as one self-contained HTML file."""
    report_dir = Path(output_dir).expanduser()
    if not report_dir.is_absolute():
        report_dir = Path(__file__).resolve().parents[1] / report_dir
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
