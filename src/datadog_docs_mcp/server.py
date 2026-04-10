"""MCP server for Datadog LLM documentation."""

import re
import ssl
from dataclasses import dataclass

import httpx
import truststore
from mcp.server.fastmcp import FastMCP

# Use the OS certificate store (supports corporate proxy CAs on Windows)
_ssl_ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

LLMS_TXT_URL = "https://docs.datadoghq.com/llms.txt"
BASE_URL = "https://docs.datadoghq.com"
CACHE_TTL_SECONDS = 900  # 15 minutes

mcp = FastMCP(
    "datadog-docs",
    instructions=(
        "Datadog documentation server. Use list_documents to browse the index, "
        "read_document to fetch a specific page, and search_documents to find "
        "documents by keyword."
    ),
)


@dataclass
class DocEntry:
    title: str
    url: str
    section: str


class IndexCache:
    """Simple in-memory cache for the llms.txt index."""

    def __init__(self) -> None:
        self._entries: list[DocEntry] = []
        self._raw: str = ""
        self._loaded: bool = False

    async def get_raw(self) -> str:
        if not self._loaded:
            await self._load()
        return self._raw

    async def get_entries(self) -> list[DocEntry]:
        if not self._loaded:
            await self._load()
        return self._entries

    async def _load(self) -> None:
        async with httpx.AsyncClient(timeout=30, verify=_ssl_ctx) as client:
            resp = await client.get(LLMS_TXT_URL)
            resp.raise_for_status()
            self._raw = resp.text

        self._entries = _parse_index(self._raw)
        self._loaded = True

    def invalidate(self) -> None:
        self._loaded = False
        self._entries = []
        self._raw = ""


_cache = IndexCache()

# Pattern: - [Title](URL)
_LINK_RE = re.compile(r"-\s+\[([^\]]+)\]\(([^)]+)\)")


def _parse_index(text: str) -> list[DocEntry]:
    """Parse llms.txt into a list of DocEntry objects."""
    entries: list[DocEntry] = []
    current_section = ""

    for line in text.splitlines():
        stripped = line.strip()

        # Section headers: lines starting with # or ##
        if stripped.startswith("#"):
            current_section = stripped.lstrip("#").strip()
            continue

        m = _LINK_RE.search(stripped)
        if m:
            title = m.group(1)
            url = m.group(2)
            if not url.startswith("http"):
                url = f"{BASE_URL}/{url.lstrip('/')}"
            entries.append(DocEntry(title=title, url=url, section=current_section))

    return entries


@mcp.tool()
async def list_documents(
    section: str = "",
    limit: int = 50,
    offset: int = 0,
) -> str:
    """List available Datadog documentation pages from the index.

    Args:
        section: Filter by section name (case-insensitive partial match). Leave empty for all.
        limit: Maximum number of entries to return (default 50).
        offset: Number of entries to skip for pagination.

    Returns:
        A formatted list of document titles, sections, and URLs.
    """
    entries = await _cache.get_entries()

    if section:
        section_lower = section.lower()
        entries = [e for e in entries if section_lower in e.section.lower()]

    total = len(entries)
    page = entries[offset : offset + limit]

    lines = [f"Total: {total} documents (showing {offset + 1}-{offset + len(page)})\n"]
    for e in page:
        lines.append(f"- [{e.title}]({e.url})")
        if e.section:
            lines.append(f"  Section: {e.section}")

    return "\n".join(lines)


@mcp.tool()
async def read_document(url: str, max_chars: int = 50000) -> str:
    """Fetch and return the content of a specific Datadog documentation page.

    Args:
        url: The full URL of the markdown document (e.g. https://docs.datadoghq.com/all_guides.md).
        max_chars: Maximum characters to return (default 50000). Use with start_index for pagination.

    Returns:
        The markdown content of the document.
    """
    if not url.startswith("http"):
        url = f"{BASE_URL}/{url.lstrip('/')}"

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=_ssl_ctx) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content = resp.text

    if len(content) > max_chars:
        return (
            content[:max_chars]
            + f"\n\n--- Truncated at {max_chars} chars. Total: {len(content)} chars. "
            f"Use read_document_chunk to read the rest. ---"
        )

    return content


@mcp.tool()
async def read_document_chunk(
    url: str, start_index: int = 0, max_chars: int = 50000
) -> str:
    """Read a specific chunk of a large Datadog documentation page.

    Args:
        url: The full URL of the markdown document.
        start_index: Character offset to start reading from.
        max_chars: Maximum characters to return (default 50000).

    Returns:
        The requested chunk of the document content.
    """
    if not url.startswith("http"):
        url = f"{BASE_URL}/{url.lstrip('/')}"

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=_ssl_ctx) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content = resp.text

    total = len(content)
    chunk = content[start_index : start_index + max_chars]
    end_index = start_index + len(chunk)

    header = f"[Chars {start_index}-{end_index} of {total}]\n\n"
    return header + chunk


@mcp.tool()
async def search_documents(query: str, limit: int = 20) -> str:
    """Search Datadog documentation index by keyword.

    Searches document titles and section names. Results are ranked by the
    number of matching keywords (best matches first). At least one keyword
    must match.

    Args:
        query: Search query (case-insensitive). Multiple words are scored individually.
        limit: Maximum number of results to return (default 20).

    Returns:
        A formatted list of matching documents, ranked by relevance.
    """
    entries = await _cache.get_entries()
    keywords = query.lower().split()

    # Words too common in this context to be useful on their own
    stop_words = {"datadog", "the", "a", "an", "and", "or", "for", "to", "in", "of", "with"}

    scored: list[tuple[float, DocEntry]] = []
    for e in entries:
        title_lower = e.title.lower()
        section_lower = e.section.lower()
        text = f"{title_lower} {section_lower}"

        score = 0.0
        for kw in keywords:
            if kw in stop_words:
                if kw in text:
                    score += 0.1  # minor boost
                continue
            if kw in title_lower:
                score += 2.0  # title match weighted higher
            elif kw in section_lower:
                score += 1.0

        if score > 0:
            scored.append((score, e))

    if not scored:
        return f"No documents found matching '{query}'."

    scored.sort(key=lambda x: x[0], reverse=True)
    results = scored[:limit]

    lines = [f"Found {len(scored)} result(s) for '{query}' (showing top {len(results)}):\n"]
    for score, e in results:
        lines.append(f"- [{e.title}]({e.url})")
        if e.section:
            lines.append(f"  Section: {e.section}")

    return "\n".join(lines)


@mcp.tool()
async def get_index_sections() -> str:
    """List all top-level sections in the Datadog documentation index.

    Returns:
        A list of all section names found in llms.txt.
    """
    entries = await _cache.get_entries()
    sections: dict[str, int] = {}
    for e in entries:
        s = e.section or "(No section)"
        sections[s] = sections.get(s, 0) + 1

    lines = [f"Total: {len(sections)} sections\n"]
    for name, count in sorted(sections.items()):
        lines.append(f"- {name} ({count} docs)")

    return "\n".join(lines)


@mcp.tool()
async def refresh_index() -> str:
    """Force refresh the cached llms.txt index.

    Use this if you suspect the index is outdated.

    Returns:
        Confirmation message with the number of documents loaded.
    """
    _cache.invalidate()
    entries = await _cache.get_entries()
    return f"Index refreshed. {len(entries)} documents loaded."


if __name__ == "__main__":
    mcp.run()
