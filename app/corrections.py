# SPDX-License-Identifier: AGPL-3.0-only
"""Self-service corrections of submitted pairs.

A participant can review the real pairs this session submitted and correct any of them,
also after finishing. A correction is the export's participant-correction audit record,
built by private_export.write_correction exactly like the operator command. The answers
row, payment, assignments, the study meter, the quality checks and closure never change:
a correction is not a new read.
"""

import json
from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .private_export import answer_in_force

# Correction saves per session in one window, counted like the resume attempts (code
# constants: the frozen configuration must not change).
RATE_LIMIT = 20
RATE_WINDOW_SECONDS = 900

try:
    ROME = ZoneInfo("Europe/Rome")
except ZoneInfoNotFoundError:  # pragma: no cover - only without a system time zone database
    ROME = timezone(timedelta(hours=1), "CET")  # Rome in November

MONTHS = {
    "it": (
        "gennaio",
        "febbraio",
        "marzo",
        "aprile",
        "maggio",
        "giugno",
        "luglio",
        "agosto",
        "settembre",
        "ottobre",
        "novembre",
        "dicembre",
    ),
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
}


def when(epoch, lang):
    """«il 14 novembre 2026 alle 15:42» / "on 14 November 2026 at 15:42", Rome time."""
    moment = datetime.fromtimestamp(epoch, UTC).astimezone(ROME)
    month = MONTHS[lang][moment.month - 1]
    clock = f"{moment.hour}:{moment.minute:02d}"
    if lang == "en":
        return f"on {moment.day} {month} {moment.year} at {clock}"
    day = {1: "il 1°", 8: "l’8", 11: "l’11"}.get(moment.day, f"il {moment.day}")
    return f"{day} {month} {moment.year} {'all’' if moment.hour == 1 else 'alle '}{clock}"


def submitted_answers(db, session_id):
    """Real pairs this session submitted, oldest first: no practice, controls or retired pairs."""
    return db.execute(
        "SELECT a.*,i.data AS item_data FROM answers a JOIN items i ON i.id=a.item_id "
        "WHERE a.session_id=? AND a.kind='real' AND i.retired=0 ORDER BY a.submitted,a.id",
        (session_id,),
    ).fetchall()


def submitted_count(db, session_id):
    return db.execute(
        "SELECT COUNT(*) FROM answers a JOIN items i ON i.id=a.item_id "
        "WHERE a.session_id=? AND a.kind='real' AND i.retired=0",
        (session_id,),
    ).fetchone()[0]


def find(db, session_id, assignment_id):
    """(list number, answer row) of one of this session's submitted pairs, else (None, None)."""
    for number, row in enumerate(submitted_answers(db, session_id), 1):
        if row["assignment_id"] == assignment_id:
            return number, row
    return None, None


def listing(db, session_id, lang):
    pairs = []
    for number, row in enumerate(submitted_answers(db, session_id), 1):
        item = json.loads(row["item_data"])
        current = answer_in_force(db, row)
        pairs.append(
            {
                "number": number,
                "assignment_id": row["assignment_id"],
                "submitted": when(row["submitted"], lang),
                "corrected": when(current["corrected_at"], lang)
                if current["corrected_at"] is not None
                else None,
                "titles": {side: item[side]["article"]["title"] for side in ("a", "b")},
            }
        )
    return pairs


def form_values(path, rationale):
    """A canonical answer path as the pair form's control values (names as in pair.html).

    The page script restores these like a draft, so the question flow and its checks
    are those of a normal answer.
    """
    values = {"rationale": rationale}
    for side in ("a", "b"):
        for field, row in path["q1"][side].items():
            values[f"q1.{side}.{field}"] = row["answer"]
            values[f"q1.{side}.{field}.problems"] = list(row["problems"])
    if "q1_relevance" in path:
        values["q1.relevance"] = path["q1_relevance"]
    q2 = path.get("q2", {})
    for field, row in q2.items():
        values[f"q2.{field}"] = row["answer"]
        # The outcome has one fixed reason and no control for it.
        if field != "outcome" and "reason" in row:
            values[f"q2.{field}.reason"] = row["reason"]
        if "detail" in row:
            values[f"q2.{field}.detail"] = row["detail"]
    # The form asks for the main reason only when more than one check fails.
    if sum(row["answer"] != "yes" for row in q2.values()) > 1 and "q2_primary" in path:
        values["q2.primary"] = path["q2_primary"]
    for key in ("q3", "q4"):
        if key in path:
            values[key] = path[key]
    if "q5" in path:
        values["q5.answer"] = path["q5"]["answer"]
        for key in ("factor", "detail"):
            if key in path["q5"]:
                values[f"q5.{key}"] = path["q5"][key]
    return values
