"""Run a local, privacy-preserving OCR acceptance test over a user directory."""

import argparse
import json
import statistics
import time
from pathlib import Path

from advanced_file_finder.core.ocr.cache import IMAGE_EXTENSIONS
from advanced_file_finder.core.ocr.engine import RapidOcrEngine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--include-text", action="store_true")
    args = parser.parse_args()
    images = [
        p
        for p in args.directory.rglob("*")
        if p.is_file() and p.suffix.casefold() in IMAGE_EXTENSIONS
    ]
    engine = RapidOcrEngine()
    rows = []
    for image in images:
        started = time.perf_counter()
        try:
            result = engine.recognize(image)
            row = {
                "filename": image.name,
                "elapsed": time.perf_counter() - started,
                "success": True,
                "characters": len(result.text),
                "error": "",
            }
            if args.include_text:
                row["text"] = result.text
        except (OSError, RuntimeError, ValueError) as error:
            row = {
                "filename": image.name,
                "elapsed": time.perf_counter() - started,
                "success": False,
                "characters": 0,
                "error": type(error).__name__,
            }
        rows.append(row)
    durations = [r["elapsed"] for r in rows]
    successes = sum(r["success"] for r in rows)
    reports = Path(__file__).resolve().parents[1] / ".local" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    summary = {
        "total_images": len(rows),
        "successful": successes,
        "failed": len(rows) - successes,
        "empty_text": sum(r["characters"] == 0 for r in rows),
        "total_characters": sum(r["characters"] for r in rows),
        "total_elapsed": sum(durations),
        "average_seconds": statistics.mean(durations) if durations else 0.0,
        "p50_seconds": statistics.median(durations) if durations else 0.0,
        "p95_seconds": statistics.quantiles(durations, n=20)[18]
        if len(durations) >= 2
        else (durations[0] if durations else 0.0),
        "slowest": max(rows, key=lambda r: r["elapsed"], default=None),
    }
    (reports / "ocr_acceptance_report.json").write_text(
        json.dumps({"summary": summary, "images": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# OCR Acceptance Report",
        "",
        f"- Images: {summary['total_images']}",
        f"- Successful: {summary['successful']}",
        f"- Failed: {summary['failed']}",
        f"- Empty text: {summary['empty_text']}",
        f"- Characters: {summary['total_characters']}",
        f"- Average: {summary['average_seconds']:.3f}s",
        f"- P50: {summary['p50_seconds']:.3f}s",
        f"- P95: {summary['p95_seconds']:.3f}s",
        f"- Slowest: {summary['slowest']['filename'] if summary['slowest'] else 'N/A'}",
    ]
    (reports / "ocr_acceptance_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
