"""Convert PDF and PPTX files to slide images.

PDF  — rendered directly via PyMuPDF (fitz).
PPTX — converted to PDF via LibreOffice headless, then rendered.
"""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)


class SlideConverter:
    """Converts presentation files to a list of PIL Images."""

    SUPPORTED_EXTENSIONS = {".pdf", ".pptx", ".ppt", ".odp"}

    @staticmethod
    def is_supported(file_path: str) -> bool:
        return Path(file_path).suffix.lower() in SlideConverter.SUPPORTED_EXTENSIONS

    @staticmethod
    def convert(file_path: str, dpi: int = 150) -> List[Image.Image]:
        """Convert a presentation file to a list of slide images.

        Args:
            file_path: Path to PDF, PPTX, PPT, or ODP file.
            dpi: Render resolution (default 150 — good balance of quality/size).

        Returns:
            List of PIL Images, one per slide.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If file type is unsupported.
            RuntimeError: If conversion fails.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = path.suffix.lower()
        if ext not in SlideConverter.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}")

        if ext == ".pdf":
            return SlideConverter._render_pdf(path, dpi)
        else:
            # PPTX/PPT/ODP → convert to PDF first via LibreOffice
            return SlideConverter._convert_via_libreoffice(path, dpi)

    @staticmethod
    def _render_pdf(pdf_path: Path, dpi: int) -> List[Image.Image]:
        """Render PDF pages to images using PyMuPDF."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError(
                "PyMuPDF is required for PDF rendering. "
                "Install with: pip install PyMuPDF"
            )

        images = []
        zoom = dpi / 72.0  # PDF default is 72 DPI
        mat = fitz.Matrix(zoom, zoom)

        try:
            doc = fitz.open(str(pdf_path))
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix = page.get_pixmap(matrix=mat)

                # Convert to PIL Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                images.append(img)

            doc.close()
            logger.info(f"Rendered {len(images)} pages from {pdf_path.name}")

        except Exception as e:
            raise RuntimeError(f"Failed to render PDF: {e}")

        return images

    @staticmethod
    def _convert_via_libreoffice(file_path: Path, dpi: int) -> List[Image.Image]:
        """Convert PPTX/PPT/ODP to PDF via LibreOffice, then render."""
        lo_bin = SlideConverter._find_libreoffice()
        if not lo_bin:
            raise RuntimeError(
                "LibreOffice is required to convert PowerPoint files. "
                "Install it or export your presentation as PDF first.\n\n"
                "Linux:   sudo apt install libreoffice-impress\n"
                "macOS:   brew install --cask libreoffice\n"
                "Windows: https://www.libreoffice.org/download/"
            )

        with tempfile.TemporaryDirectory(prefix="seenslide_") as tmpdir:
            logger.info(f"Converting {file_path.name} to PDF via LibreOffice...")

            try:
                result = subprocess.run(
                    [
                        lo_bin,
                        "--headless",
                        "--convert-to", "pdf",
                        "--outdir", tmpdir,
                        str(file_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError("LibreOffice conversion timed out (120s)")
            except FileNotFoundError:
                raise RuntimeError(f"LibreOffice binary not found: {lo_bin}")

            if result.returncode != 0:
                raise RuntimeError(
                    f"LibreOffice conversion failed:\n{result.stderr[:500]}"
                )

            # Find the generated PDF
            pdf_files = list(Path(tmpdir).glob("*.pdf"))
            if not pdf_files:
                raise RuntimeError("LibreOffice produced no PDF output")

            return SlideConverter._render_pdf(pdf_files[0], dpi)

    @staticmethod
    def _find_libreoffice() -> Optional[str]:
        """Find LibreOffice binary on the system."""
        import shutil
        import platform

        # Common binary names
        candidates = ["libreoffice", "soffice"]

        # Platform-specific paths
        system = platform.system()
        if system == "Darwin":
            candidates.append("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        elif system == "Windows":
            for prog in ["C:/Program Files/LibreOffice/program/soffice.exe",
                         "C:/Program Files (x86)/LibreOffice/program/soffice.exe"]:
                candidates.append(prog)

        for name in candidates:
            found = shutil.which(name)
            if found:
                return found
            if Path(name).exists():
                return name

        return None

    @staticmethod
    def get_slide_count(file_path: str) -> int:
        """Quick count of slides without full rendering.

        Args:
            file_path: Path to presentation file.

        Returns:
            Number of slides/pages.
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext == ".pdf":
            try:
                import fitz
                doc = fitz.open(str(path))
                count = len(doc)
                doc.close()
                return count
            except Exception:
                return 0
        else:
            # For PPTX, use python-pptx if available for quick count
            try:
                from pptx import Presentation
                prs = Presentation(str(path))
                return len(prs.slides)
            except Exception:
                return 0  # Unknown — will count after conversion
