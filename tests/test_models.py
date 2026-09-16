"""Tests for the KampKlar API models: match venues and meeting times."""

from __future__ import annotations

from datetime import datetime

import pytest

from custom_components.kampklar.api import Activity, MatchVenue
from custom_components.kampklar.api.models import repair_meeting_time

from .conftest import load_fixture


def test_venue_from_get_match_strips_text(get_match_response):
    """Venue text is stripped (DBU sends an address with a trailing space) and coordinates are floats."""
    venue = MatchVenue.from_api(get_match_response)

    assert venue == MatchVenue(
        name="Testby Stadion",
        address="Prøvevej 1",
        zip="1234",
        city="Testby",
        latitude=56.123456,
        longitude=9.654321,
        field_name="Bane 2",
    )
    assert venue.formatted_address == "Testby Stadion, Prøvevej 1, 1234 Testby"
    assert venue.has_coordinates


@pytest.mark.parametrize(
    ("stadium", "expected"),
    [
        ({"name": " Testby Stadion", "address": "", "zip": "1234", "city": "Testb"}, "Testby Stadion, 1234 Testb"),
        ({"name": "Testby Stadion", "address": "Prøvevej 1", "zip": None, "city": "  "}, "Testby Stadion, Prøvevej 1"),
        ({"name": "", "address": "Prøvevej 1", "zip": 1234, "city": "Testby"}, "Prøvevej 1, 1234 Testby"),
        (
            {"name": "Testby Stadion", "address": "Prøvevej 1", "zip": "", "city": "Testby"},
            "Testby Stadion, Prøvevej 1, Testby",
        ),
    ],
)
def test_formatted_address_skips_empty_parts(stadium, expected):
    """The one-line address leaves out empty parts without stray separators."""
    assert MatchVenue.from_api({"stadium": stadium}).formatted_address == expected


@pytest.mark.parametrize(
    ("stadium", "expected"),
    [
        (
            {"name": "Testby Stadion", "address": "Prøvevej 1", "zip": "1234", "city": "Testby"},
            "Testby Stadion\nPrøvevej 1, 1234 Testby",
        ),
        ({"name": "Testby Stadion", "address": "", "zip": "1234", "city": "Testby"}, "Testby Stadion\n1234 Testby"),
        ({"name": "Testby Stadion", "latitude": 56.5, "longitude": 9.25}, "Testby Stadion"),
        ({"name": "", "address": "Prøvevej 1", "zip": "1234", "city": "Testby"}, "Prøvevej 1, 1234 Testby"),
    ],
)
def test_location_text_puts_the_name_on_its_own_line(stadium, expected):
    """The calendar location is the name, a line break, then the address, as Apple Calendar writes a place."""
    assert MatchVenue.from_api({"stadium": stadium}).location_text == expected


def test_coordinates_given_as_text_are_parsed():
    """Coordinates sent as strings still become floats."""
    venue = MatchVenue.from_api({"stadium": {"name": "Testby Stadion", "latitude": " 56.5", "longitude": "9.25"}})
    assert (venue.latitude, venue.longitude) == (56.5, 9.25)


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (None, 9.6),
        (56.1, None),
        ("", ""),
        ("north", 9.6),
        (True, 9.6),
        (0, 0),
        (91.0, 9.6),
        (56.1, 181),
        (float("nan"), 9.6),
        ([56.1], 9.6),
    ],
)
def test_invalid_coordinates_are_none(latitude, longitude):
    """Missing, invalid, out-of-range or placeholder coordinates give no coordinates at all."""
    stadium = {"name": "Testby Stadion", "address": "Prøvevej 1", "latitude": latitude, "longitude": longitude}
    venue = MatchVenue.from_api({"stadium": stadium})
    assert venue.latitude is None
    assert venue.longitude is None
    assert not venue.has_coordinates


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"stadium": None},
        {"stadium": "Testby Stadion"},
        {"stadium": {"name": " ", "address": "", "zip": None, "latitude": None}},
        # A bare name locates nothing; the activity's meeting place stays the better location.
        {
            "stadium": {"name": "Testby Stadion", "address": " ", "zip": None, "city": "", "latitude": None},
            "fieldName": "Bane 2",
        },
    ],
)
def test_response_without_stadium_is_no_venue(payload):
    """A GetMatch response without a usable stadium gives no venue."""
    assert MatchVenue.from_api(payload) is None


@pytest.mark.parametrize(
    "stadium",
    [
        {"name": "Testby Stadion", "zip": "1234"},
        {"name": "Testby Stadion", "city": "Testby"},
        {"name": "Testby Stadion", "latitude": 56.1, "longitude": 9.6},
    ],
)
def test_stadium_with_any_location_part_is_a_venue(stadium):
    """A zip, a city or coordinates alone are enough for a venue."""
    assert MatchVenue.from_api({"stadium": stadium}) is not None


def test_venue_dict_round_trip(mock_venue):
    """The stored form reads back to the same venue."""
    assert MatchVenue.from_dict(mock_venue.as_dict()) == mock_venue


START = datetime(2026, 3, 14, 11, 0)


@pytest.mark.parametrize(
    ("meeting", "expected"),
    [
        (datetime(2026, 3, 14, 9, 45), datetime(2026, 3, 14, 9, 45)),
        # DBU quirk: the date lies weeks before the match while the time of day is sensible.
        (datetime(2026, 2, 20, 10, 0), datetime(2026, 3, 14, 10, 0)),
        (datetime(2026, 4, 2, 9, 50), datetime(2026, 3, 14, 9, 50)),
        (datetime(2026, 3, 14, 11, 0), None),
        (datetime(2026, 3, 14, 11, 30), None),
        (datetime(2026, 2, 20, 12, 0), None),
        # Midnight is how DBU writes a date without a time, not a meeting at 00:00.
        (datetime(2026, 3, 14, 0, 0), None),
        (datetime(2026, 2, 20, 0, 0), None),
        (datetime(2026, 3, 14, 0, 1), datetime(2026, 3, 14, 0, 1)),
        (None, None),
    ],
)
def test_repair_meeting_time(meeting, expected):
    """The time of day moves onto the start date; a result at midnight or not before the start is dropped."""
    assert repair_meeting_time(meeting, START) == expected


def test_activity_keeps_raw_meeting_time_and_repairs_the_effective_one():
    """Activity keeps the API value and exposes the repaired one; the meeting place is stripped."""
    entry = load_fixture("person_activities.json")[0]
    entry["activity"]["meetingTime"] = "2026-02-20T10:00:00"
    entry["activity"]["meetingPlace"] = " TBK "

    act = Activity.from_api(entry)

    assert act.meeting_time == datetime(2026, 2, 20, 10, 0)
    assert act.effective_meeting_time == datetime(2026, 3, 14, 10, 0)
    assert act.meeting_place == "TBK"
    assert act.venue is None


def test_activity_with_null_meeting_place():
    """A null meetingPlace becomes an empty string."""
    entry = load_fixture("person_activities.json")[1]
    entry["activity"]["meetingPlace"] = None
    assert Activity.from_api(entry).meeting_place == ""


def test_match_text_fields_are_never_none():
    """Null text in the embedded match becomes empty strings, and the stadium and field names are stripped."""
    entry = load_fixture("person_activities.json")[0]
    entry["activity"]["match"].update(
        stadiumName=None,
        fieldName=" Bane 1 ",
        homeTeamName=None,
        awayTeamName=None,
        rowName=None,
        homeTeamLogoUrl=None,
        awayTeamLogoUrl=None,
    )

    match = Activity.from_api(entry).match

    assert match.stadium_name == ""
    assert match.field_name == "Bane 1"
    assert (match.home_team_name, match.away_team_name, match.row_name) == ("", "", "")
    assert (match.home_team_logo_url, match.away_team_logo_url) == ("", "")


@pytest.mark.parametrize(
    ("results", "name", "expected"),
    [
        # The exact name wins over the ones the search matched on a substring.
        (
            [
                {"name": "Testby Hallen (Inde)", "address": "Hallevej 1", "zip": "1234", "city": "Testby"},
                {"name": "Testby Hallen", "address": "Hallevej 1", "zip": "1234", "city": "Testby"},
            ],
            "Testby Hallen",
            "Testby Hallen, Hallevej 1, 1234 Testby",
        ),
        # Case and surrounding spaces do not decide a name.
        (
            [{"name": " testby hallen ", "address": "Hallevej 1", "zip": "1234", "city": "Testby"}],
            "Testby Hallen",
            "testby hallen, Hallevej 1, 1234 Testby",
        ),
        # The register spells the name with a suffix; a search that hit one stadium is that stadium.
        (
            [{"name": "Testby Arena (Sponsor)", "address": "Arenavej 3", "zip": "1234", "city": "Testby"}],
            "Testby Arena",
            "Testby Arena (Sponsor), Arenavej 3, 1234 Testby",
        ),
        # The same stadium twice, the first row without a place: the usable one is taken.
        (
            [
                {"name": "Testby Hallen", "address": " ", "zip": None, "city": ""},
                {"name": "Testby Hallen", "address": "Hallevej 1", "zip": "1234", "city": "Testby"},
            ],
            "Testby Hallen",
            "Testby Hallen, Hallevej 1, 1234 Testby",
        ),
    ],
)
def test_venue_from_stadium_search(results, name, expected):
    """The stadium register answer is narrowed down to the one stadium the activity names."""
    assert MatchVenue.from_stadium_search(results, name).formatted_address == expected


@pytest.mark.parametrize(
    ("results", "name"),
    [
        ([], "Testby Hallen"),
        (None, "Testby Hallen"),
        ("Testby Hallen", "Testby Hallen"),
        ([None, "Testby Hallen"], "Testby Hallen"),
        # Several hits, none of them named that: too many places to pick one.
        (
            [
                {"name": "Testby Stadion", "address": "Prøvevej 1", "zip": "1234", "city": "Testby"},
                {"name": "Testby Skole", "address": "Skolevej 2", "zip": "1234", "city": "Testby"},
            ],
            "Testby",
        ),
        # The one hit has a name but no place.
        ([{"name": "Testby Hallen", "address": "", "zip": None, "city": " "}], "Testby Hallen"),
    ],
)
def test_venue_from_stadium_search_without_a_place(results, name):
    """A search that places no stadium gives no venue."""
    assert MatchVenue.from_stadium_search(results, name) is None


def test_activity_takes_the_stadium_name_of_its_round():
    """A stævne carries its stadium on stadiumRound, stripped; a match leaves the activity's name empty."""
    entry = load_fixture("person_activities.json")[0]
    entry["activity"]["stadiumRound"] = {"stadiumName": " Testby Hallen ", "poolName": "Pulje 206"}
    assert Activity.from_api(entry).stadium_name == "Testby Hallen"

    entry["activity"]["stadiumRound"] = {"stadiumName": None, "poolName": "Pulje 541"}
    assert Activity.from_api(entry).stadium_name == ""

    entry["activity"]["stadiumRound"] = None
    assert Activity.from_api(entry).stadium_name == ""
