# Gutenberg Cleaner

This package cleans Project Gutenberg plain-text books. It uses conservative rules that preserve authored content.

## Behavior

The cleaner performs these operations:

1. Decode bytes as UTF-8 without replacement characters.
2. Normalize Unicode to NFC and use `\n` line endings.
3. Remove text outside official Gutenberg boundary markers.
4. Remove clear production noise and duplicate navigation sections.
5. Preserve headings, notes, tables, verse, dialogue, and descriptive captions.

The cleaner raises `UnresolvedBoundaryError` when a boundary marker is missing. Send these files to an exclusion or quarantine output.

## Install

```console
pip install .
```

The package has no runtime dependencies.

## Clean text

Use `simple_cleaner` for boundary removal and safe normalization.

```python
from gutenberg_cleaner import simple_cleaner

cleaned_text = simple_cleaner(raw_book)
```

Use `super_cleaner` for conservative content cleaning.

```python
from gutenberg_cleaner import super_cleaner

cleaned_text = super_cleaner(raw_book)
```

The old `min_token` and `max_token` arguments remain compatible. The cleaner ignores them because token limits can remove valid book content.

## Get metadata and audit text

Use `clean_book` when the pipeline needs metadata or removed text.

```python
from gutenberg_cleaner import clean_book

result = clean_book(raw_book)
cleaned_text = result.text
metadata = result.metadata
header_audit = result.removed_prefix
footer_audit = result.removed_suffix
section_audit = result.removed_sections
```

The metadata includes these fields:

- `gutenberg_id`
- `title`
- `authors`
- `language`
- `source` and `source_url`
- `rights_statement`
- `raw_sha256`
- `cleaner_version`
- `boundary_status`
- `production_credits`, when present

## Test

```console
python -B -m unittest discover -v
```

## License

This project uses the MIT License. See [LICENSE.md](LICENSE.md).
