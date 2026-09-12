"""Test conservative Gutenberg cleaning behavior."""

import hashlib
import unittest

from gutenberg_cleaner import (
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


class BoundaryTests(unittest.TestCase):
    """Test strict Gutenberg boundary handling."""

    def test_removes_prefix_marker_suffix_and_marker(self):
        book = make_book("Title\n\nBody", "Header", "License")

        self.assertEqual(simple_cleaner(book), "Title\n\nBody")

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

        self.assertEqual(super_cleaner(book), "Body")

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

        self.assertEqual(super_cleaner(book), "Body")

    def test_rejects_an_unresolved_boundary(self):
        with self.assertRaises(UnresolvedBoundaryError) as context:
            clean_book("Header\nBody without official markers")

        self.assertEqual(context.exception.missing_markers, ("start", "end"))
        self.assertEqual(
            context.exception.metadata["boundary_status"], "unresolved"
        )

    def test_extracts_metadata_for_an_unresolved_boundary(self):
        book = "Title: Test Book\nRelease Date: Today [EBook #123]\nBody"

        with self.assertRaises(UnresolvedBoundaryError) as context:
            clean_book(book)

        self.assertEqual(context.exception.metadata["title"], "Test Book")
        self.assertEqual(context.exception.metadata["gutenberg_id"], "123")

    def test_ignores_start_marker_after_line_600(self):
        book = "\n".join(["Header"] * 600 + [START, "Body", END])

        with self.assertRaises(UnresolvedBoundaryError) as context:
            super_cleaner(book)

        self.assertIn("start", context.exception.missing_markers)


class NormalizationTests(unittest.TestCase):
    """Test safe text normalization."""

    def test_normalizes_characters_lines_and_blank_runs(self):
        body = (
            "Cafe\u0301\r\nsoft\u00adhyphen\u200b  \r\n"
            "\x00text\r\n\r\n\r\n\r\nEnd"
        )
        book = make_book(body).encode("utf-8")

        cleaned = super_cleaner(book)

        self.assertEqual(cleaned, "Café\nsofthyphen\ntext\n\n\nEnd")

    def test_rejects_invalid_utf8(self):
        with self.assertRaises(UnicodeDecodeError):
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

        self.assertIn("reflow. The next", cleaned)
        self.assertIn(verse, cleaned)
        self.assertIn(table, cleaned)


class PreservationTests(unittest.TestCase):
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
            self.assertIn(paragraph, cleaned)
        self.assertNotIn("[deleted]", cleaned)

    def test_removes_only_bare_image_placeholders(self):
        body = (
            "[Illustration: image023.jpg]\n\n"
            "[Illustration: A map of London in 1720.]"
        )

        cleaned = super_cleaner(make_book(body))

        self.assertNotIn("image023.jpg", cleaned)
        self.assertIn("A map of London in 1720.", cleaned)

    def test_ignores_legacy_token_limits(self):
        body = "A valid short line.\n\n" + "word " * 700

        cleaned = super_cleaner(make_book(body), min_token=100, max_token=2)

        self.assertIn("A valid short line.", cleaned)
        self.assertGreater(len(cleaned.split()), 700)

    def test_keeps_symbol_guidance_and_removes_correction_log(self):
        filler = "\n".join("Story line " + str(index) for index in range(30))
        correction_log = (
            "TRANSCRIBER'S NOTE\nObvious typographical errors were corrected."
        )
        symbol_note = "TRANSCRIBER'S NOTE\nAn asterisk represents italic text."

        cleaned_log = super_cleaner(make_book(filler + "\n" + correction_log))
        cleaned_symbols = super_cleaner(make_book(filler + "\n" + symbol_note))

        self.assertNotIn("typographical", cleaned_log)
        self.assertIn("asterisk represents italic text", cleaned_symbols)


class RemovalAndMetadataTests(unittest.TestCase):
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

        self.assertEqual(result.text.count("CHAPTER I\n"), 1)
        self.assertNotIn("CONTENTS", result.text)
        self.assertEqual(
            result.removed_sections[0]["type"], "table_of_contents"
        )

    def test_keeps_a_contents_heading_without_duplicate_evidence(self):
        body = (
            "CONTENTS\n\nHow to use this reference work.\n\n"
            "Entries follow alphabetically."
        )

        self.assertIn("CONTENTS", super_cleaner(make_book(body)))

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

        self.assertEqual(result.metadata["gutenberg_id"], "123")
        self.assertEqual(result.metadata["title"], "Test Book")
        self.assertEqual(result.metadata["authors"], ["Jane Doe"])
        self.assertEqual(result.metadata["language"], "English")
        self.assertEqual(
            result.metadata["source_url"],
            "https://www.gutenberg.org/ebooks/123",
        )
        self.assertEqual(result.metadata["cleaner_version"], CLEANER_VERSION)
        self.assertEqual(
            result.metadata["raw_sha256"],
            hashlib.sha256(book.encode()).hexdigest(),
        )
        self.assertIn("Title: Test Book", result.removed_prefix)
        self.assertIn("License", result.removed_suffix)
        self.assertEqual(result.text.count("Test Book"), 1)
        self.assertTrue(result.text.startswith("Test Book\nBy Jane Doe"))

    def test_moves_production_credits_to_audit_output(self):
        body = (
            "Produced by Jane Doe and Distributed Proofreaders\n\n"
            "TEST BOOK\n\nBody"
        )

        result = clean_book(make_book(body))

        self.assertNotIn("Produced by", result.text)
        self.assertEqual(
            result.removed_sections[0]["type"], "production_credits"
        )
        self.assertIn("Produced by", result.removed_sections[0]["text"])
        self.assertEqual(
            result.metadata["production_credits"],
            ["Produced by Jane Doe and Distributed Proofreaders"],
        )

    def test_adds_missing_title_and_author_headings(self):
        prefix = (
            "Title: Test Book\nAuthor: Jane Doe\n"
            "Release Date: Today [EBook #123]"
        )

        cleaned = super_cleaner(make_book("CHAPTER I\n\nBody", prefix))

        self.assertTrue(
            cleaned.startswith("Test Book\nBy Jane Doe\n\nCHAPTER I")
        )

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

        self.assertNotIn("INDEX", result.text)
        self.assertEqual(result.removed_sections[0]["type"], "index")

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

        self.assertNotIn("ADVERTISEMENTS", result.text)
        self.assertEqual(
            result.removed_sections[0]["type"], "publisher_advertisements"
        )


if __name__ == "__main__":
    unittest.main()
