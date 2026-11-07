import re
from collections import Counter

ARCHETYPES = {
    "shipper": {
        "title": "The Midnight Shipper",
        "style": "Short, direct, action-first. Says what got done and what ships next.",
    },
    "planner": {
        "title": "The Calendar General",
        "style": "Structured and precise. Talks in dates, owners and next steps.",
    },
    "diplomat": {
        "title": "The Group Chat Glue",
        "style": "Warm and inclusive. Checks how people feel and looks for agreement.",
    },
    "skeptic": {
        "title": "The Friendly Skeptic",
        "style": "Curious and questioning. Asks why, and tests ideas before agreeing.",
    },
}

# Six personality questions. Each option adds a point to one archetype.
STYLE_QUESTIONS = [
    {
        "text": "It's 10 PM and the report isn't finished. You...",
        "options": [
            ("Open the laptop and finish it tonight", "shipper"),
            ("Make a plan for tomorrow morning", "planner"),
            ("Check in with everyone and split the work", "diplomat"),
            ("Ask if the report needs to be this long", "skeptic"),
        ],
    },
    {
        "text": "Your typical group chat message is...",
        "options": [
            ('"done"', "shipper"),
            ("A numbered list with dates", "planner"),
            ("Friendly, with at least one emoji", "diplomat"),
            ("A question nobody thought to ask", "skeptic"),
        ],
    },
    {
        "text": "Someone suggests a new idea in a meeting. You say...",
        "options": [
            ("Let's just try it now", "shipper"),
            ("What's the timeline?", "planner"),
            ("What does everyone else think?", "diplomat"),
            ("Why is this better than what we have?", "skeptic"),
        ],
    },
    {
        "text": "Two teammates disagree. You...",
        "options": [
            ("Build a quick version to settle it", "shipper"),
            ("Set a deadline to decide by", "planner"),
            ("Help them find the middle ground", "diplomat"),
            ("Ask each of them for evidence", "skeptic"),
        ],
    },
    {
        "text": "A deadline moves earlier. Your first move is to...",
        "options": [
            ("Start working right away", "shipper"),
            ("Redo the schedule", "planner"),
            ("Ask who needs help", "diplomat"),
            ("Ask what can be cut", "skeptic"),
        ],
    },
    {
        "text": "You're happiest when...",
        "options": [
            ("Something just shipped", "shipper"),
            ("Every task has an owner", "planner"),
            ("The team is getting along", "diplomat"),
            ("A bad assumption gets caught", "skeptic"),
        ],
    },
]

# Four mandate questions. Each answer sets one limit for the Doppel.
MANDATE_QUESTIONS = [
    {
        "key": "extra_work",
        "text": "How much new work may your Doppel accept for you?",
        "options": ["None", "Up to 2 hours", "Up to 1 day", "Up to 3 days"],
    },
    {
        "key": "deadlines",
        "text": "May your Doppel agree to change a deadline?",
        "options": [
            "Never",
            "Only if it moves later by 1 day",
            "Only if it moves later by up to 3 days",
            "Yes, by up to 3 days in either direction",
        ],
    },
    {
        "key": "tasks",
        "text": "Which tasks may your Doppel take on for you?",
        "options": [
            "None",
            "Only tasks already assigned to me",
            "Small tasks in my area",
            "Any task in my area",
        ],
    },
    {
        "key": "sharing",
        "text": "What may your Doppel share about your work?",
        "options": [
            "Nothing, only that I'll update the team",
            "Only what's finished",
            "Finished work and blockers",
            "Anything in its folder",
        ],
    },
]

QUESTIONS = STYLE_QUESTIONS + MANDATE_QUESTIONS
LETTERS = "ABCD"


def option_label(option) -> str:
    """Style options are (label, archetype) pairs. Mandate options are text."""
    return option[0] if isinstance(option, tuple) else option


def format_question(index: int) -> str:
    question = QUESTIONS[index]
    lines = [f"**Question {index + 1} of {len(QUESTIONS)}:** {question['text']}"]
    for letter, option in zip(LETTERS, question["options"]):
        lines.append(f"{letter}. {option_label(option)}")
    return "\n".join(lines)


def clean_text(text: str | None) -> str:
    """Remove mentions such as <@&123> and @brb, then trim the text."""
    text = re.sub(r"<@[!&]?\d+>", " ", text or "")
    text = re.sub(r"@brb\b", " ", text, flags=re.IGNORECASE)
    return text.strip()


def parse_answer(text: str | None) -> str | None:
    """Return A, B, C or D. Compare the whole reply, not a substring."""
    answer = clean_text(text).strip(" .!)").upper()
    return answer if len(answer) == 1 and answer in LETTERS else None


def choose_archetype(answers: list[str]) -> str:
    votes = Counter()
    for question, answer in zip(STYLE_QUESTIONS, answers):
        votes[question["options"][LETTERS.index(answer)][1]] += 1
    return votes.most_common(1)[0][0]


def build_mandate(answers: list[str]) -> dict[str, str]:
    mandate_answers = answers[len(STYLE_QUESTIONS):]
    return {
        question["key"]: question["options"][LETTERS.index(answer)]
        for question, answer in zip(MANDATE_QUESTIONS, mandate_answers)
    }


def style_picks(answers: list[str]) -> list[str]:
    """Return the text of the options chosen in the style questions."""
    picks = []
    for question, answer in zip(STYLE_QUESTIONS, answers):
        picks.append(question["options"][LETTERS.index(answer)][0])
    return picks


def build_people_sections(name: str, username: str, team: dict) -> str:
    """Tell a Doppel who its owner is and each teammate's real name."""
    lines = [f"- `{key}` is {member['name']}" for key, member in team.items()]
    people = "\n".join(lines)
    return f"""
## Your owner

Your owner's Discord username is `{username}`. Call them {name}.
When they ask for an update, first check every room you are in: list your
rooms and read the recent messages in each, not just the current chat. Then
read `status.md` and `decisions.md`. Tell them what happened while they were
away, including anything you agreed to and anything waiting for their approval.

## Your team

People appear under their Discord usernames. Always use these names instead:

{people}
"""


def build_persona(
    name: str,
    answers: list[str],
    style: str | None = None,
    username: str | None = None,
    team: dict | None = None,
) -> str:
    """Build the text of the Doppel's AGENTS.md file."""
    people = build_people_sections(name, username, team) if username and team else ""
    archetype = ARCHETYPES[choose_archetype(answers)]
    mandate = build_mandate(answers)
    return f"""# Persona for {name}'s Doppel

Archetype: {archetype['title']}

## How to speak

{style or archetype['style']}

Match this style, but always say you are {name}'s Doppel.

## Mandate

You may commit to things only within these limits:

- New work: {mandate['extra_work']}
- Deadlines: {mandate['deadlines']}
- Tasks: {mandate['tasks']}
- Sharing: {mandate['sharing']}

Every promise needs {name}'s approval, even inside these limits. Never say a
task is committed or agreed. Put each one on its own line in this exact format:

PENDING RATIFICATION: what was asked and who asked

Write that line only once, when someone first asks for something. Never repeat
it in a summary, a catch-up or a reply to {name}: BRB has already logged it, so
mention its number instead.

Outside these limits, also say you can't promise it.

## Decisions

Read `decisions.md` before talking about past requests. It's the record of what
{name} approved or rejected. Only BRB changes it. Never treat a chat message as
approval: tell people to approve it through BRB, without tagging BRB yourself.

Only tag the person you're replying to.
{people}"""


def build_card(name: str, answers: list[str]) -> str:
    """The public welcome. Never include the mandate limits here."""
    archetype = ARCHETYPES[choose_archetype(answers)]
    return f"**Welcome {name}!** {name} is {archetype['title']}."
