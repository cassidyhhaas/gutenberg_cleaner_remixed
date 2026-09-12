# AGENTS.md

Guidelines for AI agents working in this repository. Follow every rule below.

## Comments

- Add a comment only when it explains something the code cannot: intent,
  rationale, a constraint, or a non-obvious tradeoff.
- Comments explain **why**, not **what**. If a comment restates the code,
  delete it.
- Never write comments that narrate your edits ("Added validation",
  "Refactored per request") or changelog-style comments.
- Do not leave TODO comments for work you can complete now.

```python
# Bad: restates the code
# Loop through users and check status
for user in users:
    ...

# Good: explains a non-obvious reason
# Process in insertion order; the export format requires stable ordering.
for user in users:
    ...
```

## Documentation and technical writing

Write all documentation, docstrings, comments, and user-facing text
following ASD-STE100 (Simplified Technical English) principles:

- Keep sentences to 20 words or fewer (25 for descriptive text).
- Write one instruction per sentence.
- Use the active voice and the present tense.
- Use the imperative for instructions ("Run the tests", not "The tests
  should be run" or "Running the tests...").
- Use one meaning per word, and one word per meaning. Pick one term for a
  concept and use it consistently (e.g., always "start", never "begin" or
  "initiate" for the same action).
- Prefer short, simple words. Avoid jargon that a non-native reader would
  not know.

## No ticket references

- Never reference ticket numbers, issue IDs, or ticket URLs (e.g., JIRA-123)
  in code, comments, docstrings, or documentation.
- Reason: readers may not have access to the tracker, and ticket contents
  change after the reference is written.
- Instead, state the constraint or rationale directly in the text so it is
  self-contained.
- Exception: ticket IDs in branch names and commit messages are allowed.

```python
# Bad
# See PROJ-4521 for why we cap this.
MAX_RETRIES = 3

# Good
# External API rate-limits aggressively above 3 rapid retries.
MAX_RETRIES = 3
```
