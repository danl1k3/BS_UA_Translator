from urllib.parse import quote


def make_content_disposition_header(filename: str) -> dict[str, str]:
    """Build a Content-Disposition attachment header with ASCII fallback and RFC 5987 filename*."""
    fallback = "".join(c if " " <= c <= "~" and c not in '"\\' else "_" for c in filename)
    pct = quote(filename, safe="")
    return {
        "Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{pct}"
    }
