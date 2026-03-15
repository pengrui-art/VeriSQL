from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO_ROOT / "paper_data"
KNOWN_CATEGORIES = {"runs", "reports", "logs"}


def resolve_output_path(path_str: str | None, category: str, default_name: str) -> Path:
    """Resolve output paths into the shared paper_data workspace by default."""
    candidate = Path(path_str) if path_str else Path(default_name)

    if candidate.is_absolute():
        resolved = candidate
    elif candidate.parts and candidate.parts[0] == ARTIFACT_ROOT.name:
        resolved = REPO_ROOT / candidate
    elif candidate.parts and candidate.parts[0] in KNOWN_CATEGORIES:
        resolved = ARTIFACT_ROOT / candidate
    else:
        resolved = ARTIFACT_ROOT / category / candidate

    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def resolve_input_path(path_str: str, category: str) -> Path:
    """Resolve an existing input path, preferring files under paper_data."""
    candidate = Path(path_str)
    checked: list[Path] = []

    if candidate.is_absolute():
        checked.append(candidate)
    else:
        if candidate.parts and candidate.parts[0] == ARTIFACT_ROOT.name:
            checked.append(REPO_ROOT / candidate)
        elif candidate.parts and candidate.parts[0] in KNOWN_CATEGORIES:
            checked.append(ARTIFACT_ROOT / candidate)
        else:
            checked.append(ARTIFACT_ROOT / category / candidate)
            checked.append(ARTIFACT_ROOT / candidate)
            checked.append(REPO_ROOT / candidate)

    seen: set[Path] = set()
    for path in checked:
        if path in seen:
            continue
        seen.add(path)
        if path.exists():
            return path

    searched = ", ".join(str(path) for path in checked)
    raise FileNotFoundError(f"Could not locate '{path_str}'. Checked: {searched}")


def to_repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
