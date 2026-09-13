"""Apply conservative cleaning rules to Project Gutenberg text."""

import hashlib
import re
import unicodedata
from collections import Counter
from typing import NamedTuple, NotRequired, Pattern, TypeAlias, TypedDict

from .strip_headers import (
    BoundaryResult,
    BoundaryStatus,
    UnresolvedBoundaryError,
    _split_headers,
)


CLEANER_VERSION = "0.1.0"

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_ZERO_WIDTH_CHARACTERS = re.compile(r"[\u200b-\u200f\u2060\ufeff]")
_BARE_IMAGE = re.compile(
    r"^\s*\[(?:illustration|image)(?::\s*(?:image)?[\w.-]+"
    r"(?:\.(?:png|jpe?g|gif|tiff?|bmp))?)?\]\s*$",
    re.IGNORECASE,
)
_DECORATED_PAGE = re.compile(
    r"^\s*(?:\[\s*(?:page|pg\.?)\s*\d+\s*\]|-\s*\d+\s*-|"
    r"(?:page|pg\.?)\s+\d+)\s*$",
    re.IGNORECASE,
)
_BARE_PAGE = re.compile(r"^\s*(\d{1,4})\s*$")
_SECTION_HEADING = re.compile(
    r"^(?:chapter|book|part|preface|introduction|foreword|prologue|section)\b",
    re.IGNORECASE,
)
_LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)]|[A-Za-z][.)])\s+")
_GUTENBERG_ID = re.compile(
    r"(?:ebook\s*#?\s*|etext\s*#?\s*|/ebooks/)(\d+)",
    re.IGNORECASE,
)
_SOURCE_URL = re.compile(
    r"https?://(?:www\.)?gutenberg\.org/\S+", re.IGNORECASE
)


class RemovedSection(TypedDict):
    """Describe one section that the cleaner removed."""

    type: str
    text: str


class Metadata(TypedDict):
    """Describe metadata that the cleaner extracts or creates."""

    gutenberg_id: str | None
    title: str | None
    authors: list[str]
    language: str | None
    source: str
    source_url: str | None
    rights_statement: str | None
    raw_sha256: str
    cleaner_version: str
    boundary_status: BoundaryStatus
    removed_sections: NotRequired[list[str]]
    production_credits: NotRequired[list[str]]


RemovalResult: TypeAlias = tuple[str, list[RemovedSection]]


class CleaningResult(NamedTuple):
    """Contain cleaned text, metadata, and removed audit text."""

    text: str
    metadata: Metadata
    removed_prefix: str
    removed_suffix: str
    removed_sections: list[RemovedSection]


def simple_cleaner(book: str | bytes) -> str:
    """Normalize text and remove Gutenberg boundary sections."""
    text, raw_bytes = _decode_book(book)
    del raw_bytes
    normalized = _normalize_text(text)
    boundary = _split_headers(normalized)
    _require_boundaries(boundary)
    return _normalize_spacing(boundary.text)


def clean_book(book: str | bytes) -> CleaningResult:
    """Clean one book and return its metadata and audit text."""
    text, raw_bytes = _decode_book(book)
    normalized = _normalize_text(text)
    boundary = _split_headers(normalized)
    metadata_prefix = (
        normalized
        if boundary.boundary_status == "unresolved"
        else boundary.removed_prefix
    )
    metadata_suffix = (
        ""
        if boundary.boundary_status == "unresolved"
        else boundary.removed_suffix
    )
    metadata = _extract_metadata(
        metadata_prefix,
        metadata_suffix,
        hashlib.sha256(raw_bytes).hexdigest(),
        boundary.boundary_status,
    )

    if boundary.boundary_status == "unresolved":
        missing: list[str] = []
        if boundary.start_line is None:
            missing.append("start")
        if boundary.end_line is None:
            missing.append("end")
        raise UnresolvedBoundaryError(missing, metadata)

    body = boundary.text
    removed_sections: list[RemovedSection] = []
    body, removed = _remove_production_credits(body)
    removed_sections.extend(removed)
    body, removed = _remove_duplicate_contents(body)
    removed_sections.extend(removed)
    body, removed = _remove_transcriber_log(body)
    removed_sections.extend(removed)
    body, removed = _remove_publisher_ads(body)
    removed_sections.extend(removed)
    body, removed = _remove_terminal_index(body)
    removed_sections.extend(removed)
    body = _remove_layout_artifacts(body)
    body = _ensure_title_heading(body, metadata)
    body = _reflow_prose(body)
    body = _normalize_spacing(body)

    if removed_sections:
        metadata["removed_sections"] = [
            section["type"] for section in removed_sections
        ]
    production_credits = [
        section["text"].strip()
        for section in removed_sections
        if section["type"] == "production_credits"
    ]
    if production_credits:
        metadata["production_credits"] = production_credits

    return CleaningResult(
        text=body,
        metadata=metadata,
        removed_prefix=boundary.removed_prefix,
        removed_suffix=boundary.removed_suffix,
        removed_sections=removed_sections,
    )


def super_cleaner(book: str | bytes) -> str:
    """Clean a book without deleting valid content classes."""
    return clean_book(book).text


def _decode_book(book: str | bytes) -> tuple[str, bytes]:
    """Decode bytes as UTF-8 without replacement characters."""
    if isinstance(book, bytes):
        return book.decode("utf-8", errors="strict"), book
    if not isinstance(book, str):
        raise TypeError("book must be str or bytes")
    return book, book.encode("utf-8")


def _normalize_text(text: str) -> str:
    """Apply safe character and line-ending normalization."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00ad", "")
    text = _ZERO_WIDTH_CHARACTERS.sub("", text)
    return _CONTROL_CHARACTERS.sub("", text)


def _normalize_spacing(text: str) -> str:
    """Remove trailing space and limit blank-line runs."""
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    output: list[str] = []
    blank_count = 0
    for line in lines:
        if line:
            blank_count = 0
            output.append(line)
            continue
        blank_count += 1
        if blank_count <= 2:
            output.append("")
    return "\n".join(output).strip()


def _require_boundaries(boundary: BoundaryResult) -> None:
    """Raise an error when a marker is missing."""
    if boundary.boundary_status == "resolved":
        return
    missing: list[str] = []
    if boundary.start_line is None:
        missing.append("start")
    if boundary.end_line is None:
        missing.append("end")
    raise UnresolvedBoundaryError(missing)


def _extract_metadata(
    prefix: str,
    suffix: str,
    raw_sha256: str,
    boundary_status: BoundaryStatus,
) -> Metadata:
    """Extract stable metadata before boilerplate removal."""
    metadata_text = prefix + "\n" + suffix
    title = _first_field(prefix, "title")
    authors = _all_fields(prefix, "author")
    language = _first_field(prefix, "language")
    identifier = _first_match(_GUTENBERG_ID, metadata_text)
    source_url = None
    if identifier:
        source_url = "https://www.gutenberg.org/ebooks/" + identifier
    else:
        source_url = _first_match(_SOURCE_URL, metadata_text)
        if source_url:
            source_url = source_url.rstrip(".,);]")

    return {
        "gutenberg_id": identifier,
        "title": title,
        "authors": authors,
        "language": language,
        "source": "Project Gutenberg",
        "source_url": source_url,
        "rights_statement": _extract_rights_statement(metadata_text),
        "raw_sha256": raw_sha256,
        "cleaner_version": CLEANER_VERSION,
        "boundary_status": boundary_status,
    }


def _first_field(text: str, field: str) -> str | None:
    """Return the first Gutenberg metadata field."""
    pattern = re.compile(
        r"^" + re.escape(field) + r":\s*(.+?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def _all_fields(text: str, field: str) -> list[str]:
    """Return all Gutenberg metadata fields with one name."""
    pattern = re.compile(
        r"^" + re.escape(field) + r":\s*(.+?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    return [match.strip() for match in pattern.findall(text)]


def _first_match(pattern: Pattern[str], text: str) -> str | None:
    """Return the first capture or full regular expression match."""
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1) if match.lastindex else match.group(0)


def _extract_rights_statement(text: str) -> str | None:
    """Return the most specific rights line."""
    field = _first_field(text, "copyright status") or _first_field(
        text, "rights"
    )
    if field:
        return field
    for line in text.split("\n"):
        lower = line.lower().strip()
        if (
            "not protected by u.s. copyright" in lower
            or "copyrighted project gutenberg" in lower
        ):
            return line.strip()
    return None


def _remove_production_credits(text: str) -> RemovalResult:
    """Remove explicit production credits near the book start."""
    parts = re.split(r"(\n{2,})", text)
    output: list[str] = []
    removed: list[RemovedSection] = []
    consumed_lines = 0
    for part_number in range(0, len(parts), 2):
        block = parts[part_number]
        separator = (
            parts[part_number + 1] if part_number + 1 < len(parts) else ""
        )
        lower = block.strip().lower()
        is_credit = consumed_lines <= 120 and (
            lower.startswith("produced by ")
            or lower.startswith("e-text prepared by ")
            or lower.startswith("this ebook was prepared by ")
            or "distributed proofread" in lower
            or "scanning acknowledg" in lower
        )
        if is_credit:
            removed.append({"type": "production_credits", "text": block})
        else:
            output.append(block)
            output.append(separator)
        consumed_lines += block.count("\n") + separator.count("\n")
    return "".join(output), removed


def _remove_duplicate_contents(text: str) -> RemovalResult:
    """Remove a contents section only when later headings duplicate it."""
    lines = text.split("\n")
    search_limit = min(len(lines), max(400, len(lines) // 4))
    contents_line = next(
        (
            index
            for index, line in enumerate(lines[:search_limit])
            if line.strip().lower() in {"contents", "table of contents"}
        ),
        None,
    )
    if contents_line is None:
        return text, []

    keys = [_heading_key(line) for line in lines]
    candidate_limit = min(len(lines), contents_line + 300)
    pairs: list[tuple[int, int, str]] = []
    first_body_line = len(lines)
    for index in range(contents_line + 1, candidate_limit):
        if index >= first_body_line:
            break
        key = keys[index]
        if not _is_heading_key(key):
            continue
        try:
            later = keys.index(key, index + 1)
        except ValueError:
            continue
        pairs.append((index, later, key))
        first_body_line = min(first_body_line, later)

    unique_keys = {pair[2] for pair in pairs}
    later_lines = [pair[1] for pair in pairs]
    if len(unique_keys) < 3 or later_lines != sorted(later_lines):
        return text, []

    removed_text = "\n".join(lines[contents_line:first_body_line])
    kept = lines[:contents_line] + lines[first_body_line:]
    return "\n".join(kept), [
        {"type": "table_of_contents", "text": removed_text}
    ]


def _heading_key(line: str) -> str:
    """Normalize a possible heading for exact duplicate checks."""
    value = re.sub(r"\s+", " ", line.strip()).casefold()
    value = re.sub(r"\.{2,}\s*\d+\s*$", "", value).strip(" .")
    return value


def _is_heading_key(value: str) -> bool:
    """Identify a short line that can be a structural heading."""
    if not value or len(value) > 100 or len(value.split()) > 12:
        return False
    if value.endswith(("?", "!", ";")):
        return False
    return bool(_SECTION_HEADING.match(value)) or not value.endswith(".")


def _remove_terminal_index(text: str) -> RemovalResult:
    """Remove a final index only when entries contain page references."""
    lines = text.split("\n")
    start = max(0, len(lines) * 3 // 4)
    index_line = next(
        (
            index
            for index in range(start, len(lines))
            if lines[index].strip().lower() == "index"
        ),
        None,
    )
    if index_line is None:
        return text, []
    entries = [
        line.strip() for line in lines[index_line + 1 :] if line.strip()
    ]
    page_entries = [
        line
        for line in entries
        if len(line) < 180
        and re.search(r"(?:,|\.{2,}|\s)\s*\d+(?:[-–, ]+\d+)*\.?$", line)
    ]
    if len(entries) < 5 or len(page_entries) * 2 < len(entries):
        return text, []
    removed_text = "\n".join(lines[index_line:])
    return "\n".join(lines[:index_line]), [
        {"type": "index", "text": removed_text}
    ]


def _remove_publisher_ads(text: str) -> RemovalResult:
    """Remove a final publisher section only when sales terms occur."""
    lines = text.split("\n")
    start = max(0, len(lines) * 4 // 5)
    heading = re.compile(
        r"^(?:publisher(?:'s)? (?:advertisements|catalogue)|advertisements|"
        r"books by the same author)$",
        re.IGNORECASE,
    )
    ad_line = next(
        (
            index
            for index in range(start, len(lines))
            if heading.match(lines[index].strip())
        ),
        None,
    )
    if ad_line is None:
        return text, []
    section = "\n".join(lines[ad_line:])
    sales_terms = re.findall(
        r"\b(?:price|cloth|net|postage|publisher)\b|[$£]\s*\d|\d+s\.\s*\d+d\.",
        section,
        re.IGNORECASE,
    )
    if len(sales_terms) < 2:
        return text, []
    return "\n".join(lines[:ad_line]), [
        {"type": "publisher_advertisements", "text": section}
    ]


def _remove_transcriber_log(text: str) -> RemovalResult:
    """Remove a final correction log but keep symbol guidance."""
    lines = text.split("\n")
    start = max(0, len(lines) * 4 // 5)
    heading = re.compile(r"^transcriber(?:'s|s')? notes?:?$", re.IGNORECASE)
    note_line = next(
        (
            index
            for index in range(start, len(lines))
            if heading.match(lines[index].strip())
        ),
        None,
    )
    if note_line is None:
        return text, []
    section = "\n".join(lines[note_line:])
    lower = section.lower()
    symbol_terms = (
        "symbol",
        "denotes",
        "represents",
        "italic",
        "bold",
        "superscript",
        "small caps",
        "greek",
    )
    if any(term in lower for term in symbol_terms):
        return text, []
    production_terms = (
        "typographical",
        "punctuation",
        "spelling",
        "corrected",
        "changed from",
        "printer's error",
    )
    if not any(term in lower for term in production_terms):
        return text, []
    return "\n".join(lines[:note_line]), [
        {"type": "transcriber_correction_log", "text": section}
    ]


def _remove_layout_artifacts(text: str) -> str:
    """Remove image placeholders and confident page artifacts."""
    lines = text.split("\n")
    remove = {
        index
        for index, line in enumerate(lines)
        if _BARE_IMAGE.match(line) or _DECORATED_PAGE.match(line)
    }

    bare_pages: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = _BARE_PAGE.match(line)
        if match:
            bare_pages.append((index, int(match.group(1))))
    if _is_page_sequence(bare_pages):
        remove.update(index for index, value in bare_pages)

    neighbor_values: list[str] = []
    page_indexes = {
        index
        for index in remove
        if index < len(lines)
        and (
            _DECORATED_PAGE.match(lines[index])
            or _BARE_PAGE.match(lines[index])
        )
    }
    for page_index in page_indexes:
        for neighbor in (
            page_index - 2,
            page_index - 1,
            page_index + 1,
            page_index + 2,
        ):
            if 0 <= neighbor < len(lines):
                value = re.sub(r"\s+", " ", lines[neighbor].strip()).casefold()
                if 2 < len(value) <= 80 and not _SECTION_HEADING.match(value):
                    neighbor_values.append(value)
    repeated = {
        value
        for value, count in Counter(neighbor_values).items()
        if count >= 3
    }
    for index, line in enumerate(lines):
        value = re.sub(r"\s+", " ", line.strip()).casefold()
        if value in repeated and any(
            abs(index - page) <= 2 for page in page_indexes
        ):
            remove.add(index)

    return "\n".join(
        line for index, line in enumerate(lines) if index not in remove
    )


def _is_page_sequence(pages: list[tuple[int, int]]) -> bool:
    """Identify dispersed and increasing bare page numbers."""
    if len(pages) < 4:
        return False
    positions = [item[0] for item in pages]
    values = [item[1] for item in pages]
    if positions[-1] - positions[0] < len(pages) * 5:
        return False
    differences = [right - left for left, right in zip(values, values[1:])]
    return (
        all(value > 0 for value in differences)
        and sum(value == 1 for value in differences) * 4
        >= len(differences) * 3
    )


def _ensure_title_heading(text: str, metadata: Metadata) -> str:
    """Keep one exact title and author heading near the book start."""
    title = metadata["title"]
    authors = metadata["authors"]
    if not title and not authors:
        return text

    lines = text.split("\n")
    output: list[str] = []
    title_key = _line_key(title) if title else None
    author_keys = {_line_key(author) for author in authors}
    for index, line in enumerate(lines):
        value = _line_key(line)
        if index < 120 and title_key and value == title_key:
            continue
        if index < 120:
            author_key = value[3:] if value.startswith("by ") else value
            if author_key in author_keys:
                continue
        output.append(line)

    heading: list[str] = []
    if title:
        heading.append(title)
    if authors:
        heading.append("By " + " and ".join(authors))
    return "\n\n".join(("\n".join(heading), "\n".join(output).lstrip("\n")))


def _line_key(value: str) -> str:
    """Normalize one line for exact title-page comparisons."""
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _reflow_prose(text: str) -> str:
    """Reflow fixed-width prose and preserve structured text."""
    parts = re.split(r"(\n{2,})", text)
    return "".join(
        part if index % 2 else _reflow_block(part)
        for index, part in enumerate(parts)
    )


def _reflow_block(block: str) -> str:
    """Reflow one block only when its layout is prose."""
    lines = block.split("\n")
    nonempty = [line for line in lines if line]
    if len(nonempty) < 3:
        return block
    if any(
        line[:1].isspace() or "\t" in line or re.search(r"\S {2,}\S", line)
        for line in nonempty
    ):
        return block
    if any(_LIST_ITEM.match(line) for line in nonempty):
        return block
    if any(line.rstrip().endswith("-") for line in nonempty[:-1]):
        return block
    if (
        sum(
            line.lstrip().startswith(('"', "'", "—", "–")) for line in nonempty
        )
        > 1
    ):
        return block
    if (
        sum(len(line.rstrip()) >= 45 for line in nonempty[:-1]) * 4
        < (len(nonempty) - 1) * 3
    ):
        return block
    return " ".join(line.strip() for line in nonempty)
