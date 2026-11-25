from app.sentence_splitter import split_sentences


def test_split_empty_and_whitespace():
    assert split_sentences("") == []
    assert split_sentences("   \n\t  ") == []


def test_split_single_sentence():
    assert split_sentences("Zdravo svijete.") == ["Zdravo svijete."]


def test_split_multiple_sentences():
    text = "Prva rečenica. Druga rečenica! Treća rečenica?"
    assert split_sentences(text) == [
        "Prva rečenica.",
        "Druga rečenica!",
        "Treća rečenica?",
    ]


def test_split_preserves_abbreviations():
    text = "Dr. Petrović je došao. Sve je u redu."
    assert split_sentences(text) == [
        "Dr. Petrović je došao.",
        "Sve je u redu.",
    ]
