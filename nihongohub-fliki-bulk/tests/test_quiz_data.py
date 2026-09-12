import csv

import pytest

from models import FIELDS, load_quiz, load_rows

EXPECTED = [
    (
        "Cat",
        "B",
        "Neko",
        "ねこ",
        [("Inu", "いぬ"), ("Neko", "ねこ"), ("Sakana", "さかな")],
    ),
    (
        "Dog",
        "A",
        "Inu",
        "いぬ",
        [("Inu", "いぬ"), ("Sakana", "さかな"), ("Hana", "はな")],
    ),
    (
        "Apple",
        "C",
        "Ringo",
        "りんご",
        [("Hon", "ほん"), ("Mizu", "みず"), ("Ringo", "りんご")],
    ),
    (
        "Fish",
        "B",
        "Sakana",
        "さかな",
        [("Hana", "はな"), ("Sakana", "さかな"), ("Neko", "ねこ")],
    ),
    ("Book", "C", "Hon", "ほん", [("Kasa", "かさ"), ("Yama", "やま"), ("Hon", "ほん")]),
    (
        "Water",
        "A",
        "Mizu",
        "みず",
        [("Mizu", "みず"), ("Kuruma", "くるま"), ("Inu", "いぬ")],
    ),
    (
        "Flower",
        "B",
        "Hana",
        "はな",
        [("Ringo", "りんご"), ("Hana", "はな"), ("Sakana", "さかな")],
    ),
    (
        "Mountain",
        "A",
        "Yama",
        "やま",
        [("Yama", "やま"), ("Hon", "ほん"), ("Kasa", "かさ")],
    ),
    (
        "Umbrella",
        "C",
        "Kasa",
        "かさ",
        [("Kuruma", "くるま"), ("Neko", "ねこ"), ("Kasa", "かさ")],
    ),
    (
        "Car",
        "A",
        "Kuruma",
        "くるま",
        [("Kuruma", "くるま"), ("Mizu", "みず"), ("Yama", "やま")],
    ),
]


def test_exact_storyboard(quiz_path):
    rows = load_rows(quiz_path)
    assert len(rows) == 10
    assert [q.id for q in load_quiz(quiz_path)] == [f"Q{i}" for i in range(1, 11)]
    for row, (target, letter, romaji, ja, options) in zip(rows, EXPECTED):
        assert (
            row["english_target"],
            row["correct_letter"],
            row["correct_romaji"],
            row["correct_japanese"],
        ) == (target, letter, romaji, ja)
        assert row["question_text"] == f"What is {target.lower()} in Japanese?"
        for key, option in zip("abc", options):
            assert (
                row[f"option_{key}_romaji"],
                row[f"option_{key}_japanese"],
            ) == option


def test_workbook_matches_csv(quiz_path):
    from openpyxl import load_workbook

    path = quiz_path.with_name("NihongoHub_Fliki_Bulk_10.xlsx")
    assert load_quiz(path) == load_quiz(quiz_path)
    book = load_workbook(path)
    assert book.active.freeze_panes == "E2"
    assert book.active["A1"].font.bold
    book.close()


@pytest.mark.parametrize(
    "key,value",
    [
        ("correct_letter", "D"),
        ("correct_japanese", "いぬ"),
        ("answer_page", "1"),
        ("question_start", "nan"),
        ("answer_start", "7"),
        ("option_a_romaji", ""),
        ("question_voice_text", "wrong"),
        ("answer_voice_text", "wrong"),
    ],
)
def test_invalid_rows_rejected(quiz_path, tmp_path, key, value):
    rows = load_rows(quiz_path)
    rows[0][key] = value
    path = tmp_path / "bad.csv"
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError):
        load_quiz(path)
