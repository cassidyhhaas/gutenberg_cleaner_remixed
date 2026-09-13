"""Test conservative Gutenberg cleaning behavior."""

import hashlib

import pytest

from gutenberg_cleaner_remixed import (
    CLEANER_VERSION,
    UnresolvedBoundaryError,
    clean_book,
    simple_cleaner,
    super_cleaner,
)


START = "*** START OF THE PROJECT GUTENBERG EBOOK TEST BOOK ***"
END = "*** END OF THE PROJECT GUTENBERG EBOOK TEST BOOK ***"


def make_book(body, prefix="", suffix=""):
    """Add Gutenberg boundary sections to test text."""
    return "\n".join((prefix, START, body, END, suffix))


class TestBoundaries:
    """Test strict Gutenberg boundary handling."""

    def test_removes_prefix_marker_suffix_and_marker(self):
        book = make_book("Title\n\nBody", "Header", "License")

        assert simple_cleaner(book) == "Title\n\nBody"

    def test_accepts_this_project_and_old_spacing(self):
        book = "\n".join(
            (
                "Header",
                "***START OF THIS PROJECT GUTENBERG ETEXT TEST***",
                "Body",
                "***END OF THIS PROJECT GUTENBERG ETEXT TEST***",
                "License",
            )
        )

        assert super_cleaner(book) == "Body"

    def test_accepts_constrained_older_markers(self):
        book = "\n".join(
            (
                "Header",
                "*END*THE SMALL PRINT",
                "Body",
                "End of Project Gutenberg",
                "License",
            )
        )

        assert super_cleaner(book) == "Body"

    def test_rejects_an_unresolved_boundary(self):
        with pytest.raises(UnresolvedBoundaryError) as context:
            clean_book("Header\nBody without official markers")

        assert context.value.missing_markers == ("start", "end")
        assert context.value.metadata["boundary_status"] == "unresolved"

    def test_extracts_metadata_for_an_unresolved_boundary(self):
        book = "Title: Test Book\nRelease Date: Today [EBook #123]\nBody"

        with pytest.raises(UnresolvedBoundaryError) as context:
            clean_book(book)

        assert context.value.metadata["title"] == "Test Book"
        assert context.value.metadata["gutenberg_id"] == "123"

    def test_ignores_start_marker_after_line_600(self):
        book = "\n".join(["Header"] * 600 + [START, "Body", END])

        with pytest.raises(UnresolvedBoundaryError) as context:
            super_cleaner(book)

        assert "start" in context.value.missing_markers


class TestNormalization:
    """Test safe text normalization."""

    def test_normalizes_characters_lines_and_blank_runs(self):
        body = (
            "Cafe\u0301\r\nsoft\u00adhyphen\u200b  \r\n"
            "\x00text\r\n\r\n\r\n\r\nEnd"
        )
        book = make_book(body).encode("utf-8")

        cleaned = super_cleaner(book)

        assert cleaned == "Café\nsofthyphen\ntext\n\n\nEnd"

    def test_rejects_invalid_utf8(self):
        with pytest.raises(UnicodeDecodeError):
            super_cleaner(
                b"\xff" + START.encode() + b"\nBody\n" + END.encode()
            )

    def test_reflows_prose_and_preserves_structured_text(self):
        prose = (
            "This fixed-width prose line contains enough text for safe "
            "paragraph reflow.\n"
            "The next fixed-width prose line also contains enough text "
            "for reflow.\n"
            "The final line completes the paragraph."
        )
        verse = "The moon is high\nThe river is still\nNight holds its breath"
        table = (
            "Name   Count   Place\nJane   2       Bath\nJohn   4       York"
        )

        cleaned = super_cleaner(make_book("\n\n".join((prose, verse, table))))

        assert "reflow. The next" in cleaned
        assert verse in cleaned
        assert table in cleaned


class TestPreservation:
    """Test the content classes that the cleaner must preserve."""

    def test_preserves_book_content_classes(self):
        content = "\n\n".join(
            (
                "TEST BOOK",
                "CHAPTER I",
                "PREFACE",
                "For my family",
                "[1] This is an original footnote.",
                "APPENDIX A",
                "Name   Value\nAlpha  1",
                "[Illustration: A child reads beside the fire.]",
                "Original archaick spelling remaineth.",
            )
        )

        cleaned = super_cleaner(make_book(content))

        for paragraph in content.split("\n\n"):
            assert paragraph in cleaned
        assert "[deleted]" not in cleaned

    def test_removes_only_bare_image_placeholders(self):
        body = (
            "[Illustration: image023.jpg]\n\n"
            "[Illustration: A map of London in 1720.]"
        )

        cleaned = super_cleaner(make_book(body))

        assert "image023.jpg" not in cleaned
        assert "A map of London in 1720." in cleaned

    @pytest.mark.parametrize("argument", ["min_token", "max_token"])
    def test_rejects_legacy_token_limits(self, argument):
        book = make_book("Body")

        with pytest.raises(TypeError, match=argument):
            super_cleaner(book, **{argument: 1})

    def test_keeps_symbol_guidance_and_removes_correction_log(self):
        filler = "\n".join("Story line " + str(index) for index in range(30))
        correction_log = (
            "TRANSCRIBER'S NOTE\nObvious typographical errors were corrected."
        )
        symbol_note = "TRANSCRIBER'S NOTE\nAn asterisk represents italic text."

        cleaned_log = super_cleaner(make_book(filler + "\n" + correction_log))
        cleaned_symbols = super_cleaner(make_book(filler + "\n" + symbol_note))

        assert "typographical" not in cleaned_log
        assert "asterisk represents italic text" in cleaned_symbols


class TestRemovalAndMetadata:
    """Test duplicate sections, metadata, and audit output."""

    def test_removes_a_contents_section_only_when_headings_repeat(self):
        body = "\n".join(
            (
                "TEST BOOK",
                "",
                "CONTENTS",
                "CHAPTER I",
                "CHAPTER II",
                "CHAPTER III",
                "",
                "CHAPTER I",
                "First chapter text.",
                "",
                "CHAPTER II",
                "Second chapter text.",
                "",
                "CHAPTER III",
                "Third chapter text.",
            )
        )

        result = clean_book(make_book(body))

        assert result.text.count("CHAPTER I\n") == 1
        assert "CONTENTS" not in result.text
        assert result.removed_sections[0]["type"] == "table_of_contents"

    def test_keeps_a_contents_heading_without_duplicate_evidence(self):
        body = (
            "CONTENTS\n\nHow to use this reference work.\n\n"
            "Entries follow alphabetically."
        )

        assert "CONTENTS" in super_cleaner(make_book(body))

    def test_extracts_metadata_before_removal(self):
        prefix = "\n".join(
            (
                "Title: Test Book",
                "Author: Jane Doe",
                "Language: English",
                "Release Date: Today [EBook #123]",
                "Copyright Status: Public domain in the USA.",
            )
        )
        book = make_book("TEST BOOK\n\nBody", prefix, "License")

        result = clean_book(book)

        assert result.metadata["gutenberg_id"] == "123"
        assert result.metadata["title"] == "Test Book"
        assert result.metadata["authors"] == ["Jane Doe"]
        assert result.metadata["language"] == "English"
        assert result.metadata["source_url"] == (
            "https://www.gutenberg.org/ebooks/123"
        )
        assert result.metadata["cleaner_version"] == CLEANER_VERSION
        assert (
            result.metadata["raw_sha256"]
            == hashlib.sha256(book.encode()).hexdigest()
        )
        assert "Title: Test Book" in result.removed_prefix
        assert "License" in result.removed_suffix
        assert result.text.count("Test Book") == 1
        assert result.text.startswith("Test Book\nBy Jane Doe")

    def test_moves_production_credits_to_audit_output(self):
        body = (
            "Produced by Jane Doe and Distributed Proofreaders\n\n"
            "TEST BOOK\n\nBody"
        )

        result = clean_book(make_book(body))

        assert "Produced by" not in result.text
        assert result.removed_sections[0]["type"] == "production_credits"
        assert "Produced by" in result.removed_sections[0]["text"]
        assert result.metadata["production_credits"] == [
            "Produced by Jane Doe and Distributed Proofreaders"
        ]

    def test_adds_missing_title_and_author_headings(self):
        prefix = (
            "Title: Test Book\nAuthor: Jane Doe\n"
            "Release Date: Today [EBook #123]"
        )

        cleaned = super_cleaner(make_book("CHAPTER I\n\nBody", prefix))

        assert cleaned.startswith("Test Book\nBy Jane Doe\n\nCHAPTER I")

    def test_removes_a_terminal_page_reference_index(self):
        body = "\n".join(
            ["Main text."] * 30
            + [
                "INDEX",
                "Abbey, 2",
                "Bath, 4, 7",
                "Collins, 9",
                "Darcy, 10-12",
                "Elizabeth, 14",
            ]
        )

        result = clean_book(make_book(body))

        assert "INDEX" not in result.text
        assert result.removed_sections[0]["type"] == "index"

    def test_removes_terminal_publisher_advertisements(self):
        body = "\n".join(
            (
                "Main text.",
                "More text.",
                "More text.",
                "More text.",
                "More text.",
                "More text.",
                "More text.",
                "More text.",
                "ADVERTISEMENTS",
                "Fine cloth edition. Price $2.",
                "Published in London.",
            )
        )

        result = clean_book(make_book(body))

        assert "ADVERTISEMENTS" not in result.text
        assert result.removed_sections[0]["type"] == (
            "publisher_advertisements"
        )
