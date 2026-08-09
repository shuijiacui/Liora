import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from database import ReflectionDatabase, utc_now


IGNORED_DIRECTORIES = {".git", ".obsidian", ".trash", "node_modules", "templates"}
LIORA_BLOCK_PATTERN = re.compile(
    r"<!--\s*liora:begin\s*-->(.*?)<!--\s*liora:end\s*-->",
    re.IGNORECASE | re.DOTALL,
)
INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
INLINE_TAG_PATTERN = re.compile(r"(?<![\w#])#([^\s#.,;:!?，。；：！？()（）\[\]{}]+)")


def _file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_filename(title: str) -> str:
    value = INVALID_FILENAME.sub("-", str(title or "").strip()).strip(" .-")
    value = re.sub(r"\s+", " ", value)
    return (value[:80].rstrip(" .-") or "未命名知识")


def _yaml_scalar(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _parse_scalar(value: str):
    value = value.strip()
    if not value:
        return ""
    if value[0:1] in {'"', "'"} and value[-1:] == value[0:1]:
        if value[0] == '"':
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else value
        except json.JSONDecodeError:
            return [part.strip().strip('"\'') for part in value[1:-1].split(",") if part.strip()]
    try:
        return int(value)
    except ValueError:
        return value


def split_frontmatter(text: str) -> tuple[dict, str, list[str]]:
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text.lstrip("\ufeff"), []
    end = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if end is None:
        return {}, text.lstrip("\ufeff"), []

    metadata = {}
    raw = lines[1:end]
    index = 0
    while index < len(raw):
        line = raw[index]
        if ":" not in line or line.startswith((" ", "\t", "-")):
            index += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        parsed = _parse_scalar(value)
        if not str(value).strip():
            values = []
            cursor = index + 1
            while cursor < len(raw) and re.match(r"^\s+-\s+", raw[cursor]):
                values.append(_parse_scalar(re.sub(r"^\s+-\s+", "", raw[cursor])))
                cursor += 1
            if values:
                parsed = values
                index = cursor - 1
        metadata[key] = parsed
        index += 1
    body = "\n".join(lines[end + 1 :]).lstrip("\n")
    return metadata, body, raw


def _section_map(body: str) -> tuple[str, dict[str, list[str]]]:
    title = ""
    sections: dict[str, list[str]] = {"": []}
    current = ""
    for line in body.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            heading = match.group(2).strip()
            if len(match.group(1)) == 1 and not title:
                title = heading
            current = heading
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return title, sections


def _clean_lines(lines: list[str]) -> list[str]:
    values = []
    for line in lines:
        value = re.sub(r"^\s*(?:[-*+] |\d+[.)]\s+)", "", line).strip()
        if value:
            values.append(value)
    return values


def _knowledge_tags(metadata: dict, body: str) -> list[str]:
    raw = metadata.get("tags", metadata.get("tag", []))
    if isinstance(raw, str):
        values = re.split(r"[,，\s]+", raw)
    elif isinstance(raw, list):
        values = raw
    else:
        values = []
    values.extend(match.group(1) for match in INLINE_TAG_PATTERN.finditer(body))
    tags = []
    seen = set()
    for value in values:
        tag = str(value).strip().lstrip("#").strip()
        key = tag.casefold()
        if tag and key not in seen:
            seen.add(key)
            tags.append(tag)
    return tags


def parse_markdown(text: str, fallback_title: str) -> dict:
    metadata, body, _ = split_frontmatter(text)
    managed = LIORA_BLOCK_PATTERN.search(body)
    parsed_body = managed.group(1).strip() if managed else body
    heading_title, sections = _section_map(parsed_body)

    aliases = {
        "core_insight": ("核心理解", "核心洞察", "core insight"),
        "logic_chain": ("逻辑链", "logic chain"),
        "open_questions": ("仍待确认", "还想继续弄清", "开放问题", "open questions"),
        "next_step": ("下一步", "next step"),
    }

    def find_section(names: tuple[str, ...]) -> list[str]:
        for heading, lines in sections.items():
            normalized = heading.casefold().strip()
            if any(normalized == name.casefold() for name in names):
                return lines
        return []

    managed_title = ""
    if managed and heading_title.startswith("Liora 整理："):
        managed_title = heading_title.removeprefix("Liora 整理：").strip()
    title = str(managed_title or metadata.get("title") or heading_title or fallback_title).strip()
    tags = _knowledge_tags(metadata, body)
    core_lines = _clean_lines(find_section(aliases["core_insight"]))
    if not core_lines:
        generic = []
        for heading, lines in sections.items():
            if heading.startswith("Liora 整理："):
                continue
            generic.extend(_clean_lines(lines))
        core_lines = generic[:8]

    return {
        "id": str(metadata.get("liora_id") or metadata.get("id") or "").strip(),
        "title": title,
        "created_at": str(metadata.get("created") or "").strip(),
        "updated_at": str(metadata.get("liora_updated") or metadata.get("updated") or "").strip(),
        "version": metadata.get("liora_version") or metadata.get("version") or 1,
        "source": str(metadata.get("source") or "obsidian").strip() or "obsidian",
        "tags": tags,
        "search_text": "\n".join((title, body)).strip(),
        "content": {
            "title": title,
            "core_insight": "\n".join(core_lines).strip(),
            "logic_chain": _clean_lines(find_section(aliases["logic_chain"])),
            "open_questions": _clean_lines(find_section(aliases["open_questions"])),
            "next_step": "\n".join(_clean_lines(find_section(aliases["next_step"]))).strip(),
        },
    }


def _knowledge_sections(content: dict, heading_level: int = 2) -> str:
    prefix = "#" * heading_level
    lines = [
        f"{prefix} 核心理解",
        "",
        str(content.get("core_insight") or "").strip(),
        "",
        f"{prefix} 逻辑链",
        "",
    ]
    chain = content.get("logic_chain") or []
    lines.extend([f"- {item}" for item in chain] or ["- 暂无"])
    lines.extend(["", f"{prefix} 仍待确认", ""])
    questions = content.get("open_questions") or []
    lines.extend([f"- {item}" for item in questions] or ["- 暂无"])
    lines.extend(
        [
            "",
            f"{prefix} 下一步",
            "",
            str(content.get("next_step") or "").strip(),
        ]
    )
    return "\n".join(lines).rstrip()


def render_knowledge_markdown(item: dict) -> str:
    content = item["content"]
    title = str(content.get("title") or item.get("title") or "未命名知识").strip()
    frontmatter = [
        "---",
        f"id: {_yaml_scalar(item['id'])}",
        "type: knowledge",
        f"title: {_yaml_scalar(title)}",
        f"created: {_yaml_scalar(item['created_at'])}",
        f"updated: {_yaml_scalar(item['updated_at'])}",
        f"version: {int(item.get('version') or 1)}",
        "source: liora",
        "tags: []",
        "schema_version: 1",
        "---",
        "",
        f"# {title}",
        "",
        "<!-- liora:begin -->",
        _knowledge_sections(content),
        "<!-- liora:end -->",
        "",
    ]
    return "\n".join(frontmatter)


def render_managed_block(content: dict) -> str:
    title = str(content.get("title") or "新的理解").strip()
    return "\n".join(
        [
            "<!-- liora:begin -->",
            f"# Liora 整理：{title}",
            "",
            _knowledge_sections(content),
            "<!-- liora:end -->",
        ]
    )


def _update_frontmatter(text: str, additions: dict[str, str]) -> str:
    _, body, raw = split_frontmatter(text)
    if raw:
        output = list(raw)
        keys = {line.split(":", 1)[0].strip(): index for index, line in enumerate(output) if ":" in line}
        for key, value in additions.items():
            line = f"{key}: {value}"
            if key in keys:
                output[keys[key]] = line
            else:
                output.append(line)
        return "---\n" + "\n".join(output) + "\n---\n\n" + body
    return "---\n" + "\n".join(f"{key}: {value}" for key, value in additions.items()) + "\n---\n\n" + text.lstrip("\ufeff")


def _update_external_frontmatter(text: str, item: dict) -> str:
    return _update_frontmatter(
        text,
        {
            "liora_id": _yaml_scalar(item["id"]),
            "liora_version": str(int(item.get("version") or 1)),
            "liora_updated": _yaml_scalar(item["updated_at"]),
        },
    )


def _update_liora_frontmatter(text: str, item: dict) -> str:
    return _update_frontmatter(
        text,
        {
            "id": _yaml_scalar(item["id"]),
            "title": _yaml_scalar(item["title"]),
            "updated": _yaml_scalar(item["updated_at"]),
            "version": str(int(item.get("version") or 1)),
            "source": "liora",
        },
    )


class KnowledgeVault:
    def __init__(self, database: ReflectionDatabase, vault_path: Path, backup_dir: Path):
        self.database = database
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.backup_dir = Path(backup_dir)
        self._last_scan_at = 0.0
        self._last_scan_report: dict | None = None
        if not self.vault_path.is_dir():
            raise ValueError("选择的 Obsidian Vault 不存在或不是文件夹。")

    def status(self) -> dict:
        return {
            "configured": True,
            "vault_path": str(self.vault_path),
            "indexed_count": self.database.count_knowledge_documents(),
        }

    def _relative(self, path: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(self.vault_path).as_posix()
        except ValueError as error:
            raise ValueError("知识文件必须位于所选 Obsidian Vault 中。") from error

    def _path(self, relative_path: str) -> Path:
        candidate = (self.vault_path / Path(relative_path)).resolve()
        self._relative(candidate)
        return candidate

    def _markdown_files(self) -> list[Path]:
        files = []
        for path in self.vault_path.rglob("*.md"):
            relative = path.relative_to(self.vault_path)
            if any(part.casefold() in IGNORED_DIRECTORIES for part in relative.parts[:-1]):
                continue
            if path.is_file():
                files.append(path)
        return sorted(files, key=lambda value: value.as_posix().casefold())

    def scan(self, force: bool = False, allow_cached: bool = False) -> dict:
        if (
            allow_cached
            and not force
            and self._last_scan_report is not None
            and time.monotonic() - self._last_scan_at < 30
        ):
            return {**self._last_scan_report, "cached": True}
        files = self._markdown_files()
        active_paths = {self._relative(path) for path in files}
        existing = {item["relative_path"]: item for item in self.database.all_knowledge_documents()}
        seen_paths = set()
        seen_ids = set()
        counts = {"scanned": len(files), "indexed": 0, "updated": 0, "unchanged": 0, "deleted": 0, "conflicts": 0, "errors": 0}

        for path in files:
            try:
                relative = self._relative(path)
                seen_paths.add(relative)
                stat = path.stat()
                previous = existing.get(relative)
                if (
                    not force
                    and previous
                    and not previous.get("deleted_at")
                    and previous["file_mtime_ns"] == stat.st_mtime_ns
                    and previous["file_size"] == stat.st_size
                    and previous.get("search_indexed")
                ):
                    seen_ids.add(previous["id"])
                    counts["unchanged"] += 1
                    continue

                data = path.read_bytes()
                text = data.decode("utf-8-sig")
                parsed = parse_markdown(text, path.stem)
                content_hash = _file_hash(data)
                document_id = parsed["id"] or (previous or {}).get("id")
                if not document_id:
                    renamed = self.database.find_missing_document_by_hash(content_hash, active_paths)
                    document_id = (renamed or {}).get("id") or str(uuid.uuid4())
                if document_id in seen_ids:
                    document_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"liora:{relative}"))
                    counts["conflicts"] += 1
                seen_ids.add(document_id)

                now = utc_now()
                try:
                    version = max(1, int(parsed["version"]))
                except (TypeError, ValueError):
                    version = 1
                item = {
                    "id": document_id,
                    "relative_path": relative,
                    "title": parsed["title"],
                    "created_at": parsed["created_at"] or datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat(timespec="seconds"),
                    "updated_at": parsed["updated_at"] or datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
                    "version": version,
                    "content": parsed["content"],
                    "file_mtime_ns": stat.st_mtime_ns,
                    "file_size": stat.st_size,
                    "content_hash": content_hash,
                    "source": parsed["source"],
                    "indexed_at": now,
                    "folder": Path(relative).parent.as_posix()
                    if Path(relative).parent.as_posix() != "."
                    else "",
                    "tags": parsed["tags"],
                    "search_text": parsed["search_text"],
                }
                self.database.upsert_knowledge_document(item)
                counts["updated" if previous else "indexed"] += 1
            except (OSError, UnicodeError, ValueError):
                counts["errors"] += 1

        counts["deleted"] = self.database.mark_missing_knowledge_documents(seen_paths)
        counts["active"] = self.database.count_knowledge_documents()
        counts["cached"] = False
        self._last_scan_at = time.monotonic()
        self._last_scan_report = dict(counts)
        return counts

    def rebuild_index(self) -> dict:
        # Keep generated IDs for notes without frontmatter while forcing every
        # active Markdown file to be decoded and parsed again.
        return self.scan(force=True)

    def _atomic_write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def write(self, item: dict) -> dict:
        existing = self.database.get_knowledge_document(item["id"])
        if existing:
            path = self._path(existing["relative_path"])
        else:
            name = f"{_safe_filename(item['title'])}--{item['id'][:8]}.md"
            path = self.vault_path / "00 Inbox" / "Liora" / name

        if existing and existing.get("source") != "liora" and path.exists():
            original = path.read_text(encoding="utf-8-sig")
            block = render_managed_block(item["content"])
            if LIORA_BLOCK_PATTERN.search(original):
                output = LIORA_BLOCK_PATTERN.sub(block, original, count=1)
            else:
                output = original.rstrip() + "\n\n" + block + "\n"
            output = _update_external_frontmatter(output, item)
        elif existing and path.exists():
            original = path.read_text(encoding="utf-8-sig")
            block = "<!-- liora:begin -->\n" + _knowledge_sections(item["content"]) + "\n<!-- liora:end -->"
            if LIORA_BLOCK_PATTERN.search(original):
                output = LIORA_BLOCK_PATTERN.sub(block, original, count=1)
                output = _update_liora_frontmatter(output, item)
            else:
                # Files created before managed blocks existed cannot be safely
                # separated from generated content, so upgrade them once.
                output = render_knowledge_markdown(item)
        else:
            output = render_knowledge_markdown(item)

        self._atomic_write(path, output)
        stat = path.stat()
        data = path.read_bytes()
        parsed = parse_markdown(data.decode("utf-8-sig"), path.stem)
        stored = {
            **item,
            "relative_path": self._relative(path),
            "file_mtime_ns": stat.st_mtime_ns,
            "file_size": stat.st_size,
            "content_hash": _file_hash(data),
            "source": "liora" if not existing or existing.get("source") == "liora" else existing["source"],
            "indexed_at": utc_now(),
            "folder": Path(self._relative(path)).parent.as_posix()
            if Path(self._relative(path)).parent.as_posix() != "."
            else "",
            "tags": parsed["tags"],
            "search_text": parsed["search_text"],
            "content": parsed["content"] if existing and existing.get("source") != "liora" else item["content"],
        }
        self.database.upsert_knowledge_document(stored)
        return self.database.get_knowledge_document(item["id"])

    def migrate_legacy(self) -> dict:
        legacy = self.database.list_all_knowledge()
        pending = [item for item in legacy if self.database.get_knowledge_document(item["id"]) is None]
        report = {"total": len(legacy), "migrated": 0, "skipped": len(legacy) - len(pending), "failed": 0, "backup_path": None}
        if not pending:
            return report

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = self.backup_dir / f"liora-pre-vault-{timestamp}.sqlite3"
        self.database.backup(backup_path)
        report["backup_path"] = str(backup_path)
        for item in pending:
            try:
                self.write(item)
                report["migrated"] += 1
            except (OSError, UnicodeError, ValueError):
                report["failed"] += 1
        return report
