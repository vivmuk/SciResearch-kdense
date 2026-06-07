import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def load_instructions(agent_name: str) -> str:
    """Load instructions from a markdown file in the instructions directory."""
    instructions_path = Path("kady_agent/instructions") / f"{agent_name}.md"
    return instructions_path.read_text(encoding="utf-8")


def list_skill_summaries(skills_dir: str | None = None) -> list[dict]:
    """Read skill name and description from each SKILL.md frontmatter.

    Returns a list of ``{"name": ..., "description": ...}`` dicts sorted by
    name, suitable for injecting into the orchestrator's instruction as a
    reference catalogue. When ``skills_dir`` is omitted, resolves to the
    active project's ``sandbox/.gemini/skills``.
    """
    if skills_dir is None:
        from .projects import active_paths
        skills_path = active_paths().gemini_settings_dir / "skills"
    else:
        skills_path = Path(skills_dir)
    if not skills_path.is_dir():
        return []

    summaries: list[dict] = []
    for child in sorted(skills_path.iterdir(), key=lambda p: p.name.lower()):
        skill_file = child / "SKILL.md"
        if not child.is_dir() or not skill_file.is_file():
            continue
        try:
            text = skill_file.read_text(encoding="utf-8", errors="replace")
            match = _FRONTMATTER_RE.match(text)
            if not match:
                continue
            try:
                meta = yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError:
                meta = {}
            summaries.append({
                "name": meta.get("name", child.name),
                "description": meta.get("description", ""),
            })
        except Exception:
            continue
    return summaries


def format_skills_reference(skills: list[dict]) -> str:
    """Format a skill list into a compact markdown reference block."""
    if not skills:
        return ""

    lines = [
        "",
        "## Available expert skills — reference only",
        "",
        "The following skills are installed on the expert (Gemini CLI) that runs "
        "inside `delegate_task`. **You (Kady) MUST NOT attempt to activate, call, "
        "or use these skills yourself.** They exist here ONLY so you can:",
        "",
        "1. Recognize when a user mentions a skill by name.",
        "2. Pass the skill name verbatim in the `delegate_task` prompt.",
        "3. Match user requests to the most relevant skill(s) even when the user "
        "does not name one explicitly, and instruct the expert to use the "
        "skill in your `delegate_task` prompt.",
        "",
        "| Skill name | Description |",
        "|---|---|",
    ]
    for s in skills:
        desc = (s["description"] or "").replace("\n", " ").strip()
        if len(desc) > 200:
            desc = desc[:197] + "..."
        lines.append(f"| `{s['name']}` | {desc} |")

    lines.append("")
    return "\n".join(lines)


def _resolve_skills_target(target_dir: str | None) -> Path:
    if target_dir is None:
        from .projects import active_paths
        return active_paths().gemini_settings_dir / "skills"
    return Path(target_dir)


def _clone_scientific_skills_repo(
    *,
    github_repo: str = "K-Dense-AI/scientific-agent-skills",
    source_path: str = "skills",
    branch: str = "main",
) -> Path:
    """Shallow-clone the skills repo and return the path to its ``skills/`` folder."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        repo_url = f"https://github.com/{github_repo}.git"
        print("Cloning Scientific Agent Skills repository (this may take a moment)...")
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", branch, repo_url, str(temp_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        source_dir = temp_path / source_path
        if not source_dir.is_dir():
            raise FileNotFoundError(
                f"Source path '{source_path}' not found in repository"
            )
        # Copy into a second temp dir so the clone root survives after this
        # context manager exits.
        staging = Path(tempfile.mkdtemp(prefix="kady-skills-"))
        shutil.copytree(source_dir, staging / source_path)
        return staging / source_path


def _copy_skill_catalogue(
    source_dir: Path,
    target_path: Path,
    *,
    replace_existing: bool,
) -> int:
    """Copy skill subdirectories from ``source_dir`` into ``target_path``."""
    target_path.mkdir(parents=True, exist_ok=True)
    skill_count = 0
    for skill_dir in sorted(source_dir.iterdir(), key=lambda p: p.name.lower()):
        if not skill_dir.is_dir():
            continue
        dest_dir = target_path / skill_dir.name
        if dest_dir.exists():
            if not replace_existing:
                continue
            shutil.rmtree(dest_dir)
        shutil.copytree(skill_dir, dest_dir)
        print(f"  ✓ {skill_dir.name}")
        skill_count += 1
    return skill_count


def download_scientific_skills(
    target_dir: str | None = None,
    github_repo: str = "K-Dense-AI/scientific-agent-skills",
    source_path: str = "skills",
    branch: str = "main",
) -> None:
    """
    Download all directories from the skills folder in the GitHub repository
    and place them in the target directory using git clone.

    Existing skill directories are replaced so the local catalogue matches
    the remote repo.
    """
    target_path = _resolve_skills_target(target_dir)
    staging_root: Path | None = None
    try:
        source_dir = _clone_scientific_skills_repo(
            github_repo=github_repo, source_path=source_path, branch=branch
        )
        staging_root = source_dir.parent
        print(f"\n📂 Copying skills to {target_path}...")
        skill_count = _copy_skill_catalogue(
            source_dir, target_path, replace_existing=True
        )
        print(
            f"\n✅ Successfully downloaded {skill_count} scientific skills "
            f"to {target_path.absolute()}"
        )
    except subprocess.CalledProcessError as e:
        print(f"❌ Error cloning repository: {e.stderr}")
        raise
    finally:
        if staging_root is not None:
            shutil.rmtree(staging_root, ignore_errors=True)


def sync_missing_scientific_skills(
    target_dir: str | None = None,
    github_repo: str = "K-Dense-AI/scientific-agent-skills",
    source_path: str = "skills",
    branch: str = "main",
) -> int:
    """Clone the skills repo and copy only skill dirs not already present locally."""
    target_path = _resolve_skills_target(target_dir)
    staging_root: Path | None = None
    try:
        source_dir = _clone_scientific_skills_repo(
            github_repo=github_repo, source_path=source_path, branch=branch
        )
        staging_root = source_dir.parent
        added = _copy_skill_catalogue(
            source_dir, target_path, replace_existing=False
        )
        if added:
            print(
                f"Synced {added} missing scientific skills to {target_path.absolute()}"
            )
        return added
    except subprocess.CalledProcessError as e:
        print(f"❌ Error cloning repository: {e.stderr}")
        raise
    finally:
        if staging_root is not None:
            shutil.rmtree(staging_root, ignore_errors=True)


def fetch_venice_models(api_key: str | None = None) -> list[dict]:
    import httpx
    import os
    key = api_key or os.getenv("VENICE_API_KEY")
    if not key:
        print("No VENICE_API_KEY provided.")
        return []

    try:
        resp = httpx.get("https://api.venice.ai/api/v1/models", headers={"Authorization": f"Bearer {key}"})
        resp.raise_for_status()
    except Exception as e:
        print(f"Error fetching Venice models: {e}")
        return []

    return resp.json().get('data', [])


def update_models_json(
    output_path: str = "web/src/data/models.json",
    default_model_id: str = "minimax-m3",
    expert_default_model_id: str = "qwen3.5-9b",
    api_key: str | None = None,
) -> None:
    """Fetch models from Venice and overwrite the frontend models.json.

    Args:
        output_path: Path to the output JSON file.
        default_model_id: The Venice model ID to mark as the default.
        expert_default_model_id: The Venice model ID to mark as the expert
            default in the frontend picker.
        api_key: Venice API key (falls back to VENICE_API_KEY env var).
    """
    raw_models = fetch_venice_models(api_key=api_key)
    out = Path(output_path)
    entries = []
    
    for m in raw_models:
        m_id = m['id']
        entry = {
            "id": f"venice/{m_id}",
            "label": m_id,
            "provider": "Venice",
            "tier": "high" if "minimax" in m_id.lower() or "llama-3.3" in m_id.lower() else "mid",
            "context_length": m.get('context_length', 128000),
            "pricing": {"prompt": 0, "completion": 0},
            "modality": "text+image+file->text",
            "description": m.get('description', f"Venice model: {m_id}. Powered by Venice.")
        }
        if default_model_id in m_id.lower():
            entry["default"] = True
        if expert_default_model_id in m_id.lower():
            entry["expertDefault"] = True
        entries.append(entry)

    # ensure defaults
    if entries and not any(e.get('default') for e in entries):
        entries[0]['default'] = True
    if len(entries) > 1 and not any(e.get('expertDefault') for e in entries):
        entries[1]['expertDefault'] = True

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    print(f"Models: wrote {len(entries)} Venice models to {out}")