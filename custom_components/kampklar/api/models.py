"""Data models for the KampKlar API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class User:
    """Authenticated user."""

    user_id: int
    person_id: int
    first_name: str
    last_name: str
    email: str

    @classmethod
    def from_api(cls, data: dict) -> User:
        """Create from API response data dict."""
        return cls(
            user_id=data["userId"],
            person_id=data["personId"],
            first_name=data["firstName"],
            last_name=data["lastName"],
            email=data.get("email", ""),
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
            match_id=data["matchId"],
            pool_id=data["poolId"],
            home_team_name=data.get("homeTeamName", ""),
            away_team_name=data.get("awayTeamName", ""),
            stadium_name=data.get("stadiumName", ""),
            field_name=data.get("fieldName", ""),
            row_name=data.get("rowName", ""),
            home_team_logo_url=data.get("homeTeamLogoUrl", ""),
            away_team_logo_url=data.get("awayTeamLogoUrl", ""),
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
    person_contact_id: int
    person_contact_name: str
    match: MatchInfo | None

    @classmethod
    def from_api(cls, entry: dict) -> Activity:
        """Create from a PersonActivity/GetList array entry."""
        act = entry["activity"]
        match_data = act.get("match")
        return cls(
            activity_id=act["id"],
            name=act["name"],
            type_id=act["typeId"],
            type_name=act.get("typeName", ""),
            start_time=datetime.fromisoformat(act["startTime"]),
            end_time=datetime.fromisoformat(act["endTime"]) if act.get("endTime") else None,
            meeting_time=datetime.fromisoformat(act["meetingTime"]) if act.get("meetingTime") else None,
            meeting_place=act.get("meetingPlace", ""),
            team_id=act.get("teamId", 0),
            team_name=act.get("teamName", ""),
            club_name=act.get("clubName", ""),
            club_logo_url=act.get("clubLogoUrl", ""),
            signup_status_id=act.get("signupStatusId"),
            signup_status_name=act.get("signupStatusName", ""),
            subscribed=act.get("subscribed", 0),
            subscribed_text=act.get("subscribedText", ""),
            person_contact_id=act["personContactId"],
            person_contact_name=act.get("personContactName", ""),
            match=MatchInfo.from_api(match_data) if match_data else None,
        )
