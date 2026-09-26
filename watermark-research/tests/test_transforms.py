import pytest

from claude_mark_research.protect import find_protected
from claude_mark_research.transforms.deterministic_rewrite import DeterministicRewrite
from claude_mark_research.transforms.lexical_substitution import LexicalSubstitution
from claude_mark_research.transforms.phrase_substitution import PhraseSubstitution
from claude_mark_research.transforms.pipeline import Pipeline
from claude_mark_research.transforms.punctuation import PunctuationNormalization
from claude_mark_research.transforms.sentence_rules import SentenceRules, active_to_passive, because_fronting
from claude_mark_research.transforms.unicode_normalization import UnicodeNormalization
from claude_mark_research.transforms.whitespace import WhitespaceNormalization


def test_whitespace_example_and_counts():
    r = WhitespaceNormalization().transform("This   is\tan example.")
    assert r.output_text == "This is an example."
    assert r.changed_characters == 4  # "   " (3) + "\t" (1)
    assert r.edit_distance == 3
    assert r.changed_words == 0


def test_whitespace_keeps_indentation_and_collapses_blank_lines():
    text = "- item\n    - nested  item\n\n\n\nNext   para  \n"
    out = WhitespaceNormalization().transform(text).output_text
    assert out == "- item\n    - nested item\n\nNext para\n"


def test_unicode_forms_and_strip_invisible():
    text = "caf\u0065\u0301 \ufb01ne re\u200bview"
    assert UnicodeNormalization("NFC").transform(text).output_text == "caf\u00e9 \ufb01ne re\u200bview"
    assert UnicodeNormalization("NFKC").transform(text).output_text == "caf\u00e9 fine re\u200bview"
    r = UnicodeNormalization("NFC", strip_invisible=True).transform(text)
    assert r.output_text == "caf\u00e9 \ufb01ne review"
    assert any(e.operation == "strip_invisible" for e in r.edits)
    assert r.parameters["label"] == "Unicode normalization experiment"


def test_punctuation_normalized_and_typographic():
    t = "He said \u201chello\u201d \u2014 it\u2019s fine\u2026 Really?? Yes !"
    out = PunctuationNormalization("normalized", protection=None).transform(t).output_text
    assert out == 'He said "hello" -- it\'s fine... Really? Yes!'
    typo = PunctuationNormalization("typographic").transform('She said "yes" and it\'s done -- ok.').output_text
    assert typo == "She said \u201cyes\u201d and it\u2019s done\u2014ok."


def test_lexical_context_safety():
    text = ("We utilize the tool. Utilize it! UTILIZE. utilize_cache and see https://x.org/utilize "
            "or `utilize` or pre-utilize or utilized. Email utilize@example.com")
    out = LexicalSubstitution(strategy="first").transform(text).output_text
    assert out.startswith("We use the tool. Use it! USE.")
    for keep in ("utilize_cache", "https://x.org/utilize", "`utilize`", "pre-utilize", "utilize@example.com"):
        assert keep in out
    assert "used." in out


def test_lexical_article_agreement():
    out = LexicalSubstitution(strategy="first").transform("It took an approximately equal time.").output_text
    assert out == "It took an about equal time."
    out = LexicalSubstitution(strategy="first").transform("This is a significant result.").output_text
    assert out == "This is a notable result."
    out = LexicalSubstitution(strategy="first").transform("This is an important step.").output_text
    assert out == "This is a key step."


@pytest.mark.parametrize("strategy", ["first", "hash", "round_robin"])
def test_lexical_strategies_deterministic(strategy):
    text = "Approximately ten. Approximately nine. Approximately eight. Therefore done."
    a = LexicalSubstitution(strategy=strategy, seed=3).transform(text)
    b = LexicalSubstitution(strategy=strategy, seed=3).transform(text)
    assert a.output_text == b.output_text
    assert [e.audit() for e in a.edits] == [e.audit() for e in b.edits]


def test_round_robin_cycles():
    text = "approximately a. approximately b. approximately c."
    out = LexicalSubstitution(strategy="round_robin").transform(text).output_text
    assert out == "about a. roughly b. about c."


def test_lexical_budget():
    text = " ".join(["They utilize tools."] * 50)
    r = LexicalSubstitution(strategy="first", max_word_ratio=0.05).transform(text)
    assert len(r.edits) == int(0.05 * 150)


def test_phrase_substitution_records_every_replacement():
    t = "In order to win, and due to the fact that it rained, we stayed at this point in time."
    r = PhraseSubstitution().transform(t)
    assert r.output_text == "To win, and because it rained, we stayed currently."
    assert [e.metadata["phrase"] for e in r.edits] == ["in order to", "due to the fact that", "at this point in time"]


def test_sentence_rule_a():
    assert because_fronting("The build failed, because the disk was full.") == \
        "Because the disk was full, the build failed."
    assert because_fronting("Alice left, because she was tired.") is None  # proper noun start
    assert because_fronting("It failed, because of rain, mostly.") is None


def test_sentence_rule_b():
    assert active_to_passive("The team reviewed the proposal.") == "The proposal was reviewed by the team."
    assert active_to_passive("We tested these pumps.") == "These pumps were tested by us."
    assert active_to_passive("The team reviewed the data.") is None  # ambiguous number
    assert active_to_passive("The team went to the store.") is None
    assert active_to_passive("The team quickly reviewed the proposal.") is None


def test_sentence_rules_skip_protected_and_lists():
    text = "- The team reviewed the proposal.\nThe team reviewed the proposal. The team reviewed 3 files."
    out = SentenceRules().transform(text).output_text
    assert out == "- The team reviewed the proposal.\nThe proposal was reviewed by the team. The team reviewed 3 files."


def test_contractions():
    assert DeterministicRewrite("expand").transform("Don't stop; it's fine; I'm here.").output_text == \
        "Do not stop; it's fine; I am here."
    assert DeterministicRewrite("contract").transform("We do not know.").output_text == "We don't know."


PROTECTED_DOC = (
    "Utilize the API at https://example.com/utilize?x=1 approximately 3.5 times on 2024-01-02 [1].\n\n"
    "```python\nprint(\"hello\")  # utilize approximately\n```\n\n"
    "Inline `approximately()` and $x = approximately$ and C:\\utilize\\file.txt and /usr/utilize/bin.\n"
    "As noted, \"we utilize approximately everything\" (Smith, 2020).\n"
)


@pytest.mark.parametrize("pipeline", ["conservative", "aggressive"])
def test_protected_content_is_byte_identical(pipeline):
    out = Pipeline(pipeline).run(PROTECTED_DOC).output_text
    for s in find_protected(PROTECTED_DOC):
        assert PROTECTED_DOC[s.start:s.end] in out, (s.kind, PROTECTED_DOC[s.start:s.end])
    assert '```python\nprint("hello")  # utilize approximately\n```' in out
    assert out.startswith("Use the API")


def test_code_transform_opt_in():
    from claude_mark_research.transforms.pipeline import PipelineConfig
    out = Pipeline("lexical", PipelineConfig(transform_code=True)).run("`utilize` it").output_text
    assert out == "`use` it"


def test_pipeline_presets_and_audit():
    p = Pipeline("unicode,whitespace,punctuation")
    assert p.stage_names == ["unicode", "whitespace", "punctuation"]
    r = Pipeline("conservative").run("We  utilize it in order to win.")
    log = r.audit_log()
    assert all(e["deterministic"] for e in log)
    assert {e["operation"] for e in log} >= {"whitespace_normalization", "lexical_substitution", "phrase_substitution"}
    assert r.output_text == "We use it to win."
    assert not Pipeline("conservative").is_aggressive and Pipeline("aggressive").is_aggressive


def test_unknown_stage_rejected():
    with pytest.raises(ValueError):
        Pipeline("paraphrase")
