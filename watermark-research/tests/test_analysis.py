from claude_mark_research.baseline import analyze, code_statistics
from claude_mark_research.corpus import documents
from claude_mark_research.similarity import compare
from claude_mark_research.strength import StrengthThresholds, classify
from claude_mark_research.textutil import anchored_edit_distance, changed_word_count, levenshtein, sentences
from claude_mark_research.unicode_diag import analyze_unicode


def test_baseline_fields():
    b = analyze(documents()["mixed_prose_code.md"])
    for k in ("character_count", "token_count", "word_count", "sentence_count", "paragraph_count",
              "unicode_categories", "punctuation_distribution", "whitespace_distribution",
              "lexical_diversity", "repeated_ngrams", "word_frequency_top", "sentence_length_words",
              "sentence_length_histogram", "code"):
        assert k in b
    assert b["code"]["code_tokens"] > 0 and b["code"]["comment_tokens"] > 0 and b["code"]["prose_tokens"] > 0


def test_code_stats_split():
    s = code_statistics("Prose here.\n\n```py\nx = 1  # note\n```\n")
    assert s["code_blocks"] == 1 and s["comment_tokens"] == 2


def test_sentence_split_abbreviations():
    assert len(sentences("Dr. Smith arrived, e.g. at noon. It was 3.5 hours late! Next?")) == 3


def test_unicode_diag_reports_hidden_chars_with_disclaimer():
    r = analyze_unicode("a​b‌‍‮\U000E0041️ cаt")
    assert r["counts"] == {"bidi_control": 1, "homoglyph": 1, "tag_character": 1, "unusual_whitespace": 1,
                           "variation_selector": 1, "zero_width": 3}
    assert "NOT the Claude statistical watermark" in r["disclaimer"]
    assert analyze_unicode("plain text")["total_suspicious"] == 0


def test_similarity_identity_and_change():
    t = documents()["technical.md"]
    s = compare(t, t)
    assert s["tfidf_cosine"] == 1.0 and s["preservation_score"] == 1.0
    s2 = compare(t, t.replace("8080", "9090").replace("Numerous", "Many"))
    assert s2["numbers"]["ratio"] < 1 and s2["tfidf_cosine"] < 1
    assert "not semantic equivalence" in s2["label"]


def test_edit_distances():
    assert levenshtein("kitten", "sitting") == 3
    a = ("para one is here.\n\n" * 200)
    b = a.replace("one", "two", 3)
    assert anchored_edit_distance(a, b) == 9
    assert changed_word_count(a, b) == 3


def test_strength_classification_configurable():
    assert classify(0, 100, 0, 500, 0, 10)["strength"] == "NONE"
    assert classify(4, 100, 10, 500, 0, 10)["strength"] == "LIGHT"
    assert classify(10, 100, 10, 500, 0, 10)["strength"] == "MODERATE"
    assert classify(30, 100, 10, 500, 0, 10)["strength"] == "STRONG"
    assert classify(1, 100, 1, 500, 5, 10)["strength"] == "STRONG"  # sentence ratio drives it
    t = StrengthThresholds.parse("word_light=0.5,word_moderate=0.9")
    assert classify(30, 100, 10, 500, None, 10, t)["strength"] == "LIGHT"
