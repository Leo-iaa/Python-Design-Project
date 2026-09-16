from io import BytesIO
from pathlib import Path

from PIL import Image

from advanced_file_finder.core.ocr.engine import prepare_image_for_ocr


def test_large_images_are_downscaled_in_memory(tmp_path: Path) -> None:
    image_path = tmp_path / "large.png"
    Image.new("RGB", (4000, 2000), "white").save(image_path)

    payload = prepare_image_for_ocr(image_path, 2560)
    with Image.open(BytesIO(payload)) as prepared:
        assert prepared.size == (2560, 1280)
    assert not (tmp_path / "large_ocr.png").exists()


def test_small_images_keep_dimensions_and_exif_orientation(tmp_path: Path) -> None:
    image_path = tmp_path / "small.jpg"
    image = Image.new("RGB", (100, 50), "white")
    exif = image.getexif()
    exif[274] = 6
    image.save(image_path, exif=exif)

    payload = prepare_image_for_ocr(image_path, 2560)
    with Image.open(BytesIO(payload)) as prepared:
        assert prepared.size == (50, 100)


def test_preprocessing_rejects_invalid_limit(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    Image.new("RGB", (10, 10), "white").save(image_path)

    try:
        prepare_image_for_ocr(image_path, 0)
    except ValueError as error:
        assert "max_long_edge" in str(error)
    else:
        raise AssertionError("expected ValueError")