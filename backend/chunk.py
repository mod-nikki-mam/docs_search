"""
provides different chunking algorithms for vecdbs
    chunk_general, mainly for .md,.txt or .py files
    chunk_json_discord,specialized chunking for discord chat extraction
"""

import re


def chunk_json_discord(
    content: str,
    *,
    min_chunk_chars: int = 100,
    time_gap_seconds: int | None = 60 * 4,
    max_chunk_chars: int = 4000,
) -> list[str]:
    """
    Split json file content into message chunks for focused retrieval.

    split by messages in a reply chain of multiple users,
    combine multiple messages into one if they come from one user near the same time
    send the user name as [User: username]: message so the model doesnt think its part of the convo
    """
    from datetime import datetime

    if not content:
        return []

    def contains_link(text) -> bool:
        # regex for urls(not perfect)
        url_pattern = r"(https?://[^\s]+)|(www\.[^\s]+)|([^\s]+\.(?:com|net|org|edu|gov|io|be|me)\b)"

        if re.search(url_pattern, text, re.IGNORECASE):
            return True
        return False

    def parse_time(msg) -> datetime:
        return datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00"))

    def ids_to_chunk(ids: list[str]) -> str:
        return "\n".join(msg_lookup[i] for i in ids if i in msg_lookup)

    msg_lookup = {
        msg["id"]: f"{msg['author']['name']} said:{msg['content']} \n"
        for msg in content["messages"]
        if not msg["author"]["isBot"]
        and not msg["content"] == ""
        or " "
        and not contains_link(msg["content"])
    }
    messages = [
        msg
        for msg in content["messages"]
        if not msg["author"]["isBot"]
        and not msg["content"] == ""
        or " "
        and not contains_link(msg["content"])
    ]

    chained_ids: set[str] = set()
    chains: list[list[str]] = []
    parent_to_chain: dict[str, int] = {}

    for msg in messages:
        if "reference" not in msg:
            continue
        msg_id = msg["id"]
        parent = msg["reference"]["messageId"]
        chained_ids.add(msg_id)
        chained_ids.add(parent)

        if parent in parent_to_chain:
            idx = parent_to_chain[parent]
            chains[idx].append(msg_id)
            parent_to_chain[msg_id] = idx
        else:
            idx = len(chains)
            chains.append([parent, msg_id])
            parent_to_chain[parent] = idx
            parent_to_chain[msg_id] = idx

    time_groups: list[list[str]] = []
    for msg in messages:
        msg_id = msg["id"]
        if msg_id in chained_ids:
            continue
        msg_time = parse_time(msg)
        if time_groups:
            last_id = time_groups[-1][-1]
            last_msg = next(m for m in messages if m["id"] == last_id)
            gap = (msg_time - parse_time(last_msg)).total_seconds()
            if gap <= time_gap_seconds:
                time_groups[-1].append(msg_id)
                continue
        time_groups.append([msg_id])

    chunks = [ids_to_chunk(g) for g in time_groups] + [ids_to_chunk(c) for c in chains]
    result = [c for c in chunks if len(c) >= min_chunk_chars]
    return result


def chunk_general(
    content: str,
    suffix: str,
    *,
    min_chunk_chars: int = 80,
    max_chunk_chars: int = 2000,
) -> list[str]:
    """
    Split file content into semantic chunks for focused retrieval.

    - .md: split by ## / ### headers; fallback to paragraphs
        also removes yaml frontmatter
    - .py: split by top-level def/class definitions
    - .txt / other: split by double-newline paragraphs
    """
    content = content.strip()
    if not content:
        return []
    suffix = (suffix or "").lower().lstrip(".")

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

    if suffix == "md":
        if content.startswith("---"):
            end = content.find("\n---", 3)
            if end != -1:
                content = content[end + 4 :].strip()
        parts = re.split(r"(?=^#{2,3}\s+.+$)", content, flags=re.MULTILINE)
        for p in parts:
            p = p.strip()
            if p:
                chunks.append(p)
        if not chunks:
            chunks = re.split(r"\n\n+", content)
    elif suffix == "py":
        parts = re.split(r"(?=^(?:def |class )\w)", content, flags=re.MULTILINE)
        for p in parts:
            p = p.strip()
            if p:
                chunks.append(p)
    else:
        chunks = []

    chunks = [c.strip() for c in chunks if c.strip()]
    chunks = _merge_small(chunks)
    chunks = _split_large(chunks)
    result = [c for c in chunks if len(c) >= min_chunk_chars]
    if not result and content.strip():
        return [content.strip()]
    return result
