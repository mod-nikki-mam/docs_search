from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, NamedTuple, Sequence
from uuid import uuid4

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest

from chunk import chunk


class SearchResult(NamedTuple):
    """A single result from similarity search."""

    id: int
    text: str
    score: float
    source: str | None = None

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return (
            f"SearchResult(id={self.id}, text={self.text!r}, "
            f"score={self.score:.3f}, source={self.source!r})"
        )


def normalize_roots(roots: str | Path | Sequence[str] | Sequence[Path]) -> list[Path]:
    if isinstance(roots, (str, Path)):
        return [Path(roots)]
    return [Path(p) for p in roots]


def normalize_glob_patterns(glob_patterns: str | Iterable[str]) -> list[str]:
    patterns = (
        [glob_patterns] if isinstance(glob_patterns, str) else list(glob_patterns)
    )
    patterns = [p.strip() for p in patterns if p and str(p).strip()]
    return patterns if patterns else ["*.md"]


def collect_file_paths(
    roots: str | Path | Iterable[str | Path],
    glob_patterns: str | Iterable[str] = "*.md",
) -> set[str]:
    """Collect absolute file paths matching glob patterns from roots."""
    path_roots = normalize_roots(roots)
    allowed_exts = {"md", "txt", "c", "lua", "typ", "sh", "json", "py"}

    raw_patterns = normalize_glob_patterns(glob_patterns)
    # keep only patterns whose extension is in the allow-list
    filtered = [
        p for p in raw_patterns if any(p.endswith(f".{ext}") for ext in allowed_exts)
    ]
    include_pats = [p for p in filtered if not p.startswith("!")]
    exclude_pats = [p[1:] for p in filtered if p.startswith("!")]
    if not include_pats:
        include_pats = [f"*.{ext}" for ext in allowed_exts]

    out: set[str] = set()
    for root in path_roots:
        root = root.resolve()
        for pat in include_pats:
            for match in root.rglob(pat):
                if match.is_file():
                    path_str = match.resolve().as_posix()
                    if not any(match.match(ex) for ex in exclude_pats):
                        out.add(path_str)
    return out


_DENSE_VECTOR = "dense"
_SPARSE_VECTOR = "sparse"
_SPARSE_MODEL = "Qdrant/bm42-all-minilm-l6-v2-attentions"


class VectorDB:
    """
    Vector database backed by Qdrant.

    db_path:
        `":memory:"` for an in-process store, or a directory path for
        on-disk persistence via Qdrant's local mode.
    url:
        If given, connects to a remote Qdrant server instead of local mode.
        Takes precedence over db_path.
    api_key:
        Bearer token for a remote Qdrant server.
    collection:
        Qdrant collection name.
    dims:
        Dense vector dimension; must match the embedding model.
    model:
        Dense embedding model name (fastembed).
    query_instruction:
        Prepended to queries for instruction-tuned embedders.
    cache_dir, parallel, batch_size:
        Passed to fastembed's TextEmbedding.
    """

    DEFAULT_MODEL = "nomic-ai/nomic-embed-text-v1.5"

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        *,
        url: str | None = None,
        api_key: str | None = None,
        collection: str = "embeddings",
        dims: int = 768,
        model: str | None = None,
        cache_dir: Path | None = None,
        parallel: int | None = None,
        query_instruction: str | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.collection = collection
        self.dims = dims
        self.model = model or self.DEFAULT_MODEL

        self._query_instruction = (
            query_instruction
            if query_instruction is not None
            else (
                "Retrieve passages that are semantically relevant to the search query. "
                "Prioritize meaning and context over exact keyword matches."
            )
        )

        #  Qdrant client
        if url:
            self._client = QdrantClient(url=url, api_key=api_key)
        elif str(db_path) == ":memory:":
            self._client = QdrantClient(":memory:")
        else:
            self._client = QdrantClient(path=str(db_path))

        #  Embedders
        embedder_kwargs: dict[str, Any] = {
            "model_name": self.model,
            "cache_dir": str(cache_dir) if cache_dir else None,
        }
        if parallel is not None:
            embedder_kwargs["parallel"] = parallel
        if batch_size is not None:
            embedder_kwargs["batch_size"] = batch_size

        self._dense_embedder = TextEmbedding(**embedder_kwargs)

        if hybrid:
            self._sparse_embedder = SparseTextEmbedding(
                model_name=_SPARSE_MODEL,
                cache_dir=str(cache_dir) if cache_dir else None,
            )
        else:
            self._sparse_embedder = None

        self._ensure_collection()

    # Internal helpers

    def _ensure_collection(self) -> None:
        """Create Qdrant collection if it does not already exist."""
        existing = {c.name for c in self._client.get_collections().collections}
        if self.collection in existing:
            return

        dense_config = rest.VectorParams(
            size=self.dims,
            distance=rest.Distance.COSINE,
            on_disk=False,
        )

        if self.hybrid:
            self._client.create_collection(
                collection_name=self.collection,
                vectors_config={_DENSE_VECTOR: dense_config},
                sparse_vectors_config={
                    _SPARSE_VECTOR: rest.SparseVectorParams(
                        modifier=rest.Modifier.IDF,
                    )
                },
            )
        else:
            self._client.create_collection(
                collection_name=self.collection,
                vectors_config={_DENSE_VECTOR: dense_config},
            )

    def _normalize_query(self, query: str) -> str:
        if not query or not query.strip():
            return " "
        return " ".join(query.strip().split())

    def _format_query(self, query: str) -> str:
        normalized = self._normalize_query(query)
        if normalized == " ":
            return " "
        return f"Instruct: {self._query_instruction}\nQuery: {normalized}"

    def _dense_embed(self, texts: list[str]) -> list[list[float]]:
        stripped = [t.strip() or " " for t in texts]
        return [v.tolist() for v in self._dense_embedder.embed(stripped)]

    def _sparse_embed(self, texts: list[str]) -> list[rest.SparseVector]:
        """Return SparseVector objects for each text."""
        assert self._sparse_embedder is not None
        stripped = [t.strip() or " " for t in texts]
        out = []
        for sv in self._sparse_embedder.embed(stripped):
            out.append(
                rest.SparseVector(
                    indices=sv.indices.tolist(),
                    values=sv.values.tolist(),
                )
            )
        return out

    # Source / mtime helpers

    def get_source_mtime(self, source: str) -> float | None:
        """Return stored mtime for this source, or None."""
        results, _ = self._client.scroll(
            collection_name=self.collection,
            scroll_filter=rest.Filter(
                must=[
                    rest.FieldCondition(
                        key="source",
                        match=rest.MatchValue(value=source),
                    )
                ]
            ),
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        if not results:
            return None
        mtime = results[0].payload.get("source_mtime")
        return float(mtime) if mtime is not None else None

    def delete_by_source(self, source: str) -> int:
        """Delete all points with the given source. Returns count deleted."""
        # count first
        count_result = self._client.count(
            collection_name=self.collection,
            count_filter=rest.Filter(
                must=[
                    rest.FieldCondition(
                        key="source",
                        match=rest.MatchValue(value=source),
                    )
                ]
            ),
            exact=True,
        )
        n = count_result.count
        if n:
            self._client.delete(
                collection_name=self.collection,
                points_selector=rest.FilterSelector(
                    filter=rest.Filter(
                        must=[
                            rest.FieldCondition(
                                key="source",
                                match=rest.MatchValue(value=source),
                            )
                        ]
                    )
                ),
            )
        return n

    def list_sources(self) -> set[str]:
        """Return the set of source paths currently in the collection."""
        sources: set[str] = set()
        offset = None
        while True:
            batch, next_offset = self._client.scroll(
                collection_name=self.collection,
                limit=256,
                offset=offset,
                with_payload=["source"],
                with_vectors=False,
            )
            for point in batch:
                src = point.payload.get("source")
                if src:
                    sources.add(src)
            if next_offset is None:
                break
            offset = next_offset
        return sources

    def add_many(
        self,
        texts: list[str],
        source: str | None = None,
        source_mtime: float | None = None,
    ) -> list[str]:
        """
        Embed and store multiple texts. Returns Qdrant point UUIDs.
        """
        if not texts:
            return []

        dense_vecs = self._dense_embed(texts)
        sparse_vecs = self._sparse_embed(texts) if self.hybrid else None

        points: list[rest.PointStruct] = []
        ids: list[str] = []
        for i, (text, dvec) in enumerate(zip(texts, dense_vecs)):
            point_id = str(uuid4())
            ids.append(point_id)

            vectors: dict[str, Any] = {_DENSE_VECTOR: dvec}
            if sparse_vecs is not None:
                vectors[_SPARSE_VECTOR] = sparse_vecs[i]

            points.append(
                rest.PointStruct(
                    id=point_id,
                    vector=vectors,
                    payload={
                        "text": text,
                        "source": source,
                        "source_mtime": source_mtime,
                    },
                )
            )

        self._client.upsert(collection_name=self.collection, points=points)
        return ids

    def index_file(
        self,
        path: Path,
        *,
        encoding: str = "utf-8",
        force: bool = False,
    ) -> list[str] | None:
        """(Re)index a single file if changed. Returns point ids or None if skipped."""
        source = path.resolve().as_posix()
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None
        if not force and self.get_source_mtime(source) == mtime:
            return None
        self.delete_by_source(source)
        text = path.read_text(encoding=encoding, errors="replace")
        chunks = chunk(content=text, suffix=path.suffix)
        return self.add_many(texts=chunks, source=source, source_mtime=mtime)

    # Search

    def search(
        self, query: str, k: int = 5, hybrid: bool = True
    ) -> list[dict[str, Any]]:
        """Return the k nearest chunks. Uses hybrid search when enabled."""
        formatted = self._format_query(query)
        results: list[SearchResult]

        if hybrid:
            results = self._hybrid_search(formatted, k)
        else:
            results = self._dense_search(formatted, k)

        return [
            {
                "id": r.id,
                "text": r.text,
                "score": round(r.score, 4),
                "source": r.source,
            }
            for r in results
        ]

    def _dense_search(self, query: str, k: int) -> list[SearchResult]:
        dense_vec = self._dense_embed([query])[0]
        hits = self._client.search(
            collection_name=self.collection,
            query_vector=((_DENSE_VECTOR, dense_vec)),
            limit=k,
            with_payload=True,
        )
        return [
            SearchResult(
                id=i,
                text=h.payload["text"],
                score=float(h.score),
                source=h.payload.get("source"),
            )
            for i, h in enumerate(hits)
        ]

    def _hybrid_search(self, query: str, k: int) -> list[SearchResult]:
        """
        Combines dense ANN and sparse BM42 via Reciprocal Rank Fusion.
        Qdrant performs the fusion server-side using query_points with Prefetch.
        """
        dense_vec = self._dense_embed([query])[0]
        sparse_vec = self._sparse_embed([query])[0]

        hits = self._client.query_points(
            collection_name=self.collection,
            prefetch=[
                rest.Prefetch(
                    query=dense_vec,
                    using=_DENSE_VECTOR,
                    limit=k * 4,  # over-fetch so RRF has enough candidates
                ),
                rest.Prefetch(
                    query=sparse_vec,
                    using=_SPARSE_VECTOR,
                    limit=k * 4,
                ),
            ],
            query=rest.FusionQuery(fusion=rest.Fusion.RRF),
            limit=k,
            with_payload=True,
        ).points

        return [
            SearchResult(
                id=i,
                text=h.payload["text"],
                score=float(h.score),
                source=h.payload.get("source"),
            )
            for i, h in enumerate(hits)
        ]

    # Sync

    def sync_from_roots(
        self,
        roots: str | Path | list[str] | list[Path],
        *,
        glob_pattern: str | list[str] = "*.md",
        encoding: str = "utf-8",
    ) -> tuple[int, int]:
        """Sync collection from filesystem. Returns (deleted_count, indexed_count)."""
        path_list = normalize_roots(roots)
        current_files = collect_file_paths(path_list, glob_pattern)
        db_sources = self.list_sources()
        to_remove = db_sources - current_files
        deleted = sum(self.delete_by_source(s) for s in to_remove)
        indexed = 0
        for posix_path in current_files:
            if self.index_file(Path(posix_path), encoding=encoding) is not None:
                indexed += 1
        return deleted, indexed

    # Lifecycle

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> VectorDB:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
