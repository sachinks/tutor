"""Versioned prompt files (design §6).

Prompts live in ai/prompts/<name>/v<N>.md, split into sections by "## @section" lines. At start-up every file is
loaded and checked (known sections, known placeholders), and the active version of each prompt is the highest
number. Every tutor reply records the prompt reference (e.g. "tutor/v1") so answers can be traced to exact text.

A version is immutable once used: sync_prompts() stores each version's text (without its <!-- comments -->) with a
SHA-256 checksum in ai.prompt_version and refuses to continue if a stored version's text has changed. To change a
prompt, add v2.md.

Templates use string.Template ($name). Lesson text and student messages are always substituted *values*, so a "$" or
"{" typed by a student can never change the template.
"""

import hashlib
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from string import Template

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from .schema import prompt_version

logger = logging.getLogger("tutor_ai.prompts")

_SECTION = re.compile(r"^## @([a-z_]+)[ \t]*$", re.MULTILINE)
_VERSION_FILE = re.compile(r"^v([1-9][0-9]{0,3})\.md$")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

# Every prompt name the service knows, with its sections and the placeholders each section may use.
SCHEMAS: dict[str, dict[str, frozenset[str]]] = {
    "tutor": {
        "system": frozenset({"student", "reply_words"}),
        "explain": frozenset(),
        "socratic": frozenset(),
        "hint": frozenset(),
        "quiz_guard": frozenset(),
        "context": frozenset({"lesson_title", "passages"}),
    },
}


class PromptError(RuntimeError):
    """A prompt file is malformed, or a stored prompt version was edited."""


@dataclass(frozen=True)
class PromptVersion:
    name: str
    version: str  # "v1"
    number: int
    body: str
    checksum: str
    sections: Mapping[str, Template] = field(compare=False)

    @property
    def ref(self) -> str:
        return f"{self.name}/{self.version}"

    def render(self, section: str, **values: str) -> str:
        """Fill one section. Every placeholder must be given (a missing value is a programming error)."""
        return self.sections[section].substitute(values).strip()


def parse(name: str, version: str, body: str) -> PromptVersion:
    schema = SCHEMAS.get(name)
    if schema is None:
        raise PromptError(f"unknown prompt name {name!r} (known: {', '.join(sorted(SCHEMAS))})")
    match = _VERSION_FILE.match(f"{version}.md")
    if match is None:
        raise PromptError(f"{name}/{version}: versions are named v1, v2, …")
    text = _COMMENT.sub("", body)
    headers = list(_SECTION.finditer(text))
    found: dict[str, Template] = {}
    for i, header in enumerate(headers):
        section = header.group(1)
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        content = text[header.end() : end].strip()
        if section not in schema:
            raise PromptError(f"{name}/{version}: unknown section @{section}")
        if section in found:
            raise PromptError(f"{name}/{version}: section @{section} appears twice")
        if not content:
            raise PromptError(f"{name}/{version}: section @{section} is empty")
        template = Template(content)
        if not template.is_valid():
            raise PromptError(f"{name}/{version}: section @{section} has a malformed $placeholder")
        unknown = set(template.get_identifiers()) - schema[section]
        if unknown:
            raise PromptError(f"{name}/{version}: section @{section} uses unknown placeholders {sorted(unknown)}")
        found[section] = template
    missing = set(schema) - set(found)
    if missing:
        raise PromptError(f"{name}/{version}: missing sections {sorted(missing)}")
    return PromptVersion(
        name=name,
        version=version,
        number=int(match.group(1)),
        body=body,
        checksum=hashlib.sha256(text.strip().encode("utf-8")).hexdigest(),  # comments may be edited; text may not
        sections=found,
    )


class PromptRegistry:
    def __init__(self, versions: list[PromptVersion]) -> None:
        self._by_name: dict[str, dict[str, PromptVersion]] = {}
        for item in versions:
            self._by_name.setdefault(item.name, {})[item.version] = item
        missing = set(SCHEMAS) - set(self._by_name)
        if missing:
            raise PromptError(f"no versions found for prompts {sorted(missing)}")

    @classmethod
    def load(cls, directory: Path) -> "PromptRegistry":
        if not directory.is_dir():
            raise PromptError(f"prompt directory {directory} does not exist")
        versions = []
        for path in sorted(directory.glob("*/*.md")):
            if not _VERSION_FILE.match(path.name):
                raise PromptError(f"{path}: prompt files are named v1.md, v2.md, …")
            versions.append(parse(path.parent.name, path.stem, path.read_text(encoding="utf-8")))
        return cls(versions)

    def active(self, name: str) -> PromptVersion:
        return max(self._by_name[name].values(), key=lambda v: v.number)

    def get(self, name: str, version: str) -> PromptVersion:
        try:
            return self._by_name[name][version]
        except KeyError:
            raise PromptError(f"unknown prompt {name}/{version}") from None

    def all(self) -> list[PromptVersion]:
        return [v for versions in self._by_name.values() for v in versions.values()]

    def active_refs(self) -> dict[str, str]:
        return {name: self.active(name).version for name in sorted(self._by_name)}


async def sync_prompts(engine: AsyncEngine, registry: PromptRegistry) -> None:
    """Record every version in ai.prompt_version, mark the active ones, and refuse edited versions."""
    async with engine.begin() as conn:
        for item in registry.all():
            await conn.execute(
                pg_insert(prompt_version)
                .values(name=item.name, version=item.version, body=item.body, checksum=item.checksum)
                .on_conflict_do_nothing(constraint="uq_prompt_version")
            )
        rows = (
            await conn.execute(select(prompt_version.c.name, prompt_version.c.version, prompt_version.c.checksum))
        ).all()
        for row in rows:
            try:
                current = registry.get(row.name, row.version)
            except PromptError:
                continue  # a version deleted from disk stays in the database for traceability
            if current.checksum != row.checksum:
                raise PromptError(
                    f"prompt {current.ref} was edited after it was stored; restore it and put changes in a new version"
                )
        for name, version in registry.active_refs().items():
            await conn.execute(
                update(prompt_version)
                .where(prompt_version.c.name == name)
                .values(active=prompt_version.c.version == version)
            )
    logger.info("prompts synced", extra={"active": registry.active_refs()})
