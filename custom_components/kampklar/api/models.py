"""Data models for the KampKlar API."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

_MIDNIGHT = datetime.min.time()


def _text(value: Any) -> str:
    """Return an API text value stripped; empty for null or anything that is not text or a whole number."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return ""


def _coordinate(value: Any, limit: float) -> float | None:
    """Return a coordinate as a float between -limit and limit, or None when missing or invalid."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and abs(number) <= limit else None


def repair_meeting_time(meeting_time: datetime | None, start_time: datetime) -> datetime | None:
    """Return the meeting time to use for an activity starting at start_time, or None.

    DBU sometimes stores a meeting time whose date lies weeks before the activity while its time of
    day is right, so the time of day is kept on the activity's date. A result that is not before the
    start is not a meeting time, and neither is exactly midnight: that is how DBU writes a date
    without a time.
    """
    if meeting_time is None or meeting_time.time() == _MIDNIGHT:
        return None
    if meeting_time.date() != start_time.date():
        meeting_time = meeting_time.replace(year=start_time.year, month=start_time.month, day=start_time.day)
    return meeting_time if meeting_time < start_time else None


@dataclass(frozen=True)
class User:
    """Authenticated user."""

    user_id: int
    person_id: int
    first_name: str
    last_name: str
    email: str
    ref_calendar_url: str = ""
    team_calendar_url: str = ""
    activity_calendar_url: str = ""

    @classmethod
    def from_api(cls, data: dict) -> User:
        """Create from API response data dict."""
        return cls(
            user_id=int(data["userId"]),
            person_id=int(data["personId"]),
            first_name=data["firstName"],
            last_name=data["lastName"],
            email=data.get("email", ""),
            ref_calendar_url=data.get("refCalendarUrl") or "",
            team_calendar_url=data.get("myTeamCalendarUrl") or "",
            activity_calendar_url=data.get("teamActivityCalendarUrl") or "",
        )


@dataclass(frozen=True)
class MatchInfo:
    """Match details embedded in an activity."""

    match_id: int
    pool_id: int
    home_team_name: str
    away_team_name: str
    stadium_name: str
    field_name: str
    row_name: str
    home_team_logo_url: str
    away_team_logo_url: str

    @classmethod
    def from_api(cls, data: dict) -> MatchInfo:
        """Create from API match sub-object."""
        return cls(
            match_id=int(data["matchId"]),
            pool_id=int(data["poolId"]),
            home_team_name=data.get("homeTeamName") or "",
            away_team_name=data.get("awayTeamName") or "",
            # Stripped and never None: the stadium name is stored with the venue cache to notice a moved match.
            stadium_name=_text(data.get("stadiumName")),
            field_name=_text(data.get("fieldName")),
            row_name=data.get("rowName") or "",
            home_team_logo_url=data.get("homeTeamLogoUrl") or "",
            away_team_logo_url=data.get("awayTeamLogoUrl") or "",
        )


@dataclass(frozen=True)
class MatchVenue:
    """Where an activity is played: a match's stadium from Match/GetMatch, or a stadium from the register."""

    name: str
    address: str
    zip: str
    city: str
    latitude: float | None
    longitude: float | None
    field_name: str = ""

    @classmethod
    def from_api(cls, match: dict) -> MatchVenue | None:
        """Create from a GetMatch response, or None when it carries no usable stadium.

        A stadium needs an address, zip, city or coordinates: a bare name locates nothing, and the
        activity's meeting place is a better calendar location than that.
        """
        stadium = match.get("stadium")
        if not isinstance(stadium, dict):
            return None
        venue = cls.from_dict({**stadium, "field_name": match.get("fieldName")})
        return venue if venue.is_locatable else None

    @classmethod
    def from_stadium_search(cls, results: Any, name: str) -> MatchVenue | None:
        """Pick the venue named name out of a Stadium/GetListStadiumSearch response, or None.

        A tournament round names its stadium without an address, so the name is searched in DBU's
        stadium register. The search matches anywhere in a stadium's name or city, so an exact name
        wins; a search that hit a single stadium is that stadium, since the register sometimes spells
        the name with a suffix the activity leaves out. The register holds the same stadium twice now
        and then, differing only in the phone number, so the first usable row is taken.
        """
        if not isinstance(results, list):
            return None
        entries = [entry for entry in results if isinstance(entry, dict)]
        wanted = name.strip().casefold()
        exact = [entry for entry in entries if _text(entry.get("name")).casefold() == wanted]
        for entry in exact or (entries if len(entries) == 1 else []):
            venue = cls.from_dict(entry)
            if venue.is_locatable:
                return venue
        return None

    @classmethod
    def from_dict(cls, data: dict) -> MatchVenue:
        """Create from a dict with the stadium keys (name, address, zip, city, latitude, longitude, field_name)."""
        latitude = _coordinate(data.get("latitude"), 90)
        longitude = _coordinate(data.get("longitude"), 180)
        if latitude is None or longitude is None or (latitude == 0 and longitude == 0):
            # A coordinate is only useful as a pair, and 0,0 is a placeholder rather than a place.
            latitude = longitude = None
        return cls(
            name=_text(data.get("name")),
            address=_text(data.get("address")),
            zip=_text(data.get("zip")),
            city=_text(data.get("city")),
            latitude=latitude,
            longitude=longitude,
            field_name=_text(data.get("field_name")),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dict that from_dict reads back."""
        return asdict(self)

    @property
    def formatted_address(self) -> str:
        """Return the one-line address "<name>, <address>, <zip> <city>", skipping empty parts."""
        town = " ".join(part for part in (self.zip, self.city) if part)
        return ", ".join(part for part in (self.name, self.address, town) if part)

    @property
    def location_text(self) -> str:
        """Return the calendar location: the name, a line break, then "<address>, <zip> <city>".

        Apple Calendar writes a place this way, and Calendar Relay turns the two lines into the title and
        address of Apple's structured location. Without both a name and an address this is formatted_address.
        """
        town = " ".join(part for part in (self.zip, self.city) if part)
        rest = ", ".join(part for part in (self.address, town) if part)
        if self.name and rest:
            return f"{self.name}\n{rest}"
        return self.formatted_address

    @property
    def has_coordinates(self) -> bool:
        """Return True when both latitude and longitude are known."""
        return self.latitude is not None and self.longitude is not None

    @property
    def is_locatable(self) -> bool:
        """Return True when the venue points at a place: a bare name locates nothing."""
        return bool(self.address or self.zip or self.city) or self.has_coordinates


@dataclass(frozen=True)
class MatchEvent:
    """A single live-score event (goal, card, ...)."""

    minute: int | None
    type_name: str
    is_home: bool
    player: str
    is_goal: bool
    is_card: bool

    @classmethod
    def from_api(cls, data: dict) -> MatchEvent:
        """Create from a MatchLiveScoreModel entry."""
        person = data.get("person") or {}
        player = " ".join(p for p in (person.get("firstName"), person.get("lastName")) if p).strip()
        return cls(
            minute=data.get("minute"),
            type_name=data.get("eventTypeName") or "",
            is_home=bool(data.get("isHomeTeamPlayer")),
            player=player,
            is_goal=bool(data.get("isGoal")),
            is_card=bool(data.get("isCard")),
        )


@dataclass(frozen=True)
class MatchLive:
    """Live (or pre/post) state of a match."""

    match_id: int
    home_team: str
    away_team: str
    home_logo: str
    away_logo: str
    home_score: int | None
    away_score: int | None
    current_minute: int | None
    is_live: bool
    status_text: str
    match_length_text: str
    events: list[MatchEvent]
    kickoff: datetime | None
    stadium: str

    @classmethod
    def from_api(cls, match: dict, live: dict) -> MatchLive:
        """Build from a GetMatch response and a GetMatchLiveScoreData response."""
        minute = live.get("currentMinute")
        is_live = minute is not None
        # Live result wins while the match is running; otherwise the fixture's final score.
        home_score = live.get("homeResult") if is_live else match.get("homeScore")
        away_score = live.get("awayResult") if is_live else match.get("awayScore")
        events = [MatchEvent.from_api(e) for e in (live.get("matchLiveScoreList") or [])]
        kickoff = None
        date = match.get("matchDate")
        time = match.get("matchTime")
        if date:
            iso = date.split("T")[0] + ("T" + time if time else "T00:00")
            try:
                kickoff = datetime.fromisoformat(iso)
            except ValueError:
                kickoff = None
        return cls(
            match_id=int(match.get("id", 0)),
            home_team=match.get("homeTeamName", ""),
            away_team=match.get("awayTeamName", ""),
            home_logo=match.get("homeTeamLogoUrl") or "",
            away_logo=match.get("awayTeamLogoUrl") or "",
            home_score=home_score,
            away_score=away_score,
            current_minute=minute,
            is_live=is_live,
            status_text=live.get("messageText") or "",
            match_length_text=live.get("matchLengthText") or "",
            events=events,
            kickoff=kickoff,
            stadium=match.get("stadiumName") or "",
        )


@dataclass(frozen=True)
class Activity:
    """A person's activity (training, match, tournament)."""

    activity_id: int
    name: str
    type_id: int
    type_name: str
    start_time: datetime
    end_time: datetime | None
    meeting_time: datetime | None
    meeting_place: str
    team_id: int
    team_name: str
    club_name: str
    club_logo_url: str
    signup_status_id: int | None
    signup_status_name: str
    subscribed: int
    subscribed_text: str
    person_contact_id: int | None
    person_contact_name: str
    match: MatchInfo | None
    is_open_for_signup: bool = False
    subscription_deadline: datetime | None = None
    team_assignment_name: str = ""
    tasks: int = 0
    # Stadium of a tournament round (a DBU stævne), which has no match object; matches carry theirs on match.
    stadium_name: str = ""
    # Set by the coordinator from Match/GetMatch or the stadium register: the feed has no address or coordinates.
    venue: MatchVenue | None = None

    @property
    def effective_meeting_time(self) -> datetime | None:
        """Return the meeting time to show, repaired onto the activity's date (see repair_meeting_time)."""
        return repair_meeting_time(self.meeting_time, self.start_time)

    @classmethod
    def from_api(cls, entry: dict) -> Activity:
        """Create from a PersonActivity/GetList array entry."""
        act = entry["activity"]
        match_data = act.get("match")
        return cls(
            activity_id=int(act["id"]),
            name=act["name"],
            type_id=int(act["typeId"]),
            type_name=act.get("typeName", ""),
            start_time=datetime.fromisoformat(act["startTime"]),
            end_time=datetime.fromisoformat(act["endTime"]) if act.get("endTime") else None,
            meeting_time=datetime.fromisoformat(act["meetingTime"]) if act.get("meetingTime") else None,
            meeting_place=_text(act.get("meetingPlace")),
            team_id=int(act.get("teamId", 0)),
            team_name=act.get("teamName", ""),
            club_name=act.get("clubName", ""),
            club_logo_url=act.get("clubLogoUrl", ""),
            signup_status_id=int(act["signupStatusId"]) if act.get("signupStatusId") is not None else None,
            signup_status_name=act.get("signupStatusName", ""),
            subscribed=int(act.get("subscribed", 0)),
            subscribed_text=act.get("subscribedText", ""),
            person_contact_id=int(act["personContactId"]) if act.get("personContactId") is not None else None,
            person_contact_name=act.get("personContactName") or "",
            match=MatchInfo.from_api(match_data) if match_data else None,
            is_open_for_signup=bool(act.get("isOpenForSignUp")),
            subscription_deadline=(
                datetime.fromisoformat(act["subscriptionDeadline"]) if act.get("subscriptionDeadline") else None
            ),
            team_assignment_name=act.get("teamAssignmentName") or "",
            tasks=int(act.get("tasks", 0)),
            stadium_name=_text((act.get("stadiumRound") or {}).get("stadiumName")),
        )
