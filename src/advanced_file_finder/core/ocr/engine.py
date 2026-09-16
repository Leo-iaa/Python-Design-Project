"""Local OCR engine abstraction backed by RapidOCR."""

from dataclasses import dataclass
from pathlib import Path


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


class RapidOcrEngine(OcrEngine):
    """Lazy RapidOCR wrapper; model initialization happens only on indexing."""

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()

    def recognize(self, image_path: Path) -> OcrResult:
        output, _ = self._engine(str(image_path))
        if not output:
            return OcrResult("")
        text = " ".join(str(row[1]) for row in output if len(row) > 1)
        confidence = sum(float(row[2]) for row in output if len(row) > 2) / len(output)
        return OcrResult(text, confidence)
