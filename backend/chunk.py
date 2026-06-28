import re


def chunk(
    text: str,
    min_chunk_chars: int = 2,
    max_chunk_chars: int = 8000,
    overlap_chars: int = 100,
) -> tuple[list[str], list[str]]:
    """
    Splits text into paragraph chunks and code block chunks separately.

    - Code blocks (markdown,mediawiki and html) are extracted first and never appear in paragraph chunks.
    - Paragraph chunks are built from the remaining text, split on blank lines,
      merged until max_chunk_chars, and overlapped by overlap_chars.
    - Chunks below min_chunk_chars are merged with the next chunk.

    Returns (paragraph_chunks, code_chunks).
    """

    code_patterns = re.compile(
        r"(?:"
        r"```[\s\S]*?```"  # markdown
        r"|<pre[^>]*>[\s\S]*?</pre>"  # html <pre>
        # r"|<code[^>]*>[\s\S]*?</code>"  # only for inline code tags
        r"|<syntaxhighlight[^>]*>[\s\S]*?</syntaxhighlight>"  # mediawiki syntaxhighlight
        r"|<source[^>]*>[\s\S]*?</source>"  # mediawiki <source> (deprecated but common)
        r")",
        re.MULTILINE | re.IGNORECASE,
    )
    code_chunks: list[str] = []

    def _replace_code(match: re.Match) -> str:
        code_chunks.append(match.group(0).strip())
        return " "

    stripped_text = code_patterns.sub(_replace_code, text)

    prose_paragraphs = [p.strip() for p in re.split(r"\n\s*\n", stripped_text) if p]

    merged: list[str] = []
    current = ""

    for para in prose_paragraphs:
        if not current:
            current = para
            continue

        combined = current + "\n\n" + para
        if len(combined) <= max_chunk_chars:
            current = combined
        else:
            if len(current) >= min_chunk_chars:
                merged.append(current)
                current = para
            else:
                # current is too short; force-combine anyway
                current = combined

    if current:
        merged.append(current)

    # split any chunk that still exceeds max_chunk_chars
    def _hard_split(chunk_text: str) -> list[str]:
        parts = []
        while len(chunk_text) > max_chunk_chars:
            parts.append(chunk_text[:max_chunk_chars])
            chunk_text = chunk_text[max_chunk_chars:]
        if chunk_text:
            parts.append(chunk_text)
        return parts

    split_chunks: list[str] = []
    for c in merged:
        split_chunks.extend(_hard_split(c))

    # apply overlap between consecutive chunks
    paragraph_chunks: list[str] = []

    for i, c in enumerate(split_chunks):
        if i == 0 or overlap_chars <= 0:
            paragraph_chunks.append(c)
        else:
            prev = split_chunks[i - 1]
            overlap_text = prev[-overlap_chars:]
            combined = overlap_text + "\n\n" + c
            # If combining pushes over max, hard-split and keep last part
            if len(combined) > max_chunk_chars:
                combined = combined[-max_chunk_chars:]
            paragraph_chunks.append(combined)

    # exterminate any chunks that fell below min_chunk_chars after all processing
    paragraph_chunks = [c for c in paragraph_chunks if len(c) >= min_chunk_chars]
    return paragraph_chunks, code_chunks
