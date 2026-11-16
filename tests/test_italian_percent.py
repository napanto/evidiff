# SPDX-License-Identifier: AGPL-3.0-only
import pytest

from app.i18n import italian_al, translate


@pytest.mark.parametrize(
    "percent, expected",
    [
        (0, "Studio completo allo 0%"),
        (1, "Studio completo all’1%"),
        (2, "Studio completo al 2%"),
        (8, "Studio completo all’8%"),
        (11, "Studio completo all’11%"),
        (18, "Studio completo al 18%"),
        (37, "Studio completo al 37%"),
        (80, "Studio completo all’80%"),
        (88, "Studio completo all’88%"),
        (89, "Studio completo all’89%"),
        (90, "Studio completo al 90%"),
        (100, "Studio completo al 100%"),
    ],
)
def test_italian_percentage_article(percent, expected):
    assert translate("it", "study_percent", percent=percent) == expected


def test_english_percentage_unchanged():
    assert translate("en", "study_percent", percent=0) == "Study 0% complete"


def test_every_integer_gets_an_article():
    assert all(italian_al(n) in ("al ", "allo ", "all’") for n in range(101))
