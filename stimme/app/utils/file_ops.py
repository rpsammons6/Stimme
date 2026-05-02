"""
Atomic file write utility for crash-safe persistence.

Writes content to a temporary file in the same directory as the target,
then renames it atomically to prevent partial writes on crash.
"""

import os
import tempfile
from pathlib import Path


def atomic_write(target: Path, content: str | bytes, encoding: str = "utf-8") -> None:
    """Write content to target via temp-file-then-rename.

    1. Write to a NamedTemporaryFile in the same directory as target
    2. Flush and fsync
    3. os.replace(tmp, target) — atomic on POSIX, near-atomic on Windows

    On failure at any step, the temp file is cleaned up and the
    original exception is re-raised.

    Args:
        target: Destination file path.
        content: String or bytes to write.
        encoding: Encoding for string content (ignored for bytes).

    Raises:
        OSError: If the write or rename fails (after temp cleanup).
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    mode = "wb" if isinstance(content, bytes) else "w"
    kwargs = {} if isinstance(content, bytes) else {"encoding": encoding}

    tmp_fd = tempfile.NamedTemporaryFile(
        mode=mode,
        dir=target.parent,
        delete=False,
        **kwargs,
    )
    tmp_path = Path(tmp_fd.name)

    try:
        tmp_fd.write(content)
        tmp_fd.flush()
        os.fsync(tmp_fd.fileno())
        tmp_fd.close()
        os.replace(tmp_path, target)
    except BaseException:
        tmp_fd.close()
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
