# SPDX-License-Identifier: AGPL-3.0-only
"""Every mutating function is called inside one BEGIN IMMEDIATE transaction.

A slot is one of a pair's 2–4 independent reads. Replacing an excluded paid
answer consumes the reserve. Reinstatement selects the earliest eligible
answer in each slot, so it cannot create extra votes or erase payments.
"""

import collections
import hashlib
import json
import statistics
import time
import uuid

LABELS = (
    "extraction_error",
    "not_comparable",
    "concordant",
    "not_replicated",
    "apparent_contradiction",
    "contradictory",
)
FACTORS = (
    "population",
    "region",
    "disease_subtype",
    "design",
    "comparator",
    "molecule_class",
    "dose",
    "duration",
    "outcome_definition",
    "sample",
    "none",
    "unknown",
    "other",
)


def uid():
    return uuid.uuid4().hex


def votes(db, item_id):
    rows = db.execute(
        """SELECT a.* FROM answers a JOIN sessions s ON s.id=a.session_id
        LEFT JOIN identities i ON i.session_id=s.id
        WHERE a.item_id=? AND a.kind='real' AND a.paid=1 AND s.excluded=0
        AND COALESCE(i.needs_review,0)=0
        ORDER BY a.submitted,a.id""",
        (item_id,),
    ).fetchall()
    slots = {}
    for row in rows:
        slots.setdefault(row["slot"], row)
    return list(slots.values())


def fourth_cap_withdrawn(db):
    """Fourth-read cap withdrawal: {} before activation, else {"activated": epoch}.
    From activation every three-way split gets its fourth read; MAX_FOURTH_PAIRS stays in
    the frozen configuration but no longer limits them. FOURTH_READS stays the ceiling:
    there is no fifth read."""
    row = db.execute("SELECT value FROM metadata WHERE key='fourth_cap_withdrawn'").fetchone()
    return json.loads(row[0]) if row else {}


def finally_unresolved(state, cfg):
    """No consensus after the last read the protocol allows (FOURTH_READS)."""
    return state["status"] == "unresolved" and len(state["votes"]) >= cfg["FOURTH_READS"]


def pair_state(db, item_id, cfg):
    rows = votes(db, item_id)
    n = len(rows)
    counts = collections.Counter(r["label"] for r in rows)
    ranked = counts.most_common()
    if (
        n >= cfg["INITIAL_READS"]
        and ranked[0][1] >= 2
        and (len(ranked) == 1 or ranked[0][1] > ranked[1][1])
    ):
        return {"status": "resolved", "target": n, "votes": rows}
    if n >= cfg["FOURTH_READS"]:
        return {"status": "unresolved", "target": n, "votes": rows}
    target = cfg["INITIAL_READS"] if n < cfg["INITIAL_READS"] else n + 1
    if target == cfg["FOURTH_READS"]:
        granted = db.execute("SELECT fourth_granted FROM items WHERE id=?", (item_id,)).fetchone()[
            0
        ]
        used = db.execute("SELECT COUNT(*) FROM items WHERE fourth_granted=1").fetchone()[0]
        if (
            not granted
            and used >= cfg["MAX_FOURTH_PAIRS"]
            and not fourth_cap_withdrawn(db).get("activated")
        ):
            return {"status": "unresolved", "target": n, "votes": rows}
    return {"status": "pending", "target": target, "votes": rows}


def ledger(db, cfg):
    amendment = pay_amendment(db)
    paid, replacement, synthetic_paid, late_paid = db.execute(
        "SELECT COALESCE(SUM(paid*(kind='real')),0),COALESCE(SUM(replacement*paid),0),COALESCE(SUM(paid*(kind!='real')),0),COALESCE(SUM(late_paid AND NOT paid),0) FROM answers"
    ).fetchone()
    fixed = db.execute("SELECT COUNT(*) FROM sessions WHERE fixed_fee=1").fetchone()[0]
    reserved, replacement_reserved = db.execute(
        "SELECT COUNT(*),COALESCE(SUM(replacement),0) FROM assignments WHERE kind='real' AND state='reserved'"
    ).fetchone()
    synthetic_issued = db.execute("SELECT COUNT(*) FROM assignments WHERE kind!='real'").fetchone()[
        0
    ]
    price, params = price_sql(amendment, cfg)
    priced = db.execute(
        f"SELECT COALESCE(SUM({price}),0) FROM answers WHERE paid=1 OR late_paid=1", params
    ).fetchone()[0]
    spend = priced + fixed * cfg["FIXED_FEE_CENTS"]
    # With the payment amendment active there is no ceiling, so no worst case to report.
    lifted = bool(amendment.get("activated"))
    return {
        "paid_reads": paid,
        "replacement_reads": replacement,
        "fixed_fees": fixed,
        "synthetic_paid": synthetic_paid,
        "late_paid": late_paid,
        "synthetic_issued": synthetic_issued,
        "reserved_reads": reserved,
        "replacement_reserved": replacement_reserved,
        "spend_cents": spend,
        "worst_case_cents": None if lifted else cfg["WORST_CASE_CENTS"],
        "worst_case_left_cents": None if lifted else max(0, cfg["WORST_CASE_CENTS"] - spend),
    }


def closure(db, cfg):
    if db.execute("SELECT value FROM metadata WHERE key='manual_closed'").fetchone()[0] == "1":
        return True, "manual"
    if not limits_lifted(db) and ledger(db, cfg)["paid_reads"] >= cfg["PAID_READ_CAP"]:
        return True, "paid_cap"
    states = [
        pair_state(db, r[0], cfg)["status"]
        for r in db.execute("SELECT id FROM items WHERE retired=0")
    ]
    if states and all(s != "pending" for s in states):
        return True, "complete"
    # The reserve may be exhausted before all excluded votes can be replaced.
    # Keep those pairs explicitly pending; do not silently call them resolved.
    return False, "collecting"


# Programmes admitted after the signed configuration. Labels and
# export buckets are fixed here and reviewed with the code; `flask add-programme` only
# activates one and records when. The frozen configuration snapshot never changes.
AMENDABLE_PROGRAMMES = {
    "bme": {
        "labels": {"it": "Ingegneria biomedica", "en": "Biomedical Engineering"},
        "export_bucket": "biomedical_engineering",
    },
}


def amended_programmes(db):
    """Activated amendable programme -> activation time (epoch seconds)."""
    row = db.execute("SELECT value FROM metadata WHERE key='amended_programmes'").fetchone()
    return json.loads(row[0]) if row else {}


def programmes(db, cfg):
    """Programmes offered in the final form: configured ones, then activated amendments."""
    active = amended_programmes(db)
    return {
        **cfg["ELIGIBLE_PROGRAMMES"],
        **{
            key: AMENDABLE_PROGRAMMES[key]["labels"]
            for key in AMENDABLE_PROGRAMMES
            if key in active
        },
    }


# Mid-study rate change. None is defined in this release: the mechanism stays
# inactive (no CLI command activates it), so every answer is priced at
# PRICE_PER_PAIR. The keys document what an activated change would set.
PAY_AMENDMENT = {
    "effective": 0,
    "real_cents": 0,
    "personal_cents": 0,
    "personal_sessions_max": 0,
    # Once active, these no longer stop anything: they only sized the worst-case spend.
    "lifted": ("BUDGET_CAP_EUR", "PAID_READ_CAP", "MAX_SYNTHETIC_SCREENS"),
    # These are the reading protocol and still apply.
    "kept": ("MAX_FOURTH_PAIRS", "REPLACEMENT_READS"),
}


def pay_amendment(db):
    """{} before activation, else {"activated": epoch, "personal_sessions": {id: epoch}}."""
    row = db.execute("SELECT value FROM metadata WHERE key='pay_amendment'").fetchone()
    return json.loads(row[0]) if row else {}


def limits_lifted(db):
    """True once the payment amendment is active: no money or global read ceilings."""
    return bool(pay_amendment(db).get("activated"))


def answer_price(amendment, cfg, kind, session_id, submitted):
    """Cents for one paid answer; price_sql applies the same rule inside SQLite."""
    if not amendment.get("activated") or kind != "real" or submitted < PAY_AMENDMENT["effective"]:
        return cfg["PRICE_PER_PAIR_CENTS"]
    if session_id in amendment.get("personal_sessions", {}):
        return PAY_AMENDMENT["personal_cents"]
    return PAY_AMENDMENT["real_cents"]


def price_sql(amendment, cfg):
    """SQL expression and parameters that price one `answers` row like answer_price."""
    base = cfg["PRICE_PER_PAIR_CENTS"]
    if not amendment.get("activated"):
        return "?", [base]
    personal = sorted(amendment.get("personal_sessions", {}))
    case = "CASE WHEN kind!='real' OR submitted<? THEN ?"
    params = [PAY_AMENDMENT["effective"], base]
    if personal:
        case += f" WHEN session_id IN ({','.join('?' * len(personal))}) THEN ?"
        params += [*personal, PAY_AMENDMENT["personal_cents"]]
    return f"({case} ELSE ? END)", [*params, PAY_AMENDMENT["real_cents"]]


def pay_view(db, cfg, session_id=None):
    """Rates shown to the viewer: a personal rate appears only inside its own session."""
    amendment = pay_amendment(db)
    base = cfg["PRICE_PER_PAIR_CENTS"]
    return {
        "rate_cents": answer_price(amendment, cfg, "real", session_id, PAY_AMENDMENT["effective"]),
        "practice_cents": base,
        "old_cents": base,
        "amended": bool(amendment.get("activated")),
    }


def superseded(db):
    """New item ID -> retired item ID, from the current package manifest."""
    row = db.execute("SELECT value FROM metadata WHERE key='package_manifest'").fetchone()
    return json.loads(row[0]).get("supersedes", {}) if row else {}


# Coverage first. An arm counts as covered at a step when COVERAGE_PER_ARM of its pairs
# have that many reads done or in progress; ties end on a pseudo-random order fixed in
# advance.
COVERAGE_PER_ARM = 5
COVERAGE_ORDER_SALT = "metabolic-evidence-coverage-20261115:"


def coverage_rank(item_id):
    return hashlib.sha256((COVERAGE_ORDER_SALT + item_id).encode()).hexdigest()


def coverage_priority(arm, valid, ordinal, cover):
    """Sort key head for the next read of a pair; `ordinal` is the read it would be.

    Steps: 1 first reads in arms with fewer than COVERAGE_PER_ARM pairs read once (done
    or in progress); 2 second reads in arms with fewer than COVERAGE_PER_ARM pairs read
    twice, pairs with a valid read first; 3 third and fourth reads; 4 other second reads,
    pairs with a valid read first; 5 other first reads. Then the arm furthest behind on
    the measure of the step, then more valid reads.
    """
    once, twice = cover[arm]
    if ordinal <= 1:
        return (1 if once < COVERAGE_PER_ARM else 5, 0, once, -valid)
    if ordinal == 2:
        return (2 if twice < COVERAGE_PER_ARM else 4, 0 if valid else 1, twice, -valid)
    return (3, 0, twice, -valid)


def free_slots(db, cfg, session_id=None):
    l = ledger(db, cfg)
    if not limits_lifted(db) and l["paid_reads"] + l["reserved_reads"] >= cfg["PAID_READ_CAP"]:
        return []
    seen = set()
    if session_id:
        seen = {
            r[0]
            for r in db.execute("SELECT item_id FROM assignments WHERE session_id=?", (session_id,))
        }
        # A pair re-extracted after a package rebase is the same pair for a reader who
        # already read its retired version.
        seen |= {new for new, old in superseded(db).items() if old in seen}
    # Reads done (valid votes) and in progress (held reads) for every live pair. free_slots
    # runs in reserve() right after release_stale, so every held read is an active one.
    held = collections.Counter(
        r[0]
        for r in db.execute(
            "SELECT item_id FROM assignments WHERE state='reserved' AND kind='real'"
        )
    )
    live = {}
    cover = collections.defaultdict(lambda: [0, 0])
    # Fourth-read cap withdrawn: from activation, a pair finally unresolved after four
    # reads no longer counts for step 2, so step 2 resumes for its arm until 5 pairs can
    # still resolve.
    withdrawn = bool(fourth_cap_withdrawn(db).get("activated"))
    for item in db.execute(
        "SELECT id,COALESCE(json_extract(data,'$.arm'),'') AS arm FROM items "
        "WHERE retired=0 ORDER BY id"
    ).fetchall():
        arm = item["arm"]
        state = pair_state(db, item["id"], cfg)
        valid = len(state["votes"])
        live[item["id"]] = (arm, valid, state)
        reads = valid + held[item["id"]]
        cover[arm][0] += reads >= 1
        cover[arm][1] += reads >= 2 and not (withdrawn and finally_unresolved(state, cfg))
    candidates = []
    for item_id, (arm, valid, state) in live.items():
        if item_id in seen:
            continue
        if state["status"] != "pending":
            continue
        occupied = {r["slot"] for r in state["votes"]}
        active = {
            r[0]
            for r in db.execute(
                "SELECT slot FROM assignments WHERE item_id=? AND state='reserved' AND kind='real'",
                (item_id,),
            )
        }
        remaining = state["target"] - len(occupied) - len(active)
        for slot in range(1, cfg["FOURTH_READS"] + 1):
            if remaining <= 0:
                break
            if slot in occupied or slot in active:
                continue
            # A fourth slot is never created unless three valid votes disagree.
            if slot == 4 and state["target"] < 4:
                continue
            replacement = bool(
                db.execute(
                    "SELECT 1 FROM answers WHERE item_id=? AND slot=? AND paid=1", (item_id, slot)
                ).fetchone()
            )
            if (
                replacement
                and l["replacement_reads"] + l["replacement_reserved"] >= cfg["REPLACEMENT_READS"]
            ):
                continue
            ordinal = valid + held[item_id] + 1
            candidates.append(
                (
                    (
                        *coverage_priority(arm, valid, ordinal, cover),
                        coverage_rank(item_id),
                        slot,
                    ),
                    (
                        item_id,
                        slot,
                        int(replacement),
                        state["target"] - len(occupied),
                        len(occupied),
                    ),
                )
            )
            remaining -= 1
    return [candidate for _, candidate in sorted(candidates)]


def release_unopened(db):
    """Release real reads reserved but never opened: blocks reserved before the
    one-pair-at-a-time rule. No other path creates them."""
    return db.execute(
        "UPDATE assignments SET state='released' "
        "WHERE kind='real' AND state='reserved' AND started IS NULL"
    ).rowcount


def release_inactive(db, cfg, now):
    """Release the real reads held by sessions with neither a submission nor any other
    action for STALE_MINUTES. A session still working keeps the pair it has open, however
    long since its last submission."""
    cutoff = now - cfg["STALE_MINUTES"] * 60
    return db.execute(
        """UPDATE assignments SET state='released'
        WHERE kind='real' AND state='reserved' AND session_id IN
        (SELECT s.id FROM sessions s WHERE s.last_submission<=? AND NOT EXISTS
         (SELECT 1 FROM actions a WHERE a.session_id=s.id AND a.created>?))""",
        (cutoff, cutoff),
    ).rowcount


def release_stale(db, cfg, now):
    """Called by every reserve(): legacy unopened reads, then reads of inactive sessions."""
    return release_unopened(db) + release_inactive(db, cfg, now)


def checkpoint_due(db, cfg, session_id):
    """True when the real pairs answered end a group: the practice pair plus
    INITIAL_REAL_BATCH, then every CONTINUE_BATCH (without practice, MIN_PAYOUT_PAIRS
    first). The "continue or finish" page comes at the same counts as with blocks."""
    real = db.execute(
        "SELECT COUNT(*) FROM answers WHERE session_id=? AND kind='real'", (session_id,)
    ).fetchone()[0]
    practice = db.execute(
        "SELECT 1 FROM assignments WHERE session_id=? AND kind='practice'", (session_id,)
    ).fetchone()
    first = cfg["INITIAL_REAL_BATCH"] if practice else cfg["MIN_PAYOUT_PAIRS"]
    return real >= first and (real - first) % cfg["CONTINUE_BATCH"] == 0


def add_synthetic(db, cfg, session_id, kind, position, now):
    if (
        not limits_lifted(db)
        and ledger(db, cfg)["synthetic_issued"] >= cfg["MAX_SYNTHETIC_SCREENS"]
    ):
        return False
    size = 3 if kind == "practice" else 8
    used = {
        r[0]
        for r in db.execute("SELECT item_id FROM assignments WHERE session_id=?", (session_id,))
    }
    offset = db.execute("SELECT COUNT(*) FROM assignments WHERE kind=?", (kind,)).fetchone()[0]
    for i in range(size):
        item_id = f"{kind}-{(offset + i) % size + 1}"
        if item_id not in used:
            db.execute(
                "INSERT INTO assignments(id,session_id,item_id,kind,position,created) VALUES(?,?,?,?,?,?)",
                (uid(), session_id, item_id, kind, position, now),
            )
            return True
    return False


def reserve(db, cfg, session_id, admission=False, now=None, first_real=False):
    """Assign the session's next pair, one at a time.

    Admission still requires enough distinct free pairs to reach the payment threshold,
    without reserving them, and then gives the practice pair when enabled. Otherwise the
    next pair is a hidden control when one is due, else the first free real read in
    coverage order. `first_real` is kept for callers; groups are counted by
    checkpoint_due, not reserved.
    """
    now = time.time() if now is None else now
    s = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if s["excluded"] or s["quality_failed"] or s["finished"] or closure(db, cfg)[0]:
        return []
    if db.execute(
        "SELECT 1 FROM assignments WHERE session_id=? AND state='reserved'", (session_id,)
    ).fetchone():
        return []
    release_stale(db, cfg, now)
    if admission:
        options = free_slots(db, cfg, session_id)
        capacity = (
            float("inf")
            if limits_lifted(db)
            else cfg["PAID_READ_CAP"]
            - ledger(db, cfg)["paid_reads"]
            - ledger(db, cfg)["reserved_reads"]
        )
        # Enough distinct free pairs to reach the payment threshold; the practice pair
        # counts towards it, as before. Nothing beyond the first pair is reserved.
        needed = (
            cfg["ADMISSION_MIN_READS"]
            if cfg["PRACTICE_ENABLED"]
            else max(cfg["ADMISSION_MIN_READS"], cfg["MIN_PAYOUT_PAIRS"])
        )
        if min(len({o[0] for o in options}), capacity) < needed:
            return []
    position = db.execute(
        "SELECT COALESCE(MAX(position),-1)+1 FROM assignments WHERE session_id=?", (session_id,)
    ).fetchone()[0]
    selected = []
    if (
        (admission and cfg["PRACTICE_ENABLED"])
        and add_synthetic(db, cfg, session_id, "practice", position, now)
    ) or (
        cfg["HIDDEN_CONTROLS_ENABLED"]
        and position >= cfg["CONTROL_FIRST_POSITION"]
        and (position - cfg["CONTROL_FIRST_POSITION"]) % cfg["CONTROL_INTERVAL"] == 0
        and add_synthetic(db, cfg, session_id, "control", position, now)
    ):
        selected = [
            db.execute(
                "SELECT id FROM assignments WHERE session_id=? AND position=?",
                (session_id, position),
            ).fetchone()[0]
        ]
    else:
        options = free_slots(db, cfg, session_id)
        if options:
            item_id, slot, replacement, _, _ = options[0]
            if slot == 4:
                db.execute("UPDATE items SET fourth_granted=1 WHERE id=?", (item_id,))
            selected = [uid()]
            db.execute(
                """INSERT INTO assignments(id,session_id,item_id,kind,slot,position,created,replacement)
                VALUES(?,?,?,'real',?,?,?,?)""",
                (selected[0], session_id, item_id, slot, position, now, replacement),
            )
    if selected:
        db.execute(
            "UPDATE sessions SET stage='work',last_submission=? WHERE id=?", (now, session_id)
        )
        activate_next(db, session_id, now)
    return selected


def next_pair(db, cfg, session_id, now=None):
    """After an answer: the next pair, unless the answer ends a group (checkpoint)."""
    if checkpoint_due(db, cfg, session_id):
        return []
    return reserve(db, cfg, session_id, now=now)


def activate_next(db, session_id, now):
    row = db.execute(
        "SELECT id FROM assignments WHERE session_id=? AND state='reserved' ORDER BY position LIMIT 1",
        (session_id,),
    ).fetchone()
    if row:
        db.execute("UPDATE assignments SET started=COALESCE(started,?) WHERE id=?", (now, row[0]))


def exclude(db, session_id, reason, value=True, now=None, automatic=False):
    now = time.time() if now is None else now
    db.execute("UPDATE sessions SET excluded=? WHERE id=?", (int(value), session_id))
    if not automatic:
        db.execute(
            "UPDATE sessions SET manual_quality_override=1,quality_failed=? WHERE id=?",
            (int(value), session_id),
        )
    if value:
        db.execute(
            "UPDATE assignments SET state='released' WHERE session_id=? AND state='reserved' AND kind='real'",
            (session_id,),
        )
    db.execute(
        "INSERT INTO audit(session_id,action,reason,created) VALUES(?,?,?,?)",
        (session_id, "exclude" if value else "include", reason, now),
    )


def earnings(db, cfg, session_id):
    price, params = price_sql(pay_amendment(db), cfg)
    count, real, priced = db.execute(
        f"SELECT COUNT(*),COALESCE(SUM(kind='real'),0),COALESCE(SUM({price}),0) FROM answers "
        "WHERE session_id=? AND (paid=1 OR late_paid=1)",
        (*params, session_id),
    ).fetchone()
    session = db.execute(
        "SELECT fixed_fee,payment_exception FROM sessions WHERE id=?", (session_id,)
    ).fetchone()
    fixed = session["fixed_fee"]
    identity = db.execute(
        "SELECT needs_review FROM identities WHERE session_id=?", (session_id,)
    ).fetchone()
    review = bool(identity and identity["needs_review"])
    accrued = priced + fixed * cfg["FIXED_FEE_CENTS"]
    return {
        "count": count,
        "real": real,
        "fixed": bool(fixed),
        "cents": accrued,
        "payable_cents": accrued
        if not review and (count >= cfg["MIN_PAYOUT_PAIRS"] or session["payment_exception"])
        else 0,
        "needs_review": review,
        "payment_exception": session["payment_exception"],
    }


def site_stop_reason(db, cfg, session_id):
    """Read-only reason for accepting accrued pay below the usual threshold."""
    s = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    earned = earnings(db, cfg, session_id)
    if not earned["count"] or earned["count"] >= cfg["MIN_PAYOUT_PAIRS"]:
        return ""
    if s["payment_exception"]:
        return s["payment_exception"]
    if s["finished"]:
        return ""  # An earlier voluntary finish must not become a site-imposed stop.
    closed, reason = closure(db, cfg)
    if closed:
        return "collection_" + reason
    if s["excluded"] or s["quality_failed"]:
        return "site_quality_stop"
    if (
        not s["finished"]
        and not db.execute(
            "SELECT 1 FROM assignments WHERE session_id=? AND state='reserved'", (session_id,)
        ).fetchone()
        and not free_slots(db, cfg, session_id)
    ):
        return "no_work_available"
    return ""


def record_payment_exception(db, cfg, session_id):
    reason = site_stop_reason(db, cfg, session_id)
    if reason:
        updated = db.execute(
            "UPDATE sessions SET payment_exception=? WHERE id=? AND payment_exception=''",
            (reason, session_id),
        ).rowcount
        if updated:
            db.execute(
                "INSERT INTO audit(session_id,action,reason,created) VALUES(?,?,?,?)",
                (session_id, "payment-exception", reason, time.time()),
            )
    return reason


def submit(
    db,
    cfg,
    session_id,
    assignment_id,
    label,
    factor,
    rationale,
    seconds,
    synthetic,
    now=None,
    *,
    instrument=None,
    comment="",
):
    now = time.time() if now is None else now
    if label not in LABELS or factor not in FACTORS or len(rationale) > 2000:
        raise ValueError("invalid_answer")
    a = db.execute(
        "SELECT * FROM assignments WHERE id=? AND session_id=?", (assignment_id, session_id)
    ).fetchone()
    if not a:
        raise ValueError("invalid_assignment")
    existing = db.execute(
        "SELECT * FROM answers WHERE assignment_id=?", (assignment_id,)
    ).fetchone()
    if existing:
        return dict(existing)
    from .instrument import validate_path

    if not instrument:
        raise ValueError("A complete answer path is required")
    validated = validate_path(instrument["path"], rationale)
    if (validated["label"], validated["factor"]) != (label, factor):
        raise ValueError("Answer does not match its path")
    instrument = validated
    if not isinstance(comment, str) or len(comment) > 2000 or (comment and not cfg["PREVIEW_MODE"]):
        raise ValueError("Invalid preview comment")
    s = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    paid = replacement = late_paid = 0
    l = ledger(db, cfg)
    extra_fixed = (
        cfg["FIXED_FEE_CENTS"] > 0
        and not s["fixed_fee"]
        and earnings(db, cfg, session_id)["count"] + 1 >= cfg["FIXED_FEE_MIN_PAIRS"]
    )
    amendment = pay_amendment(db)
    lifted = bool(amendment.get("activated"))
    cost = answer_price(amendment, cfg, a["kind"], session_id, now) + (
        cfg["FIXED_FEE_CENTS"] if extra_fixed else 0
    )
    # The payment amendment removes the money cap: within_budget is then always true.
    within_budget = lifted or l["spend_cents"] + cost <= cfg["BUDGET_CAP_CENTS"]
    if a["kind"] != "real" and a["state"] == "reserved" and not s["finished"]:
        # Late payments can consume headroom previously available to practice/controls.
        paid = int(within_budget)
    if a["kind"] == "real" and not s["finished"] and not s["excluded"] and not closure(db, cfg)[0]:
        state = pair_state(db, a["item_id"], cfg)
        occupied = {r["slot"] for r in state["votes"]}
        replacement = int(
            bool(
                db.execute(
                    "SELECT 1 FROM answers WHERE item_id=? AND slot=? AND paid=1",
                    (a["item_id"], a["slot"]),
                ).fetchone()
            )
        )
        other_reserved, other_replacements = db.execute(
            "SELECT COUNT(*),COALESCE(SUM(replacement),0) FROM assignments WHERE kind='real' AND state='reserved' AND NOT (item_id=? AND slot=?)",
            (a["item_id"], a["slot"]),
        ).fetchone()
        if (
            state["status"] == "pending"
            and a["slot"] not in occupied
            and (lifted or l["paid_reads"] + other_reserved < cfg["PAID_READ_CAP"])
            and (
                not replacement
                or l["replacement_reads"] + other_replacements < cfg["REPLACEMENT_READS"]
            )
            and (not extra_fixed or l["fixed_fees"] < cfg["MAX_FIXED_FEES"])
            and within_budget
        ):
            paid = 1
            # A late answer can reclaim an unfilled slot. The newer holder's
            # work will still be stored and may qualify for a surplus payment.
            db.execute(
                "UPDATE assignments SET state='released' WHERE item_id=? AND slot=? AND kind='real' AND state='reserved' AND id!=?",
                (a["item_id"], a["slot"], a["id"]),
            )
        # Payment only: never turn surplus into a counted scientific read.
        if not paid and 0 <= now - a["created"] <= cfg["LATE_PAYMENT_SECONDS"] and within_budget:
            late_paid = 1
    if (paid or late_paid) and extra_fixed:
        db.execute("UPDATE sessions SET fixed_fee=1 WHERE id=?", (session_id,))
    surplus = int(a["kind"] == "real" and not paid)
    db.execute(
        """INSERT INTO answers(assignment_id,session_id,item_id,kind,slot,label,factor,rationale,seconds,submitted,paid,replacement,surplus,late_paid,
        instrument_version,pipeline_version,path,field_problems,relevance,other_detail,binary_inconsistent,package_sha256,config_sha256)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            assignment_id,
            session_id,
            a["item_id"],
            a["kind"],
            a["slot"],
            label,
            factor,
            rationale.strip(),
            max(0, min(seconds, 86400)),
            now,
            paid,
            replacement if paid else 0,
            surplus,
            late_paid,
            instrument["instrument_version"],
            db.execute("SELECT value FROM metadata WHERE key='pipeline_version'").fetchone()[0],
            json.dumps(instrument["path"], ensure_ascii=False),
            json.dumps(instrument["field_problems"], ensure_ascii=False),
            instrument["relevance"],
            instrument["other_detail"],
            int(instrument["binary_inconsistent"]),
            db.execute("SELECT value FROM metadata WHERE key='pair_sha256'").fetchone()[0],
            db.execute("SELECT value FROM metadata WHERE key='config_sha256'").fetchone()[0],
        ),
    )
    if comment.strip():
        answer_id = db.execute(
            "SELECT id FROM answers WHERE assignment_id=?", (assignment_id,)
        ).fetchone()[0]
        db.execute(
            "INSERT INTO feedback(session_id,screen,item_id,message,created,answer_id) VALUES(?,?,?,?,?,?)",
            (session_id, "work", a["item_id"], comment.strip(), now, answer_id),
        )
    db.execute("UPDATE assignments SET state='answered' WHERE id=?", (assignment_id,))
    db.execute("UPDATE sessions SET last_submission=? WHERE id=?", (now, session_id))
    # One pair at a time: unopened reads still held from a block reserved before the rule
    # go back to the pool; next_pair gives the next one.
    db.execute(
        "UPDATE assignments SET state='released' "
        "WHERE session_id=? AND kind='real' AND state='reserved' AND started IS NULL",
        (session_id,),
    )
    if a["kind"] == "control" and not s["manual_quality_override"]:
        controls = db.execute(
            "SELECT item_id,label FROM answers WHERE session_id=? AND kind='control'", (session_id,)
        ).fetchall()
        if len(controls) >= cfg["CONTROL_MIN_COUNT"]:
            correct = sum(r["label"] == synthetic[r["item_id"]]["answer"] for r in controls)
            if correct / len(controls) < cfg["CONTROL_MIN_ACCURACY"]:
                db.execute("UPDATE sessions SET quality_failed=1 WHERE id=?", (session_id,))
                exclude(
                    db, session_id, "Embedded controls below threshold", now=now, automatic=True
                )
                record_payment_exception(db, cfg, session_id)
    if a["kind"] == "real" and paid:
        reassess_quality(db, cfg, now)
    activate_next(db, session_id, now)
    if closure(db, cfg)[0]:
        for row in db.execute("SELECT id FROM sessions WHERE finished=0").fetchall():
            record_payment_exception(db, cfg, row[0])
    return dict(
        db.execute("SELECT * FROM answers WHERE assignment_id=?", (assignment_id,)).fetchone()
    )


def quality_report(db, cfg, session_id):
    rows = db.execute(
        "SELECT * FROM answers WHERE session_id=? AND kind='real' AND paid=1", (session_id,)
    ).fetchall()
    shared = agreements = 0
    for answer in rows:
        peers = [r for r in votes(db, answer["item_id"]) if r["session_id"] != session_id]
        if peers:
            shared += 1
            agreements += int(any(r["label"] == answer["label"] for r in peers))
    median = statistics.median(r["seconds"] for r in rows) if rows else None
    patterns = []
    if len(rows) >= cfg["PATTERN_MIN_PAIRS"] and len({r["label"] for r in rows}) == 1:
        patterns.append("same_category_every_pair")
    reasons = []
    if shared >= cfg["QUALITY_MIN_SHARED_PAIRS"] and agreements <= cfg["QUALITY_MAX_AGREEMENTS"]:
        reasons.append("low_peer_agreement")
    if len(rows) >= cfg["QUALITY_MIN_SPEED_PAIRS"] and median < cfg["QUALITY_MIN_MEDIAN_SECONDS"]:
        reasons.append("fast_responses")
    s = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    audit = db.execute(
        "SELECT reason FROM audit WHERE session_id=? AND action IN ('exclude','include') ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    return {
        "session_pseudonym": session_id,
        "preview": bool(s["preview"]),
        "real_pairs": len(rows),
        "shared_pairs": shared,
        "agreements": agreements,
        "median_seconds": median,
        "patterns": patterns,
        "flagged": bool(s["quality_failed"]),
        "excluded": bool(s["excluded"]),
        "manual_override": bool(s["manual_quality_override"]),
        "trigger_reasons": reasons,
        "recorded_reason": audit[0] if audit else None,
    }


def reassess_quality(db, cfg, now=None):
    # Evaluate one consistent snapshot first, so arbitrary session iteration
    # order does not determine who is excluded in a mutual disagreement.
    reports = [
        quality_report(db, cfg, r[0])
        for r in db.execute(
            "SELECT id FROM sessions WHERE excluded=0 AND manual_quality_override=0"
        ).fetchall()
    ]
    for report in reports:
        if report["trigger_reasons"]:
            sid = report["session_pseudonym"]
            db.execute("UPDATE sessions SET quality_failed=1 WHERE id=?", (sid,))
            exclude(
                db,
                sid,
                "Live quality: " + ", ".join(report["trigger_reasons"]),
                now=now,
                automatic=True,
            )
            record_payment_exception(db, cfg, sid)


def study_progress(db, cfg):
    participants = db.execute(
        "SELECT COUNT(DISTINCT session_id) FROM answers WHERE kind='real'"
    ).fetchone()[0]
    states = [
        pair_state(db, r[0], cfg)
        for r in db.execute("SELECT id FROM items WHERE retired=0").fetchall()
    ]
    # Valid reads of retired pairs count as already resolved work, in both terms
    # ; the retired pairs themselves are not offered or listed.
    retired = sum(
        len(pair_state(db, r[0], cfg)["votes"])
        for r in db.execute("SELECT id FROM items WHERE retired=1").fetchall()
    )
    valid = sum(len(s["votes"]) for s in states) + retired
    denominator = sum(max(cfg["INITIAL_READS"], s["target"]) for s in states) + retired
    closed = closure(db, cfg)[0]
    percent = min(100, int(100 * valid / denominator)) if denominator else 0
    return {
        "participants": participants,
        "percent": percent,
        "valid_reads": valid,
        "required_reads_so_far": denominator,
        "closed": closed,
        "resolved_pairs": sum(s["status"] == "resolved" for s in states),
        "covered_pairs": sum(len(s["votes"]) >= cfg["INITIAL_READS"] for s in states),
        "total_pairs": len(states),
    }
