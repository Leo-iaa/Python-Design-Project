"""Local OCR engine abstraction backed by RapidOCR."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str
    confidence: float = 0.0
    engine_name: str = "rapidocr"
    engine_version: str = "1.4.4"


class OcrEngine:
    """Protocol-like base for replaceable local OCR engines."""

    def recognize(self, image_path: Path) -> OcrResult:
        raise NotImplementedError


def prepare_image_for_ocr(image_path: Path, max_long_edge: int | None = 2560) -> bytes:
    """Normalize orientation and downscale oversized images in memory."""
    if max_long_edge is not None and max_long_edge <= 0:
        raise ValueError("max_long_edge must be positive or None")
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source)
        if max_long_edge is not None and max(image.size) > max_long_edge:
            ratio = max_long_edge / max(image.size)
            image = image.resize(
                (max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
                Image.Resampling.LANCZOS,
            )
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        output = BytesIO()
        image.save(output, format="PNG")
    return output.getvalue()


class RapidOcrEngine(OcrEngine):
    """Lazy RapidOCR wrapper with conservative in-memory preprocessing."""

    def __init__(self, max_long_edge: int | None = 2560) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self.max_long_edge = max_long_edge
        self._engine = RapidOCR()

    def recognize(self, image_path: Path) -> OcrResult:
        output, _ = self._engine(prepare_image_for_ocr(image_path, self.max_long_edge))
        if not output:
            return OcrResult("")
        text = " ".join(str(row[1]) for row in output if len(row) > 1)
        confidence = sum(float(row[2]) for row in output if len(row) > 2) / len(output)
        return OcrResult(text, confidence)