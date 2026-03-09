"""Extract paper figures from arXiv source packages or PDF files."""

from __future__ import annotations

import logging
import shutil
import tarfile
import tempfile
from pathlib import Path

from paper_digest.http import HttpClientProtocol
from paper_digest.models import ImageAsset, ImageExtractionResult, PaperMetadata
from paper_digest.utils import ensure_directory

LOGGER = logging.getLogger(__name__)

SOURCE_FIGURE_DIRS = ["pics", "figures", "figure", "fig", "images", "img"]
SOURCE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg"}
DIRECT_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


class PaperImageExtractor:
    """Extract figures using arXiv source packages first, then fall back to the PDF."""

    def __init__(self, http_client: HttpClientProtocol):
        self._http = http_client

    def extract(
        self,
        *,
        metadata: PaperMetadata,
        pdf_path: Path | None,
        output_dir: Path,
    ) -> ImageExtractionResult:
        ensure_directory(output_dir)
        assets: list[ImageAsset] = []
        seen_names: set[str] = set()

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            if metadata.arxiv_id:
                self._extract_from_arxiv_source(
                    arxiv_id=metadata.arxiv_id,
                    temp_dir=temp_dir,
                    output_dir=output_dir,
                    assets=assets,
                    seen_names=seen_names,
                )

            if len(assets) < 3 and pdf_path is not None and pdf_path.exists():
                self._extract_from_pdf(
                    pdf_path=pdf_path,
                    output_dir=output_dir,
                    assets=assets,
                    seen_names=seen_names,
                )

        index_path = self._write_index(output_dir=output_dir, assets=assets)
        return ImageExtractionResult(assets=assets, index_path=index_path)

    def _extract_from_arxiv_source(
        self,
        *,
        arxiv_id: str,
        temp_dir: Path,
        output_dir: Path,
        assets: list[ImageAsset],
        seen_names: set[str],
    ) -> None:
        source_url = f"https://arxiv.org/e-print/{arxiv_id}"
        archive_path = temp_dir / f"{arxiv_id}.tar"
        try:
            archive_path.write_bytes(self._http.get_bytes(source_url))
        except Exception as error:
            LOGGER.debug("Could not download arXiv source for %s: %s", arxiv_id, error)
            return

        try:
            with tarfile.open(archive_path, "r:*") as tar:
                safe_members = [
                    member
                    for member in tar.getmembers()
                    if not member.name.startswith("/") and ".." not in member.name
                ]
                tar.extractall(path=temp_dir, members=safe_members)
        except tarfile.TarError as error:
            LOGGER.debug("Could not extract arXiv source for %s: %s", arxiv_id, error)
            return

        source_files = self._find_source_figures(temp_dir)
        for source_path in source_files:
            suffix = source_path.suffix.lower()
            if suffix == ".pdf":
                self._convert_pdf_figure(
                    figure_path=source_path,
                    output_dir=output_dir,
                    assets=assets,
                    seen_names=seen_names,
                )
            else:
                self._copy_asset(
                    source_path=source_path,
                    output_dir=output_dir,
                    assets=assets,
                    seen_names=seen_names,
                    source="arxiv-source",
                )

    def _extract_from_pdf(
        self,
        *,
        pdf_path: Path,
        output_dir: Path,
        assets: list[ImageAsset],
        seen_names: set[str],
    ) -> None:
        try:
            import fitz
        except ImportError:
            LOGGER.warning("PyMuPDF is not installed; skipping PDF figure extraction.")
            return

        with fitz.open(pdf_path) as document:
            for page_index in range(len(document)):
                page = document[page_index]
                for image_index, image in enumerate(page.get_images(full=True), start=1):
                    xref = image[0]
                    try:
                        base_image = document.extract_image(xref)
                    except Exception as error:
                        LOGGER.debug(
                            "Skipping PDF image extraction for page=%s xref=%s: %s",
                            page_index + 1,
                            xref,
                            error,
                        )
                        continue
                    extension = base_image.get("ext", "png")
                    filename = f"page{page_index + 1}_fig{image_index}.{extension}"
                    if filename in seen_names:
                        continue
                    target_path = output_dir / filename
                    target_path.write_bytes(base_image["image"])
                    seen_names.add(filename)
                    assets.append(
                        ImageAsset(
                            filename=filename,
                            relative_path=filename,
                            source="pdf-extraction",
                            ext=extension,
                            size_bytes=target_path.stat().st_size,
                        )
                    )

    @staticmethod
    def _find_source_figures(temp_dir: Path) -> list[Path]:
        found: list[Path] = []
        for figure_dir_name in SOURCE_FIGURE_DIRS:
            for figure_dir in temp_dir.rglob(figure_dir_name):
                if not figure_dir.is_dir():
                    continue
                for child in figure_dir.iterdir():
                    if child.is_file() and child.suffix.lower() in SOURCE_IMAGE_EXTENSIONS:
                        found.append(child)

        if found:
            return sorted(found)

        for child in temp_dir.iterdir():
            if child.is_file() and child.suffix.lower() in DIRECT_IMAGE_EXTENSIONS:
                found.append(child)
        return sorted(found)

    def _copy_asset(
        self,
        *,
        source_path: Path,
        output_dir: Path,
        assets: list[ImageAsset],
        seen_names: set[str],
        source: str,
    ) -> None:
        filename = source_path.name
        if filename in seen_names:
            return
        target_path = output_dir / filename
        shutil.copy2(source_path, target_path)
        seen_names.add(filename)
        assets.append(
            ImageAsset(
                filename=filename,
                relative_path=filename,
                source=source,
                ext=source_path.suffix.lstrip(".").lower(),
                size_bytes=target_path.stat().st_size,
            )
        )

    def _convert_pdf_figure(
        self,
        *,
        figure_path: Path,
        output_dir: Path,
        assets: list[ImageAsset],
        seen_names: set[str],
    ) -> None:
        try:
            import fitz
        except ImportError:
            return

        with fitz.open(figure_path) as document:
            for page_index in range(len(document)):
                pixmap = document[page_index].get_pixmap(dpi=150)
                filename = f"{figure_path.stem}_page{page_index + 1}.png"
                if filename in seen_names:
                    continue
                target_path = output_dir / filename
                pixmap.save(target_path)
                seen_names.add(filename)
                assets.append(
                    ImageAsset(
                        filename=filename,
                        relative_path=filename,
                        source="pdf-figure",
                        ext="png",
                        size_bytes=target_path.stat().st_size,
                    )
                )

    @staticmethod
    def _write_index(*, output_dir: Path, assets: list[ImageAsset]) -> Path:
        index_path = output_dir / "index.md"
        lines = ["# Extracted Figures", "", f"Total: {len(assets)}", ""]
        for asset in assets:
            lines.extend(
                [
                    f"## {asset.filename}",
                    f"- Source: {asset.source}",
                    f"- Path: {asset.relative_path}",
                    f"- Size: {asset.size_bytes} bytes",
                    "",
                ]
            )
        index_path.write_text("\n".join(lines), encoding="utf-8")
        return index_path
