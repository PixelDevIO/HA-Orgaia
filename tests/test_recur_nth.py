"""Monthly series on the nth weekday of the month, as the app's recur.ts counts them."""

from custom_components.orgaia.protocol.recur import nth_weekday_of_month, occurrence_dates


def test_every_first_monday() -> None:
    item = {"start": "2026-12-07T19:00", "repeat": {"freq": "month", "interval": 1, "nth": 1}}
    assert occurrence_dates(item, "2026-11-01", "2027-04-30") == [
        "2026-12-07",
        "2027-01-04",
        "2027-02-01",
        "2027-03-01",
        "2027-04-05",
    ]


def test_every_last_friday() -> None:
    item = {"start": "2026-11-27T20:00", "repeat": {"freq": "month", "interval": 1, "nth": 5}}
    assert occurrence_dates(item, "2026-11-01", "2027-03-31") == [
        "2026-11-27",
        "2026-12-25",
        "2027-01-29",
        "2027-02-26",
        "2027-03-26",
    ]


def test_every_other_month_far_ahead() -> None:
    item = {"dueDate": "2026-12-19", "repeat": {"freq": "month", "interval": 2, "nth": 3}}
    assert occurrence_dates(item, "2026-12-01", "2027-06-30") == [
        "2026-12-19",
        "2027-02-20",
        "2027-04-17",
        "2027-06-19",
    ]
    assert occurrence_dates(item, "2030-02-01", "2030-02-28") == ["2030-02-16"]


def test_never_before_the_first_date() -> None:
    item = {"dueDate": "2026-12-10", "repeat": {"freq": "month", "interval": 1, "nth": 1}}
    assert occurrence_dates(item, "2026-12-01", "2027-01-31") == ["2027-01-07"]


def test_the_evening_before_follows() -> None:
    item = {"dueDate": "2027-01-31", "repeat": {"freq": "month", "interval": 1, "nth": 1, "back": 1}}
    assert occurrence_dates(item, "2027-01-01", "2027-04-30") == ["2027-01-31", "2027-02-28", "2027-04-04"]


def test_the_day_itself() -> None:
    assert nth_weekday_of_month("2026-11-01", 0, 1) == "2026-11-01"
    assert nth_weekday_of_month("2026-11-01", 1, 5) == "2026-11-30"
    assert nth_weekday_of_month("2026-11-01", 2, 5) == "2026-11-24"
