"""Strict CSV/XLSX validation before any paid requests."""

import csv
from dataclasses import dataclass
from pathlib import Path

FIELDS = [
    "id",
    "question_number",
    "english_target",
    "question_text",
    "option_a_romaji",
    "option_a_japanese",
    "option_b_romaji",
    "option_b_japanese",
    "option_c_romaji",
    "option_c_japanese",
    "correct_letter",
    "correct_romaji",
    "correct_japanese",
    "question_voice_text",
    "answer_voice_text",
    "question_page",
    "answer_page",
    "question_start",
    "answer_start",
]


@dataclass(frozen=True)
class Quiz:
    id: str
    number: int
    question_text: str
    answer_text: str
    correct_letter: str
    japanese: str
    question_page: int
    answer_page: int
    question_start: float
    answer_start: float


def load_rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".xlsx":
        from openpyxl import load_workbook

        book = load_workbook(path, read_only=True, data_only=True)
        try:
            values = iter(book.active.values)
            headers = next(values)
            rows = [
                dict(zip(headers, row))
                for row in values
                if any(v is not None for v in row)
            ]
        finally:
            book.close()
        return rows
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def load_quiz(path: Path) -> list[Quiz]:
    rows = load_rows(path)
    if not rows:
        raise ValueError("Quiz data is empty")
    quizzes = []
    for number, row in enumerate(rows, 1):
        missing = [
            field
            for field in FIELDS
            if row.get(field) is None or str(row[field]).strip() == ""
        ]
        if missing:
            raise ValueError(
                f"Row {number}: missing required fields: {', '.join(missing)}"
            )
        if str(row["id"]) != f"Q{number}" or str(row["question_number"]) != str(number):
            raise ValueError(
                f"Row {number}: expected Q{number} and sequential question_number"
            )
        letter = row["correct_letter"]
        if letter not in {"A", "B", "C"}:
            raise ValueError(f"Q{number}: invalid correct_letter")
        for part in ("romaji", "japanese"):
            if row[f"correct_{part}"] != row[f"option_{letter.lower()}_{part}"]:
                raise ValueError(
                    f"Q{number}: correct {part} does not match selected option"
                )
        expected = {
            "question_page": 2 * number - 1,
            "answer_page": 2 * number,
            "question_start": 9 * (number - 1),
            "answer_start": 9 * (number - 1) + 6,
        }
        if any(float(row[k]) != v for k, v in expected.items()):
            raise ValueError(f"Q{number}: page order or 6s/3s timeline is invalid")
        if (
            row["question_text"]
            != f"What is {str(row['english_target']).lower()} in Japanese?"
        ):
            raise ValueError(f"Q{number}: question does not match english_target")
        if row["question_voice_text"] != row["question_text"]:
            raise ValueError(f"Q{number}: question narration differs from question")
        if (
            row["answer_voice_text"]
            != f"The answer is {letter}. {row['correct_romaji']}. {row['correct_japanese']}."
        ):
            raise ValueError(f"Q{number}: answer narration does not match answer")
        quizzes.append(
            Quiz(
                f"Q{number}",
                number,
                row["question_voice_text"],
                row["answer_voice_text"],
                letter,
                row["correct_japanese"],
                **expected,
            )
        )
    return quizzes
