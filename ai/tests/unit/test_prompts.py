"""Prompt files: parsing, validation of sections and placeholders, versions and checksums."""

import pytest

from tutor_ai.prompts import SCHEMAS, PromptError, PromptRegistry, parse
from tutor_ai.settings import AI_DIR

REAL_DIR = AI_DIR / "prompts"
REAL_V1 = (REAL_DIR / "tutor" / "v1.md").read_text(encoding="utf-8")


def write(directory, name, version, body):
    path = directory / name / f"{version}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_the_shipped_prompts_load_and_are_complete():
    registry = PromptRegistry.load(REAL_DIR)
    tutor = registry.active("tutor")
    assert tutor.ref == "tutor/v1"
    assert set(tutor.sections) == set(SCHEMAS["tutor"])
    assert "DRAFT" in tutor.body  # safety wording awaits sign-off (design §7)
    assert len(tutor.checksum) == 64


def test_sections_render_with_values_and_comments_are_dropped():
    tutor = parse("tutor", "v1", REAL_V1)
    system = tutor.render("system", student="a Class 8 student", reply_words="180")
    assert "a Class 8 student" in system and "under 180 words" in system
    assert "$" not in system and "<!--" not in system
    with pytest.raises(KeyError):
        tutor.render("system", student="x")  # every placeholder must be filled


def test_values_are_never_treated_as_template_text():
    tutor = parse("tutor", "v1", REAL_V1)
    context = tutor.render("context", lesson_title="$student ${reply_words}", passages="Cost is $5 {x}")
    assert "$student ${reply_words}" in context and "Cost is $5 {x}" in context


def test_the_checksum_ignores_comments_but_not_text():
    base = parse("tutor", "v1", REAL_V1)
    assert parse("tutor", "v1", REAL_V1.replace("DRAFT", "Reviewed")).checksum == base.checksum  # comment only
    assert parse("tutor", "v1", REAL_V1.replace("patient", "kind")).checksum != base.checksum


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda b: b.replace("## @hint", "## @hints"), "unknown section @hints"),
        (lambda b: b + "\n## @hint\nAgain.\n", "appears twice"),
        (lambda b: b.replace("Mode: hint.", "Mode: hint for $student."), "unknown placeholders ['student']"),
        (lambda b: b.replace("Mode: hint.", "Costs $5."), "malformed $placeholder"),
        (
            lambda b: b.split("## @quiz_guard")[0] + "## @context\nLesson: $lesson_title\n$passages\n",
            "missing sections",
        ),
    ],
)
def test_malformed_prompts_are_refused(change, message):
    with pytest.raises(PromptError, match=message.replace("[", r"\[").replace("]", r"\]").replace("$", r"\$")):
        parse("tutor", "v2", change(REAL_V1))


def test_an_empty_section_is_refused():
    body = REAL_V1.replace(
        "Mode: hint. Give only the smallest next step the student needs. Do not solve the whole problem.", ""
    )
    with pytest.raises(PromptError, match="empty"):
        parse("tutor", "v1", body)


def test_unknown_names_and_bad_version_names_are_refused(tmp_path):
    with pytest.raises(PromptError, match="unknown prompt name"):
        parse("grader", "v1", REAL_V1)
    with pytest.raises(PromptError, match="versions are named"):
        parse("tutor", "version1", REAL_V1)
    write(tmp_path, "tutor", "v1", REAL_V1)
    write(tmp_path, "tutor", "draft", REAL_V1)
    with pytest.raises(PromptError, match="prompt files are named"):
        PromptRegistry.load(tmp_path)


def test_the_highest_version_is_active(tmp_path):
    for version in ("v1", "v2", "v10", "v9"):
        write(tmp_path, "tutor", version, REAL_V1)
    registry = PromptRegistry.load(tmp_path)
    assert registry.active("tutor").version == "v10"
    assert registry.active_refs() == {"tutor": "v10"}
    assert registry.get("tutor", "v2").number == 2
    assert len(registry.all()) == 4
    with pytest.raises(PromptError, match="unknown prompt tutor/v3"):
        registry.get("tutor", "v3")


def test_every_known_prompt_needs_a_version(tmp_path):
    (tmp_path / "tutor").mkdir()
    with pytest.raises(PromptError, match="no versions found"):
        PromptRegistry.load(tmp_path)
    with pytest.raises(PromptError, match="does not exist"):
        PromptRegistry.load(tmp_path / "missing")
