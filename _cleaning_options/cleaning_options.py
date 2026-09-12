"""Provide compatible checks for earlier package users."""

import re


_BARE_IMAGE = re.compile(
    r"^\s*\[(?:illustration|image)(?::\s*(?:image)?[\w.-]+"
    r"(?:\.(?:png|jpe?g|gif|tiff?|bmp))?)?\]\s*$",
    re.IGNORECASE,
)


def _is_title_or_etc(text: str, min_token: int = 5, max_token: int = 600) -> bool:
    """Identify an empty paragraph without classifying valid short text."""
    del min_token, max_token
    return not text.strip()


def _is_table(text: str) -> bool:
    """Keep tables because they contain valid book content."""
    del text
    return False


def _is_image(text: str) -> bool:
    """Identify a bare image placeholder without a caption."""
    return bool(_BARE_IMAGE.match(text))


def _is_footnote(text: str) -> bool:
    """Keep footnotes because they contain valid book content."""
    del text
    return False


def _is_books_copy(text: str) -> bool:
    """Keep copyright text when no source section identifies it."""
    del text
    return False


def _is_email_init(text: str) -> bool:
    """Keep email addresses when no source section identifies them."""
    del text
    return False
