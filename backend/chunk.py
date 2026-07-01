import re


def chunk_general(
    text: str,
    *,
    min_chunk_chars: int = 80,
    max_chunk_chars: int = 2000,
) -> list[str]:
    """
    Split file content into chunks by paragraph for focused retrieval.

    - .md: split by ## / ### headers; fallback to paragraphs
        also removes yaml frontmatter
    - .py: split by top-level def/class definitions
    - .txt / other: split by double-newline paragraphs
    """
    content = text.strip()
    if not content:
        return []

    def _merge_small(chunks: list[str]) -> list[str]:
        """Merge chunks smaller than min_chunk_chars with the next chunk."""
        out: list[str] = []
        buf = ""
        for c in chunks:
            c = c.strip()
            if not c:
                continue
            if (
                buf
                and len(buf) < min_chunk_chars
                and len(buf) + len(c) <= max_chunk_chars
            ):
                buf = f"{buf}\n\n{c}"
            else:
                if buf:
                    out.append(buf)
                buf = c
        if buf:
            out.append(buf)
        return out

    def _split_large(chunks: list[str]) -> list[str]:
        """Split chunks larger than max_chunk_chars by paragraphs."""
        out: list[str] = []
        for c in chunks:
            if len(c) <= max_chunk_chars:
                out.append(c)
                continue
            parts = re.split(r"\n\n+", c)
            buf = ""
            for p in parts:
                if buf and len(buf) + len(p) + 2 <= max_chunk_chars:
                    buf = f"{buf}\n\n{p}"
                else:
                    if buf:
                        out.append(buf)
                    buf = p
            if buf:
                out.append(buf)
        return out

    chunks: list[str] = []

    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            content = content[end + 4 :].strip()  # removing YAML frontmatter
    parts = re.split(r"(?=^#{2,3}\s+.+$)", content, flags=re.MULTILINE)
    for p in parts:
        p = p.strip()
        if p:
            chunks.append(p)
    if not chunks:
        chunks = re.split(r"\n\n+", content)

    chunks = [c.strip() for c in chunks if c.strip()]
    chunks = _merge_small(chunks)
    chunks = _split_large(chunks)
    result = [c for c in chunks if len(c) >= min_chunk_chars]
    if not result and content.strip():
        return [content.strip()]
    return result


def chunk_docs(
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
