"""Extracts .tar.gz support bundles to a temporary directory.

Handles streaming extraction for bundles that may exceed 500MB,
ensuring files are never fully loaded into memory.
"""

import asyncio
import shutil
import tarfile
import tempfile
from pathlib import Path
from types import TracebackType

from loguru import logger


class BundleExtractor:
    """Stream-extracts tar.gz support bundles to a temporary directory.

    Supports async context manager for automatic cleanup of extracted files.
    Never loads the full archive into RAM -- streams members one at a time.

    Usage::

        async with BundleExtractor() as extractor:
            root = await extractor.extract(Path("bundle.tar.gz"))
            # work with root ...
        # temp directory cleaned up automatically
    """

    def __init__(self) -> None:
        self._temp_dirs: list[Path] = []

    async def extract(
        self, bundle_path: Path, dest: Path | None = None
    ) -> Path:
        """Stream-extract a tar.gz bundle to *dest* (or a temp directory).

        Args:
            bundle_path: Path to the .tar.gz bundle file.
            dest: Optional destination directory.  A temp directory is created
                  when *dest* is ``None``.

        Returns:
            Path to the root of the extracted bundle.  If the archive contains
            a single top-level directory (common for support bundles), that
            directory is returned instead of the raw extraction target.

        Raises:
            FileNotFoundError: If *bundle_path* does not exist.
            tarfile.TarError: If the file is not a valid tar archive.
        """
        bundle_path = Path(bundle_path).resolve()
        if not bundle_path.exists():
            raise FileNotFoundError(f"Bundle not found: {bundle_path}")

        if dest is None:
            dest = Path(tempfile.mkdtemp(prefix="bundle_analyzer_"))
            self._temp_dirs.append(dest)
        else:
            dest = Path(dest).resolve()
            dest.mkdir(parents=True, exist_ok=True)

        logger.info("Extracting bundle {} -> {}", bundle_path, dest)

        # Run the blocking tar extraction in a thread pool so we don't
        # block the event loop.
        await asyncio.to_thread(self._extract_sync, bundle_path, dest)

        # Support bundles often contain a single top-level directory.
        # Unwrap it so callers don't need to guess.
        root = self._unwrap_root(dest)
        logger.info("Bundle root resolved to {}", root)
        return root

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _extract_sync(bundle_path: Path, dest: Path) -> None:
        """Blocking extraction that streams members one at a time."""
        open_mode = "r:gz" if bundle_path.suffix == ".gz" or bundle_path.name.endswith(".tar.gz") else "r:*"
        with tarfile.open(bundle_path, open_mode) as tar:
            # Security: filter out absolute paths and path traversals.
            for member in tar:
                # Skip absolute or traversal paths
                if member.name.startswith("/") or ".." in member.name:
                    logger.warning(
                        "Skipping potentially unsafe tar member: {}",
                        member.name,
                    )
                    continue
                tar.extract(member, path=dest, filter="data")

    @staticmethod
    def _unwrap_root(dest: Path) -> Path:
        """If *dest* contains a single sub-directory, return it."""
        children = [p for p in dest.iterdir() if p.is_dir()]
        if len(children) == 1:
            return children[0]
        return dest

    # -- context manager ----------------------------------------------------

    async def __aenter__(self) -> "BundleExtractor":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.cleanup()

    async def cleanup(self) -> None:
        """Remove all temporary directories created during extraction."""
        for tmp in self._temp_dirs:
            if tmp.exists():
                logger.debug("Cleaning up temp dir {}", tmp)
                await asyncio.to_thread(shutil.rmtree, tmp, ignore_errors=True)
        self._temp_dirs.clear()
