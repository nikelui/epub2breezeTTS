"""Parse CLI chapter selection expressions (1,3-5,8)."""


def select_chapters(spec: str | None, available: set[int]) -> list[int]:
    if not available:
        return []
    if spec is None or spec.strip().lower() == "all":
        return sorted(available)
    selected: set[int] = set()
    for token in spec.split(","):
        token = token.strip()
        if not token:
            raise ValueError("Empty chapter selection token")
        if "-" in token:
            fields = token.split("-")
            if len(fields) != 2 or not all(part.strip().isdigit() for part in fields):
                raise ValueError(f"Invalid range: {token!r}")
            start, end = (int(part) for part in fields)
            if start < 1 or start > end:
                raise ValueError(f"Invalid range: {token!r}")
            selected.update(range(start, end + 1))
        else:
            if not token.isdigit() or int(token) < 1:
                raise ValueError(f"Invalid chapter: {token!r}")
            selected.add(int(token))
    missing = selected - available
    if missing:
        raise ValueError(f"Unknown chapter number(s): {', '.join(map(str, sorted(missing)))}")
    return sorted(selected)
