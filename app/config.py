# SPDX-License-Identifier: AGPL-3.0-only
import json
import os
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def settings(overrides=None, *, validate_budget=True):
    cfg = {
        "DATABASE_PATH": os.getenv("DATABASE_PATH", str(ROOT / ".local/app.sqlite3")),
        "SECRET_KEY": os.getenv("SECRET_KEY"),
        "BASE_URL": os.getenv("BASE_URL", "http://localhost:8000"),
        "PAIR_FILE": None,
        # Per-instance switch. Off by default: no money is shown, asked for or computed.
        # A database created with compensation keeps it (see db.stored_compensation).
        "COMPENSATION_ENABLED": False,
        "CONTACT_EMAIL": "",
        # AGPL-3.0 section 13: every page footer links to the source of the program.
        # A modified version must point this at its own source.
        "SOURCE_URL": "https://github.com/napanto/evidiff",
        "AUTHOR_BIO_IT": "Lo studio è condotto da uno studente dell’Università di Pisa, nell’ambito di un progetto sulla lettura automatica della letteratura sulle malattie metaboliche.",
        "AUTHOR_BIO_EN": "This study is run by a student at the University of Pisa, as part of a project on the automated reading of the literature on metabolic diseases.",
        "TESTING": False,
        "INSTRUMENT_VERSION": "2.0",
        "PIPELINE_VERSION": "2.0",
        "COOKIE_SECURE": True,
        "MAX_CONTENT_LENGTH": 16 * 1024,
        "PREVIEW_MODE": False,
        "TUTORIAL_ENABLED": False,
        "QUALIFICATION_ENABLED": False,
        "PRACTICE_ENABLED": True,
        "HIDDEN_CONTROLS_ENABLED": False,
        "SHOW_TECHNICAL_DETAILS": False,
        "ADMISSION_MIN_READS": 5,
        "INITIAL_REAL_BATCH": 4,
        "CONTINUE_BATCH": 5,
        "INITIAL_READS": 2,
        "THIRD_READS": 3,
        "FOURTH_READS": 4,
        "MAX_FOURTH_PAIRS": 8,
        "REPLACEMENT_READS": 16,
        "PAID_READ_CAP": 144,
        "MAX_SYNTHETIC_SCREENS": 60,
        "STALE_MINUTES": 30,
        "LATE_PAYMENT_SECONDS": 7200,
        "FIXED_FEE_EUR": "0.00",
        "FIXED_FEE_MIN_PAIRS": 10,
        "PRICE_PER_PAIR_EUR": "0.00",
        "MIN_PAYOUT_PAIRS": 5,
        "BUDGET_CAP_EUR": "0.00",
        "TARGET_HOURLY_EUR": "0.00",
        "QUALIFICATION_SIZE": 6,
        "QUALIFICATION_PASS": 4,
        "QUALIFICATION_ATTEMPTS": 2,
        "CONTROL_FIRST_POSITION": 3,
        "CONTROL_INTERVAL": 8,
        "CONTROL_MIN_COUNT": 2,
        "CONTROL_MIN_ACCURACY": "0.5",
        "QUALITY_MIN_SHARED_PAIRS": 6,
        "QUALITY_MAX_AGREEMENTS": 1,
        "QUALITY_MIN_SPEED_PAIRS": 5,
        "QUALITY_MIN_MEDIAN_SECONDS": 30,
        "PATTERN_MIN_PAIRS": 5,
        "EXPECTED_DISAGREEMENT_RATE": "0.3",
        "EXPECTED_THREE_WAY_RATE": "0.15",
        "EXPECTED_REPLACEMENT_READS": 4,
        "EXPECTED_PAIRS_PER_SESSION": 10,
        "SOCIAL_PROOF_COPY": {
            "it": {
                "early": "Sii tra i primi a partecipare",
                "progress": "Avanzamento delle letture: {percent}% · {participants} partecipanti",
            },
            "en": {
                "early": "Be one of the first participants",
                "progress": "{percent}% of required reads complete · {participants} participants",
            },
        },
        "ELIGIBLE_PROGRAMMES": {
            "medicine": {"it": "Medicina e Chirurgia", "en": "Medicine and Surgery"},
            "biotech": {"it": "Biotecnologie", "en": "Biotechnology"},
            "biotech_molecular": {
                "it": "Biotecnologie molecolari",
                "en": "Molecular Biotechnology",
            },
            "biotech_ai": {
                "it": "Biotechnologies and Applied Artificial Intelligence for Health",
                "en": "Biotechnologies and Applied Artificial Intelligence for Health",
            },
            "pharmacy": {"it": "Farmacia", "en": "Pharmacy"},
            "ctf": {
                "it": "Chimica e Tecnologia Farmaceutiche",
                "en": "Pharmaceutical Chemistry and Technology",
            },
        },
    }
    for key, default in tuple(cfg.items()):
        if key not in os.environ:
            continue
        raw = os.environ[key]
        if isinstance(default, bool):
            if raw.lower() not in ("true", "false", "1", "0"):
                raise ValueError(f"{key} must be true or false")
            cfg[key] = raw.lower() in ("true", "1")
        elif isinstance(default, int):
            cfg[key] = int(raw)
        elif isinstance(default, (dict, list)):
            cfg[key] = json.loads(raw)
        else:
            cfg[key] = raw
    cfg.update(overrides or {})
    if not cfg["PAIR_FILE"] and cfg["PREVIEW_MODE"]:
        # Only preview mode has a bundled package; a study must supply PAIR_FILE.
        cfg["PAIR_FILE"] = str(ROOT / "content" / "preview_pairs.jsonl")
    if not cfg["SECRET_KEY"]:
        raise RuntimeError("SECRET_KEY must be supplied through the environment")
    if cfg["COMPENSATION_ENABLED"] not in (True, False, 0, 1):
        raise ValueError("COMPENSATION_ENABLED must be true or false")
    cfg["COMPENSATION_ENABLED"] = bool(cfg["COMPENSATION_ENABLED"])
    for key in ("FIXED_FEE_EUR", "PRICE_PER_PAIR_EUR", "BUDGET_CAP_EUR", "TARGET_HOURLY_EUR"):
        if not cfg["COMPENSATION_ENABLED"]:
            # Without compensation the amounts are not read or validated: every price is zero.
            cfg[key.replace("_EUR", "_CENTS")] = 0
            continue
        value = Decimal(str(cfg[key])) * 100
        if not value.is_finite() or value < 0 or value != value.to_integral_value():
            raise ValueError(f"{key} must be a nonnegative amount in whole cents")
        cfg[key.replace("_EUR", "_CENTS")] = int(value)
    if cfg["COMPENSATION_ENABLED"] and cfg["TARGET_HOURLY_CENTS"] <= 0:
        raise ValueError("TARGET_HOURLY_EUR must be positive")
    if cfg["INSTRUMENT_VERSION"] != "2.0" or cfg["PIPELINE_VERSION"] != "2.0":
        raise ValueError("This release requires instrument and pipeline version 2.0")
    positive = (
        "CONTINUE_BATCH",
        "FIXED_FEE_MIN_PAIRS",
        "MIN_PAYOUT_PAIRS",
        "STALE_MINUTES",
        "LATE_PAYMENT_SECONDS",
        "CONTROL_INTERVAL",
        "CONTROL_MIN_COUNT",
        "PAID_READ_CAP",
        "QUALITY_MIN_SHARED_PAIRS",
        "QUALITY_MIN_SPEED_PAIRS",
        "PATTERN_MIN_PAIRS",
        "EXPECTED_PAIRS_PER_SESSION",
    )
    for flag in (
        "PREVIEW_MODE",
        "TUTORIAL_ENABLED",
        "QUALIFICATION_ENABLED",
        "PRACTICE_ENABLED",
        "HIDDEN_CONTROLS_ENABLED",
        "SHOW_TECHNICAL_DETAILS",
    ):
        if cfg[flag] not in (True, False, 0, 1):
            raise ValueError(f"{flag} must be true or false")
        cfg[flag] = bool(cfg[flag])
    for rate in ("EXPECTED_DISAGREEMENT_RATE", "EXPECTED_THREE_WAY_RATE"):
        cfg[rate] = float(cfg[rate])
        if not 0 <= cfg[rate] <= 1:
            raise ValueError(f"{rate} must be between zero and one")
    if any(not isinstance(cfg[k], int) or cfg[k] < 1 for k in positive):
        raise ValueError("Counts and thresholds must be positive")
    if any(
        cfg[k] < 0
        for k in (
            "MAX_FOURTH_PAIRS",
            "REPLACEMENT_READS",
            "MAX_SYNTHETIC_SCREENS",
            "QUALITY_MAX_AGREEMENTS",
            "QUALITY_MIN_MEDIAN_SECONDS",
            "EXPECTED_REPLACEMENT_READS",
        )
    ):
        raise ValueError("Caps cannot be negative")
    if (cfg["INITIAL_READS"], cfg["THIRD_READS"], cfg["FOURTH_READS"]) != (2, 3, 4):
        raise ValueError("The frozen protocol requires 2/3/4 reads")
    if cfg["QUALIFICATION_SIZE"] != 6 or cfg["QUALIFICATION_ATTEMPTS"] != 2:
        raise ValueError("The reviewed qualification material requires two sets of six")
    if not 1 <= cfg["QUALIFICATION_PASS"] <= 6:
        raise ValueError("Invalid qualification threshold")
    cfg["CONTROL_MIN_ACCURACY"] = float(cfg["CONTROL_MIN_ACCURACY"])
    if not 0 <= cfg["CONTROL_MIN_ACCURACY"] <= 1:
        raise ValueError("Invalid control threshold")
    synthetic = (
        cfg["MAX_SYNTHETIC_SCREENS"]
        if (cfg["PRACTICE_ENABLED"] or cfg["HIDDEN_CONTROLS_ENABLED"])
        else 0
    )
    screens = cfg["PAID_READ_CAP"] + synthetic
    cfg["MAX_FIXED_FEES"] = screens // cfg["FIXED_FEE_MIN_PAIRS"]
    cfg["WORST_CASE_CENTS"] = (
        screens * cfg["PRICE_PER_PAIR_CENTS"] + cfg["MAX_FIXED_FEES"] * cfg["FIXED_FEE_CENTS"]
    )
    if (
        validate_budget
        and cfg["COMPENSATION_ENABLED"]
        and cfg["WORST_CASE_CENTS"] > cfg["BUDGET_CAP_CENTS"]
    ):
        raise ValueError(
            f"Worst-case spend {cfg['WORST_CASE_CENTS'] / 100:.2f} exceeds BUDGET_CAP_EUR"
        )
    # Admission uses the payout minimum; there is no separate batch minimum.
    cfg["ADMISSION_MIN_READS"] = cfg["MIN_PAYOUT_PAIRS"]
    cfg["INITIAL_REAL_BATCH"] = max(0, cfg["MIN_PAYOUT_PAIRS"] - 1)
    return cfg
