"""Find and remove Project Gutenberg boundary sections."""

import re
from typing import NamedTuple, Optional


_START_MARKERS = (
    re.compile(
        r"^\s*\*{3,}\s*START\s+OF\s+(?:THE|THIS)\s+PROJECT\s+GUTENBERG"
        r"(?:\s+(?:EBOOK|ETEXT))?\b",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*\*?END\*?\s*THE\s+SMALL\s+PRINT!?\s*$", re.IGNORECASE),
    re.compile(
        r"^\s*BEGINNING\s+OF\s+(?:THE|THIS)\s+PROJECT\s+GUTENBERG\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*\*{3,}\s*START\s+OF\s+THE\s+COPYRIGHTED\b", re.IGNORECASE
    ),
)
_END_MARKERS = (
    re.compile(
        r"^\s*\*{3,}\s*END\s+OF\s+(?:THE|THIS)\s+PROJECT\s+GUTENBERG"
        r"(?:\s+(?:EBOOK|ETEXT))?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*END\s+OF\s+(?:(?:THE|THIS)\s+)?PROJECT\s+GUTENBERG\b",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*FIN\s+DE\s+PROJECT\s+GUTENBERG\b", re.IGNORECASE),
    re.compile(
        r"^\s*ENDE\s+DIESES?\s+PROJE(?:C|K)T\s+GUTENBERG\b", re.IGNORECASE
    ),
    re.compile(r"^\s*\*{3,}\s*END\s+OF\s+THE\s+COPYRIGHTED\b", re.IGNORECASE),
)


class BoundaryResult(NamedTuple):
    """Contain the text sections and the boundary state."""

    text: str
    removed_prefix: str
    removed_suffix: str
    boundary_status: str
    start_line: Optional[int]
    end_line: Optional[int]


class UnresolvedBoundaryError(ValueError):
    """Report a file that does not contain both Gutenberg markers."""

    def __init__(self, missing_markers, metadata=None):
        self.missing_markers = tuple(missing_markers)
        self.metadata = metadata or {}
        markers = " and ".join(self.missing_markers)
        label = "marker" if len(self.missing_markers) == 1 else "markers"
        message = "The cleaner cannot resolve the Gutenberg boundary."
        super().__init__(message + " Missing " + label + ": " + markers + ".")


def _split_headers(text: str) -> BoundaryResult:
    """Split text at official Gutenberg markers."""
    lines = text.split("\n")
    start_line = _find_start_marker(lines)
    end_line = _find_end_marker(lines, start_line)

    if start_line is None or end_line is None:
        return BoundaryResult(text, "", "", "unresolved", start_line, end_line)

    return BoundaryResult(
        text="\n".join(lines[start_line + 1 : end_line]),
        removed_prefix="\n".join(lines[: start_line + 1]),
        removed_suffix="\n".join(lines[end_line:]),
        boundary_status="resolved",
        start_line=start_line,
        end_line=end_line,
    )


def _strip_headers(text: str) -> str:
    """Remove text outside official Gutenberg markers."""
    result = _split_headers(text)
    if result.boundary_status == "unresolved":
        missing = []
        if result.start_line is None:
            missing.append("start")
        if result.end_line is None:
            missing.append("end")
        raise UnresolvedBoundaryError(missing)
    return result.text


def _find_start_marker(lines):
    """Find a start marker in the first 600 lines."""
    for line_number, line in enumerate(lines[:600]):
        if any(marker.match(line) for marker in _START_MARKERS):
            return line_number
    return None


def _find_end_marker(lines, start_line):
    """Find an end marker in the last part of the file."""
    search_size = max(600, (len(lines) + 4) // 5)
    search_start = max(0, len(lines) - search_size)
    if start_line is not None:
        search_start = max(search_start, start_line + 1)

    for line_number in range(len(lines) - 1, search_start - 1, -1):
        if any(marker.match(lines[line_number]) for marker in _END_MARKERS):
            return line_number
    return None
