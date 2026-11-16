# SPDX-License-Identifier: AGPL-3.0-only
import hashlib
import hmac
import json
import os
import secrets
import time
from functools import wraps
from urllib.parse import urlsplit

import markdown
from flask import (
    Flask,
    abort,
    g,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from itsdangerous import BadSignature, URLSafeTimedSerializer
from markupsafe import Markup
from werkzeug.middleware.proxy_fix import ProxyFix

from . import corrections, engine, i18n, private_export
from .config import ROOT, settings
from .db import connect, initialize, purge_ip_fingerprints, stored_compensation, transaction
from .instrument import instrument_copy, parse_answer
from .presentation import claim_view, feedback_explanation, feedback_view

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
# The one sentence of the guidelines about pay, left out when compensation is disabled.
GUIDELINES_PAY_SENTENCE = {
    "it": " Leggi «Regole e compenso» per la soglia e l’eccezione quando il sito interrompe le assegnazioni.",
    "en": " Read “Rules and pay” for the threshold and the exception when the site stops providing work.",
}


def resolve_compensation(overrides=None):
    """Overrides with COMPENSATION_ENABLED fixed by the study database when it exists.

    A study keeps the compensation it was created with: an existing database decides,
    and an explicit setting that contradicts it stops the start instead of silently
    turning pay on or off. A new database follows the setting (off by default).
    """
    overrides = dict(overrides or {})
    # Only the database path is needed here, so the probe never validates amounts.
    probe = settings({**overrides, "COMPENSATION_ENABLED": False}, validate_budget=False)
    stored = stored_compensation(probe["DATABASE_PATH"])
    if stored is None:
        return overrides
    if "COMPENSATION_ENABLED" in overrides:
        requested = bool(overrides["COMPENSATION_ENABLED"])
    elif "COMPENSATION_ENABLED" in os.environ:
        requested = os.environ["COMPENSATION_ENABLED"].lower() in ("true", "1")
    else:
        requested = stored
    if requested != stored:
        state = "with" if stored else "without"
        raise RuntimeError(
            f"This study database was created {state} compensation; "
            "COMPENSATION_ENABLED cannot change for an existing study"
        )
    overrides["COMPENSATION_ENABLED"] = stored
    return overrides


def create_app(overrides=None):
    app = Flask(__name__)
    app.config.update(settings(resolve_compensation(overrides)))
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    initialize(app.config)
    synthetic = {
        x["id"]: x for x in json.loads((ROOT / "content/synthetic_items.json").read_text())
    }
    copy = json.loads((ROOT / "content/copy.json").read_text())
    signer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="form-v1")

    def digest(value):
        return hmac.new(
            app.config["SECRET_KEY"].encode(), value.encode(), hashlib.sha256
        ).hexdigest()

    def personal_code(nonce):
        value = int(digest("code:" + nonce)[:10], 16)
        raw = "".join(ALPHABET[(value >> (5 * i)) & 31] for i in reversed(range(8)))
        return raw[:4] + "-" + raw[4:]

    def normalized_code(value):
        return (
            value.upper()
            .replace("-", "")
            .replace(" ", "")
            .replace("O", "0")
            .replace("I", "1")
            .replace("L", "1")
        )

    def code_digest(value):
        """Digest of a participation code exactly as /resume looks it up; None if malformed."""
        code = normalized_code(value)
        return digest("code:" + code) if len(code) == 8 else None

    # The operator CLI resolves a code read from stdin to its session (personal-rate) and
    # stores only the session id, never the code.
    app.extensions["participation_code_digest"] = code_digest

    def refresh_session():
        token = request.cookies.get("participant", "")
        g.person = (
            g.db.execute(
                "SELECT * FROM sessions WHERE token_hash=?", (digest("token:" + token),)
            ).fetchone()
            if token
            else None
        )

    @app.before_request
    def prepare():
        # Identity fields and recovery codes are accepted only in POST bodies.
        if any(
            k in request.args
            for k in ("name", "first_name", "last_name", "programme", "year", "code")
        ):
            abort(400)
        g.db = connect(app.config)
        g.lang = request.accept_languages.best_match(["it", "en"], default="en")
        g.closed = False
        g.display_code = None
        g.notice = None
        refresh_session()
        lang = request.args.get("lang") or request.form.get("lang")
        g.lang = (
            lang
            if lang in ("it", "en")
            else request.accept_languages.best_match(["it", "en"], default="en")
        )
        g.closed, g.closure_reason = engine.closure(g.db, app.config)
        g.display_code = None
        g.notice = "feedback_saved" if request.args.get("note") == "feedback_saved" else None

    @app.teardown_request
    def cleanup(error):
        if "db" in g:
            g.db.close()

    @app.after_request
    def headers(response):
        response.headers.update(
            {
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'",
                "X-Robots-Tag": "noindex, nofollow, noarchive, nosnippet, noimageindex, noai, noimageai",
                "tdm-reservation": "1",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "same-origin",
                "Cache-Control": "no-store",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            }
        )
        return response

    def tr(key, **kwargs):
        # Without compensation, texts that mention pay have a variant that does not.
        if not app.config["COMPENSATION_ENABLED"] and f"{key}_nopay" in i18n.UI[g.lang]:
            key = f"{key}_nopay"
        return i18n.translate(g.lang, key, **kwargs)

    def money(cents):
        value = f"{cents / 100:.2f}"
        return "€" + (value.replace(".", ",") if g.lang == "it" else value)

    def link(endpoint, **kwargs):
        return url_for(endpoint, lang=g.lang, **kwargs)

    def form_token(endpoint, **extras):
        return signer.dumps(
            {
                "nonce": secrets.token_hex(16),
                "endpoint": endpoint,
                "sid": g.person["id"]
                if g.person and endpoint not in ("start", "resume", "feedback_submit")
                else "",
                "issued": time.time(),
                **extras,
            }
        )

    def confirmed_draft():
        saved = request.args.get("saved", "")
        if not saved or not g.person:
            return ""
        answered = g.db.execute(
            "SELECT 1 FROM answers WHERE assignment_id=? AND session_id=?", (saved, g.person["id"])
        ).fetchone()
        qualified = g.db.execute(
            "SELECT 1 FROM qualification WHERE item_id=? AND session_id=?", (saved, g.person["id"])
        ).fetchone()
        return saved if answered or qualified else ""

    def confirmed_feedback():
        saved = request.args.get("feedback_saved", "")
        if not saved:
            return ""
        try:
            data = signer.loads(saved, max_age=43200)
        except BadSignature:
            return ""
        if data.get("sid") != (g.person["id"] if g.person else ""):
            return ""
        row = g.db.execute(
            "SELECT 1 FROM feedback WHERE id=?", (data.get("feedback_id"),)
        ).fetchone()
        return data.get("draft_key", "") if row else ""

    @app.context_processor
    def context():
        earn = engine.earnings(g.db, app.config, g.person["id"]) if g.person else None
        if earn and app.config["PREVIEW_MODE"]:
            earn = {**earn, "cents": 0, "payable_cents": 0, "fixed": False}
        return {
            "study": engine.study_progress(g.db, app.config),
            "pay": engine.pay_view(g.db, app.config, g.person["id"] if g.person else None),
            "programmes": engine.programmes(g.db, app.config),
            "t": tr,
            "money": money,
            "link": link,
            "token": form_token,
            "lang": g.lang,
            "person": g.person,
            "closed": g.closed,
            "earn": earn,
            "cfg": app.config,
            "labels": dict(zip(engine.LABELS, i18n.LABELS[g.lang], strict=True)),
            "factors": dict(zip(engine.FACTORS, i18n.FACTORS[g.lang], strict=True)),
            "instrument_copy": instrument_copy,
            "claim_view": claim_view,
            "feedback_view": feedback_view,
            "feedback_explanation": feedback_explanation,
            "saved_draft": confirmed_draft(),
            "saved_feedback": confirmed_feedback(),
            "site_stop": engine.site_stop_reason(g.db, app.config, g.person["id"])
            if g.person
            else "",
            "identity": g.db.execute(
                "SELECT * FROM identities WHERE session_id=?", (g.person["id"],)
            ).fetchone()
            if g.person
            else None,
            "copy": copy[g.lang],
            # Shows the way to the list of submitted pairs only to people who have one.
            "submitted_count": corrections.submitted_count(g.db, g.person["id"]) if g.person else 0,
            "display_code": g.display_code,
            "notice": g.notice,
        }

    def cookie(response, raw):
        response.set_cookie(
            "participant",
            raw,
            max_age=86400 * 60,
            secure=app.config["COOKIE_SECURE"],
            httponly=True,
            samesite="Lax",
        )
        return response

    def post(endpoint, public=False):
        def decorator(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                origin = request.headers.get("Origin")
                if not origin:
                    ref = urlsplit(request.headers.get("Referer", ""))
                    origin = f"{ref.scheme}://{ref.netloc}"
                base = urlsplit(app.config["BASE_URL"])
                expected_origin = f"{base.scheme}://{base.netloc}"
                same_origin_metadata = (
                    origin in (None, "null", "://")
                    and request.headers.get("Sec-Fetch-Site") == "same-origin"
                    and request.host_url.rstrip("/") == expected_origin
                )
                if origin != expected_origin and not same_origin_metadata:
                    abort(403)
                try:
                    data = signer.loads(request.form.get("_form", ""), max_age=43200)
                except BadSignature:
                    abort(400)
                sid = g.person["id"] if g.person and not public else ""
                if data.get("endpoint") != endpoint or data.get("sid") != sid:
                    abort(403)
                if not public and not g.person:
                    abort(403)
                with transaction(g.db):
                    purge_ip_fingerprints(g.db)
                    previous = g.db.execute(
                        "SELECT * FROM actions WHERE id=?", (data["nonce"],)
                    ).fetchone()
                    if previous:
                        if endpoint in ("start", "resume"):
                            raw = digest("cookie:" + data["nonce"])
                            existing = g.db.execute(
                                "SELECT * FROM sessions WHERE id=?", (previous["session_id"],)
                            ).fetchone()
                            if existing and existing["token_hash"] == digest("token:" + raw):
                                g.person = existing
                                return cookie(make_response(redirect(link("work"), code=303)), raw)
                        if endpoint in ("answer", "qualification_answer"):
                            return redirect(
                                link("work", saved=data.get("assignment") or data.get("item")),
                                code=303,
                            )
                        if endpoint == "correction":
                            return redirect(link("submitted"), code=303)
                        return redirect(link("work" if g.person else "index"), code=303)
                    result = fn(data, *args, **kwargs)
                    g.db.execute(
                        "INSERT INTO actions(id,session_id,endpoint,created) VALUES(?,?,?,?)",
                        (
                            data["nonce"],
                            g.person["id"] if g.person else None,
                            endpoint,
                            time.time(),
                        ),
                    )
                return result

            return wrapped

        return decorator

    def enter_work():
        if engine.reserve(g.db, app.config, g.person["id"], admission=True):
            g.person = g.db.execute(
                "SELECT * FROM sessions WHERE id=?", (g.person["id"],)
            ).fetchone()
            return True
        g.db.execute("UPDATE sessions SET stage='ready' WHERE id=?", (g.person["id"],))
        return False

    def next_stage():
        if app.config["QUALIFICATION_ENABLED"]:
            g.db.execute("UPDATE sessions SET stage='qualification' WHERE id=?", (g.person["id"],))
        else:
            enter_work()

    @app.get("/")
    def index():
        # People with a session can read the home page; it offers the way back to work.
        return render_template("landing.html")

    @app.post("/start")
    @post("start", public=True)
    def start(data):
        if g.closed:
            return render_template("message.html", title="closed", description="closed_help")
        raw = digest("cookie:" + data["nonce"])
        code = personal_code(data["nonce"])
        sid = engine.uid()
        now = time.time()
        g.db.execute(
            "INSERT INTO sessions(id,token_hash,code_hash,code_hint,created,last_submission) VALUES(?,?,?,?,?,?)",
            (
                sid,
                digest("token:" + raw),
                digest("code:" + normalized_code(code)),
                code[-4:],
                now,
                now,
            ),
        )
        g.person = g.db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if app.config["TUTORIAL_ENABLED"]:
            g.db.execute("UPDATE sessions SET stage='tutorial' WHERE id=?", (sid,))
        else:
            next_stage()
        g.person = g.db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        g.display_code = code
        return cookie(make_response(show_work()), raw)

    @app.post("/resume")
    @post("resume", public=True)
    def resume(data):
        bucket = digest("rate:" + str(request.remote_addr))
        now = time.time()
        g.db.execute("DELETE FROM rate_limits WHERE until<?", (now,))
        rate = g.db.execute("SELECT * FROM rate_limits WHERE bucket=?", (bucket,)).fetchone()
        if rate and rate["count"] >= 10:
            return render_template("message.html", title="error", description="rate_limit"), 429
        g.db.execute(
            "INSERT INTO rate_limits(bucket,count,until) VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1",
            (bucket, now + 900),
        )
        code = normalized_code(request.form.get("code", ""))
        person = (
            g.db.execute(
                "SELECT * FROM sessions WHERE code_hash=?", (digest("code:" + code),)
            ).fetchone()
            if len(code) == 8
            else None
        )
        if not person:
            return render_template("landing.html", error="bad_code"), 400
        raw = digest("cookie:" + data["nonce"])
        g.db.execute(
            "UPDATE sessions SET token_hash=? WHERE id=?", (digest("token:" + raw), person["id"])
        )
        g.person = g.db.execute("SELECT * FROM sessions WHERE id=?", (person["id"],)).fetchone()
        g.display_code = code[:4] + "-" + code[4:]
        return cookie(make_response(show_work()), raw)

    @app.post("/code")
    @post("code")
    def code(data):
        value = personal_code(data["nonce"])
        g.db.execute(
            "UPDATE sessions SET code_hash=?,code_hint=? WHERE id=?",
            (digest("code:" + normalized_code(value)), value[-4:], g.person["id"]),
        )
        g.person = g.db.execute("SELECT * FROM sessions WHERE id=?", (g.person["id"],)).fetchone()
        g.display_code = value
        return show_work()

    @app.post("/tutorial")
    @post("tutorial_done")
    def tutorial_done(data):
        if g.person["stage"] == "tutorial":
            next_stage()
        return redirect(link("work"), code=303)

    @app.post("/admit")
    @post("admit")
    def admit(data):
        if g.person["stage"] == "ready" and not g.person["finished"]:
            enter_work()
        return redirect(link("work"), code=303)

    @app.post("/more")
    @post("more")
    def more(data):
        if g.person["stage"] == "work" and not engine.reserve(g.db, app.config, g.person["id"]):
            g.notice = "full_help"
        return redirect(link("work", note="unavailable" if g.notice else "saved"), code=303)

    def qualification_items():
        return sorted(
            [x for x in synthetic.values() if x["group"] == f"qualification{g.person['attempt']}"],
            key=lambda x: x["id"],
        )

    @app.post("/qualification")
    @post("qualification_answer")
    def qualification_answer(data):
        if g.person["stage"] != "qualification":
            return redirect(link("work", saved=data.get("item")), code=303)
        items = qualification_items()
        if g.db.execute(
            "SELECT 1 FROM qualification WHERE session_id=? AND attempt=? AND item_id=?",
            (g.person["id"], g.person["attempt"], data.get("item")),
        ).fetchone():
            return redirect(link("work", saved=data.get("item")), code=303)
        rows = g.db.execute(
            "SELECT * FROM qualification WHERE session_id=? AND attempt=?",
            (g.person["id"], g.person["attempt"]),
        ).fetchall()
        if len(rows) >= len(items) or data.get("item") != items[len(rows)]["id"]:
            abort(409)
        values = answer_values()
        label = values["label"]
        item = items[len(rows)]
        g.db.execute(
            "INSERT INTO qualification(session_id,attempt,item_id,label,correct,submitted,path) VALUES(?,?,?,?,?,?,?)",
            (
                g.person["id"],
                g.person["attempt"],
                item["id"],
                label,
                int(label == item["answer"]),
                time.time(),
                json.dumps(values["path"], ensure_ascii=False),
            ),
        )
        comment = preview_comment()
        if comment:
            g.db.execute(
                "INSERT INTO feedback(session_id,screen,item_id,message,created) VALUES(?,?,?,?,?)",
                (g.person["id"], "qualification", item["id"], comment, time.time()),
            )
        g.db.execute(
            "UPDATE sessions SET last_submission=? WHERE id=?", (time.time(), g.person["id"])
        )
        if len(rows) + 1 == len(items):
            g.db.execute(
                "UPDATE sessions SET stage='qualification_feedback' WHERE id=?", (g.person["id"],)
            )
        return redirect(link("work", saved=data.get("item")), code=303)

    @app.post("/qualification-next")
    @post("qualification_next")
    def qualification_next(data):
        if g.person["stage"] != "qualification_feedback":
            return redirect(link("work"), code=303)
        correct = g.db.execute(
            "SELECT SUM(correct) FROM qualification WHERE session_id=? AND attempt=?",
            (g.person["id"], g.person["attempt"]),
        ).fetchone()[0]
        if correct >= app.config["QUALIFICATION_PASS"]:
            enter_work()
        elif g.person["attempt"] < app.config["QUALIFICATION_ATTEMPTS"]:
            g.db.execute(
                "UPDATE sessions SET attempt=attempt+1,stage='qualification' WHERE id=?",
                (g.person["id"],),
            )
        else:
            g.db.execute("UPDATE sessions SET stage='failed' WHERE id=?", (g.person["id"],))
        return redirect(link("work"), code=303)

    def answer_values():
        try:
            return parse_answer(request.form)
        except (ValueError, TypeError, KeyError, RecursionError):
            abort(400)

    def preview_comment():
        comment = request.form.get("comment", "").strip()
        if len(comment) > 2000 or (comment and not app.config["PREVIEW_MODE"]):
            abort(400)
        return comment

    @app.post("/answer")
    @post("answer")
    def answer(data):
        if g.db.execute(
            "SELECT 1 FROM answers WHERE assignment_id=? AND session_id=?",
            (data.get("assignment"), g.person["id"]),
        ).fetchone():
            return redirect(link("work", saved=data.get("assignment")), code=303)
        values = answer_values()
        try:
            result = engine.submit(
                g.db,
                app.config,
                g.person["id"],
                data.get("assignment"),
                values["label"],
                values["factor"],
                values["rationale"],
                time.time() - data["issued"],
                synthetic,
                instrument=values,
                comment=preview_comment(),
            )
        except ValueError:
            abort(400)
        if result["kind"] == "practice":
            g.db.execute(
                "UPDATE sessions SET stage='practice_feedback' WHERE id=?", (g.person["id"],)
            )
        elif g.person["stage"] == "work":
            # One pair at a time: the next pair now, unless this answer ends a group.
            engine.next_pair(g.db, app.config, g.person["id"])
        return redirect(
            link(
                "work",
                note="surplus" if result["surplus"] and not result["late_paid"] else "saved",
                saved=data["assignment"],
            ),
            code=303,
        )

    @app.post("/practice-begin")
    @post("practice_begin")
    def practice_begin(data):
        assigned = g.db.execute(
            "SELECT id FROM assignments WHERE id=? AND session_id=? AND kind='practice' AND state='reserved'",
            (data.get("assignment"), g.person["id"]),
        ).fetchone()
        if not assigned or g.person["finished"]:
            abort(409)
        # Existing idempotent action log records this presentation acknowledgement.
        # No answer, allocation, payment or instrument state is changed.
        return redirect(link("work"), code=303)

    @app.post("/practice-next")
    @post("practice_next")
    def practice_next(data):
        if g.person["stage"] == "practice_feedback":
            g.db.execute("UPDATE sessions SET stage='work' WHERE id=?", (g.person["id"],))
            # Real pairs are reserved only now, after the practice answer. Sessions that
            # started before this rule already hold theirs; reserve() leaves them as they are.
            if (
                not engine.reserve(g.db, app.config, g.person["id"], first_real=True)
                and not g.db.execute(
                    "SELECT 1 FROM assignments WHERE session_id=? AND state='reserved'",
                    (g.person["id"],),
                ).fetchone()
            ):
                return redirect(link("work", note="unavailable"), code=303)
        return redirect(link("work"), code=303)

    @app.get("/finish")
    def finish_form():
        if not g.person:
            return redirect(link("index"))
        return render_template("finish.html")

    @app.post("/finish")
    @post("finish")
    def finish(data):
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        programme = request.form.get("programme", "").strip()
        other_programme = (
            request.form.get("other_programme", "").strip() if programme == "other" else ""
        )
        year = request.form.get("year", "").strip()
        review = programme == "other"
        previous_identity = g.db.execute(
            "SELECT programme,other_programme,needs_review FROM identities WHERE session_id=?",
            (g.person["id"],),
        ).fetchone()
        if (
            review
            and previous_identity
            and previous_identity["programme"] == "other"
            and previous_identity["other_programme"] == other_programme
        ):
            review = bool(previous_identity["needs_review"])
        if (programme != "other" and programme not in engine.programmes(g.db, app.config)) or (
            programme == "other" and not other_programme
        ):
            abort(400)
        if request.form.get("eligibility") != "yes":
            abort(400)
        paid = app.config["COMPENSATION_ENABLED"]
        if not paid:
            # Names are asked only to arrange payment; without compensation none is kept.
            first_name = last_name = ""
        required = (first_name, last_name, programme, year) if paid else (programme, year)
        if not all(1 <= len(v) <= 200 for v in required) or len(other_programme) > 200:
            abort(400)
        if paid:
            earned = engine.earnings(g.db, app.config, g.person["id"])
            reason = engine.site_stop_reason(g.db, app.config, g.person["id"])
            if (
                earned["count"] < app.config["MIN_PAYOUT_PAIRS"]
                and not reason
                and request.form.get("confirm_below") != "yes"
            ):
                return render_template("finish.html", confirmation_required=True), 400
            engine.record_payment_exception(g.db, app.config, g.person["id"])
        g.db.execute(
            """INSERT INTO identities(session_id,first_name,last_name,programme,other_programme,year,needs_review,eligibility_declared,updated)
            VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET
            first_name=excluded.first_name,last_name=excluded.last_name,programme=excluded.programme,
            other_programme=excluded.other_programme,year=excluded.year,
            needs_review=excluded.needs_review,eligibility_declared=excluded.eligibility_declared,updated=excluded.updated""",
            (
                g.person["id"],
                first_name,
                last_name,
                programme,
                other_programme,
                year,
                int(review),
                1,
                time.time(),
            ),
        )
        if review:
            g.db.execute(
                "INSERT INTO audit(session_id,action,reason,created) VALUES(?,?,?,?)",
                (
                    g.person["id"],
                    "eligibility-review",
                    "Other programme; answers withheld and payment blocked pending eligibility review"
                    if paid
                    else "Other programme; answers withheld pending eligibility review",
                    time.time(),
                ),
            )
        g.db.execute("UPDATE sessions SET finished=1 WHERE id=?", (g.person["id"],))
        g.db.execute(
            "UPDATE assignments SET state='released' WHERE session_id=? AND state='reserved'",
            (g.person["id"],),
        )
        return redirect(link("work"), code=303)

    @app.post("/resume-work")
    @post("resume_work")
    def resume_work(data):
        identity = g.db.execute(
            "SELECT needs_review FROM identities WHERE session_id=?", (g.person["id"],)
        ).fetchone()
        if (
            g.closed
            or g.person["excluded"]
            or g.person["quality_failed"]
            or (identity and identity["needs_review"])
        ):
            return redirect(link("work"), code=303)
        if g.person["finished"]:
            g.db.execute("UPDATE sessions SET finished=0 WHERE id=?", (g.person["id"],))
            if g.person["stage"] == "work":
                engine.reserve(g.db, app.config, g.person["id"])
        return redirect(link("work"), code=303)

    def show_work():
        if g.person["finished"]:
            return render_template("final.html")
        if g.closed:
            return render_template("message.html", title="closed", description="closed_help")
        if g.person["excluded"] or g.person["quality_failed"]:
            return render_template("message.html", title="quality_stop", description="quality_help")
        stage = g.person["stage"]
        if stage == "tutorial":
            return render_template("tutorial.html")
        if stage == "qualification":
            rows = g.db.execute(
                "SELECT COUNT(*) FROM qualification WHERE session_id=? AND attempt=?",
                (g.person["id"], g.person["attempt"]),
            ).fetchone()[0]
            return render_template(
                "pair.html",
                item=qualification_items()[rows],
                assignment=None,
                qualification=True,
                question_number=rows + 1,
            )
        if stage == "qualification_feedback":
            rows = g.db.execute(
                "SELECT * FROM qualification WHERE session_id=? AND attempt=? ORDER BY item_id",
                (g.person["id"], g.person["attempt"]),
            ).fetchall()
            return render_template(
                "feedback.html",
                results=rows,
                synthetic=synthetic,
                qualification=True,
                passed=sum(r["correct"] for r in rows) >= app.config["QUALIFICATION_PASS"],
            )
        if stage == "practice_feedback":
            row = g.db.execute(
                "SELECT * FROM answers WHERE session_id=? AND kind='practice' ORDER BY id DESC LIMIT 1",
                (g.person["id"],),
            ).fetchone()
            return render_template(
                "feedback.html", results=[row], synthetic=synthetic, qualification=False
            )
        if stage == "failed":
            return render_template("message.html", title="quality_stop", description="failed")
        if stage == "ready":
            return render_template(
                "message.html", title="full", description="full_help", action="admit"
            )
        assignment = g.db.execute(
            "SELECT * FROM assignments WHERE session_id=? AND state='reserved' ORDER BY position LIMIT 1",
            (g.person["id"],),
        ).fetchone()
        if not assignment:
            if engine.checkpoint_due(g.db, app.config, g.person["id"]):
                return render_template(
                    "message.html", title="batch_done", description="batch_help", action="more"
                )
            # Between pairs: no free pair at the last answer, or the open pair was given to
            # someone else after 30 minutes without activity.
            return render_template(
                "message.html", title="next_pair", description="next_pair_help", action="more"
            )
        if (
            assignment["kind"] == "practice"
            and not g.db.execute(
                "SELECT 1 FROM actions WHERE session_id=? AND endpoint='practice_begin'",
                (g.person["id"],),
            ).fetchone()
        ):
            return render_template("practice_intro.html", assignment=assignment)
        item = (
            json.loads(
                g.db.execute(
                    "SELECT data FROM items WHERE id=?", (assignment["item_id"],)
                ).fetchone()[0]
            )
            if assignment["kind"] == "real"
            else synthetic[assignment["item_id"]]
        )
        # Pairs are numbered by the answers given so far, so pairs released from an older
        # block leave no gap in the count.
        pair_number = (
            g.db.execute(
                "SELECT COUNT(*) FROM answers WHERE session_id=?", (g.person["id"],)
            ).fetchone()[0]
            + 1
        )
        return render_template(
            "pair.html",
            item=item,
            assignment=assignment,
            qualification=False,
            pair_number=pair_number,
        )

    @app.get("/work")
    def work():
        if not g.person:
            return redirect(link("index"))
        if request.args.get("note") in ("surplus", "saved", "unavailable"):
            g.notice = {"surplus": "surplus", "saved": "saved", "unavailable": "full_help"}[
                request.args["note"]
            ]
        return show_work()

    # Self-service corrections: the real pairs this session
    # submitted, each reopened on the same pair screen with the same question flow and
    # the presentation in force today. They work in every session state, also after
    # finishing. Saves are accepted while the collection is open; once it is closed the
    # list stays readable and nothing more is recorded, so the closure export is final.

    def show_submitted(note=None, number=None, status=200):
        pairs = corrections.listing(g.db, g.person["id"], g.lang)
        if number is not None and not 1 <= number <= len(pairs):
            number = None
        return render_template(
            "submitted.html", pairs=pairs, correction_note=note, correction_pair=number
        ), status

    @app.get("/submitted")
    def submitted():
        if not g.person:
            return redirect(link("index"))
        note = request.args.get("note")
        return show_submitted(
            note if note in ("corrected", "unchanged") else None,
            request.args.get("pair", type=int),
        )

    @app.get("/submitted/<assignment>")
    def correction_form(assignment):
        if not g.person:
            return redirect(link("index"))
        if g.closed:
            return redirect(link("submitted"))
        number, answer = corrections.find(g.db, g.person["id"], assignment)
        if answer is None:
            abort(404)
        current = private_export.answer_in_force(g.db, answer)
        return render_template(
            "pair.html",
            item=json.loads(answer["item_data"]),
            assignment=g.db.execute(
                "SELECT * FROM assignments WHERE id=?", (answer["assignment_id"],)
            ).fetchone(),
            qualification=False,
            correction={
                "number": number,
                "submitted": corrections.when(answer["submitted"], g.lang),
                "corrected": corrections.when(current["corrected_at"], g.lang)
                if current["corrected_at"] is not None
                else None,
                # Restored by the page script like a draft: the latest version, never a draft.
                "prefill": {
                    "version": "2.0",
                    "values": corrections.form_values(current["path"], current["rationale"]),
                },
            },
        )

    @app.post("/correction")
    @post("correction")
    def correction(data):
        if g.closed:
            return redirect(link("submitted"), code=303)
        number, answer = corrections.find(g.db, g.person["id"], data.get("assignment"))
        if answer is None:
            abort(404)
        bucket = digest("correction:" + g.person["id"])
        now = time.time()
        rate = g.db.execute(
            "SELECT count FROM rate_limits WHERE bucket=? AND until>?", (bucket, now)
        ).fetchone()
        if rate and rate["count"] >= corrections.RATE_LIMIT:
            return show_submitted("rate_limit", status=429)
        # The same parsing and validation as a normal answer.
        values = answer_values()
        g.db.execute(
            "INSERT INTO rate_limits(bucket,count,until) VALUES(?,1,?) "
            "ON CONFLICT(bucket) DO UPDATE SET count=count+1",
            (bucket, now + corrections.RATE_WINDOW_SECONDS),
        )
        written = private_export.write_correction(
            g.db,
            app.config,
            answer,
            values["path"],
            rationale=values["rationale"],
            source=private_export.SELF_SERVICE_SOURCE,
            disclosure=private_export.self_service_disclosure(app.config),
            recorded_by=private_export.SELF_SERVICE_RECORDED_BY,
            now=now,
        )
        return redirect(
            link("submitted", note="corrected" if written else "unchanged", pair=number),
            code=303,
        )

    @app.post("/feedback")
    @post("feedback_submit", public=True)
    def feedback_submit(data):
        if not app.config["PREVIEW_MODE"]:
            abort(404)
        message = request.form.get("message", "").strip()
        if not 1 <= len(message) <= 2000:
            abort(400)
        item_id = None
        if g.person and data.get("assignment"):
            assigned = g.db.execute(
                "SELECT item_id FROM assignments WHERE id=? AND session_id=?",
                (data["assignment"], g.person["id"]),
            ).fetchone()
            item_id = assigned[0] if assigned else None
        inserted = g.db.execute(
            "INSERT INTO feedback(session_id,screen,item_id,message,created) VALUES(?,?,?,?,?)",
            (
                g.person["id"] if g.person else None,
                data.get("screen", "unknown"),
                item_id,
                message,
                time.time(),
            ),
        )
        destination = data.get("return_to")
        if destination not in ("index", "work", "rules", "privacy", "guidelines", "finish_form"):
            destination = "work" if g.person else "index"
        saved = signer.dumps(
            {
                "sid": g.person["id"] if g.person else "",
                "feedback_id": inserted.lastrowid,
                "draft_key": data.get("draft_key", data.get("screen", "")),
            }
        )
        return redirect(link(destination, note="feedback_saved", feedback_saved=saved), code=303)

    @app.get("/rules")
    def rules():
        return render_template("document.html", page="rules")

    @app.get("/privacy")
    def privacy():
        unpaid = ROOT / f"content/privacy_{g.lang}.nopay.md"
        paid = ROOT / f"content/privacy_{g.lang}.md"
        text = (
            paid if app.config["COMPENSATION_ENABLED"] or not unpaid.exists() else unpaid
        ).read_text()
        return render_template(
            "document.html",
            page="privacy",
            document=Markup(markdown.markdown(text, extensions=["tables"])),
        )

    @app.get("/guidelines")
    def guidelines():
        text = (ROOT / f"content/guidelines_{g.lang}.md").read_text()
        if not app.config["COMPENSATION_ENABLED"]:
            text = text.replace(GUIDELINES_PAY_SENTENCE[g.lang], "")
        return render_template(
            "document.html",
            page="guidelines",
            document=Markup(markdown.markdown(text, extensions=["tables"])),
        )

    @app.get("/healthz")
    def health():
        g.db.execute("SELECT 1").fetchone()
        return {"status": "ok"}

    @app.get("/favicon.ico")
    @app.get("/apple-touch-icon.png")
    def root_icon():
        # Browsers and link previews ask for these at the site root.
        name = request.path.lstrip("/")
        return send_from_directory(app.static_folder, name, max_age=86400)

    @app.get("/robots.txt")
    def robots():
        agents = (
            "*",
            "GPTBot",
            "OAI-SearchBot",
            "ChatGPT-User",
            "ClaudeBot",
            "Claude-SearchBot",
            "Claude-User",
            "Google-Extended",
            "CCBot",
            "PerplexityBot",
            "Perplexity-User",
            "Bytespider",
            "Amazonbot",
            "meta-externalagent",
            "meta-externalfetcher",
            "Applebot-Extended",
        )
        text = "Content-Signal: search=no, ai-input=no, ai-train=no\n\n"
        text += "\n".join(f"User-agent: {agent}\nDisallow: /\n" for agent in agents)
        return text, 200, {"Content-Type": "text/plain; charset=utf-8"}

    @app.get("/.well-known/tdmrep.json")
    def tdm_reservation():
        return [{"location": "/", "tdm-reservation": 1}]

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(413)
    def error(e):
        if not hasattr(g, "db"):
            g.db = connect(app.config)
            g.person = None
            g.lang = "en"
            g.closed = False
            g.display_code = None
            g.notice = None
        return render_template(
            "message.html",
            title="error",
            description="too_large" if e.code == 413 else "error_help",
        ), e.code

    from .cli import register

    register(app)
    return app
