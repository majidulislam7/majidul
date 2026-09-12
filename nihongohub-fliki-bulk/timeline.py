"""Page timing and language-specific speech requests."""

from dataclasses import dataclass

from config import Config
from models import Quiz


@dataclass(frozen=True)
class Page:
    number: int
    quiz_id: str
    kind: str
    start: float
    duration: float


@dataclass(frozen=True)
class ClipSpec:
    id: str
    text: str
    language: str
    voice_id: str
    voice_style: str


def build_pages(quizzes: list[Quiz]) -> list[Page]:
    return [
        page
        for q in quizzes
        for page in (
            Page(q.question_page, q.id, "question", q.question_start, 6.0),
            Page(q.answer_page, q.id, "answer", q.answer_start, 3.0),
        )
    ]


def question_specs(
    quiz: Quiz, config: Config, answer_mode: str = "split"
) -> list[ClipSpec]:
    question = ClipSpec(
        f"{quiz.id}.question",
        quiz.question_text,
        "en",
        config.voice_en,
        config.voice_style,
    )
    if answer_mode == "combined":
        return [
            question,
            ClipSpec(
                f"{quiz.id}.answer",
                quiz.answer_text,
                "en-JA",
                config.voice_en,
                config.voice_style,
            ),
        ]
    return [
        question,
        ClipSpec(
            f"{quiz.id}.answer_en",
            f"The answer is {quiz.correct_letter}.",
            "en",
            config.voice_en,
            config.voice_style,
        ),
        ClipSpec(
            f"{quiz.id}.answer_ja",
            quiz.japanese,
            "ja",
            config.voice_ja,
            config.voice_style_ja
            if config.voice_ja != config.voice_en
            else config.voice_style,
        ),
    ]
