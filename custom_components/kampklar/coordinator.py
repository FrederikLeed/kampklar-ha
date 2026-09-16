"""DataUpdateCoordinator for KampKlar."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    Activity,
    KampKlarApiClient,
    KampKlarApiError,
    KampKlarAuthError,
    KampKlarConnectionError,
    MatchInfo,
    MatchLive,
    MatchVenue,
)
from .const import (
    ACTIVITY_TYPE_MATCH,
    ACTIVITY_TYPE_PRACTICE_MATCH,
    CONF_PERSON_ID,
    CONF_PERSONS,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LIVE_SCAN_INTERVAL,
    MATCH_WINDOW_AFTER,
    MATCH_WINDOW_BEFORE,
    VENUE_LOOKUP_TIMEOUT,
    VENUE_LOOKUPS_PER_REFRESH,
    VENUE_MAX_AGE,
    VENUE_RETRY_MAX,
    VENUE_RETRY_MIN,
    VENUE_STORE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

type KampKlarData = dict[int, list[Activity]]

_MATCH_TYPES = (ACTIVITY_TYPE_MATCH, ACTIVITY_TYPE_PRACTICE_MATCH)

# Errors that cost an activity its venue but never the refresh. aiohttp errors arrive as
# KampKlarConnectionError; a total request timeout is a bare TimeoutError and a non-JSON body a ValueError.
_VENUE_ERRORS = (KampKlarApiError, TimeoutError, ValueError)


def venue_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """Return the Store that keeps an entry's venue cache across restarts."""
    return Store(hass, VENUE_STORE_VERSION, f"{DOMAIN}.venues.{entry_id}", private=True)


def _venue_key(match: MatchInfo) -> str:
    """Return the venue cache key of a match: "<match id>_<pool id>"."""
    return f"{match.match_id}_{match.pool_id}"


def _stadium_key(stadium_name: str) -> str:
    """Return the venue cache key of a stadium looked up by name."""
    return f"stadium:{stadium_name.casefold()}"


@dataclass(frozen=True)
class VenueTarget:
    """What one venue lookup is for: a match fixture, or a tournament round's stadium by name."""

    key: str
    stadium_name: str
    match: MatchInfo | None = None

    def is_for(self, record: VenueRecord) -> bool:
        """Return whether a cached record holds this target's stadium; a changed name means it moved.

        Spelling is not a move: a stadium is looked up under its case-folded name, so a record written
        for one spelling belongs to the others too.
        """
        return record.stadium_name.casefold() == self.stadium_name.casefold()


def venue_target(act: Activity) -> VenueTarget | None:
    """Return what to look up for an activity, or None when it names no place to look up.

    A match is looked up by its fixture, which carries the address. A DBU stævne has no match, only the
    name of the stadium its round is played at, so that name is looked up in the stadium register.
    """
    if act.match is not None:
        return VenueTarget(_venue_key(act.match), act.match.stadium_name, act.match)
    if act.stadium_name:
        return VenueTarget(_stadium_key(act.stadium_name), act.stadium_name)
    return None


def _parse_time(value: Any) -> datetime | None:
    """Parse a stored timestamp, or None when it is missing, invalid or has no time zone."""
    parsed = dt_util.parse_datetime(value) if isinstance(value, str) else None
    return parsed if parsed is not None and parsed.tzinfo is not None else None


@dataclass
class VenueRecord:
    """Venue lookup state for one match or stadium."""

    # The activity's stadium name at lookup time; when it changes, the match has moved.
    stadium_name: str
    venue: MatchVenue | None = None
    fetched_at: datetime | None = None
    failures: int = 0
    retry_after: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the record in its stored form."""
        return {
            "stadium_name": self.stadium_name,
            "venue": self.venue.as_dict() if self.venue else None,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "failures": self.failures,
            "retry_after": self.retry_after.isoformat() if self.retry_after else None,
        }

    @classmethod
    def from_dict(cls, data: Any) -> VenueRecord | None:
        """Restore a stored record, dropping invalid parts; None when it is not a record at all."""
        if not isinstance(data, dict) or not isinstance(data.get("stadium_name"), str):
            return None
        venue = data.get("venue")
        failures = data.get("failures")
        return cls(
            stadium_name=data["stadium_name"],
            venue=MatchVenue.from_dict(venue) if isinstance(venue, dict) else None,
            fetched_at=_parse_time(data.get("fetched_at")),
            failures=failures if isinstance(failures, int) and not isinstance(failures, bool) and failures > 0 else 0,
            retry_after=_parse_time(data.get("retry_after")),
        )


class KampKlarCoordinator(DataUpdateCoordinator[KampKlarData]):
    """Coordinator that polls activities for all tracked persons."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, client: KampKlarApiClient, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self._base_interval = timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=self._base_interval,
            config_entry=entry,
        )
        self.client = client
        # Live match per person id (None when no match is in its window).
        self.live_matches: dict[int, MatchLive | None] = {}
        # Venue lookups keyed by match ("<match id>_<pool id>") or stadium name, stored so a restart keeps them.
        self.venues: dict[str, VenueRecord] = {}
        self._venue_store = venue_store(hass, entry.entry_id)
        self._venues_changed = False
        self._venue_store_closed = False

    async def _async_setup(self) -> None:
        """Load the stored venue cache once, before the first refresh."""
        try:
            stored = await self._venue_store.async_load()
        except HomeAssistantError as err:
            _LOGGER.warning("Ignoring unreadable KampKlar venue cache: %s", err)
            return
        records = stored.get("venues") if isinstance(stored, dict) else None
        if not isinstance(records, dict):
            return
        for key, data in records.items():
            if (record := VenueRecord.from_dict(data)) is not None:
                self.venues[key] = record

    def _active_match(self, activities: list[Activity]) -> Activity | None:
        """Return the person's match whose kickoff window contains now, if any."""
        # The API's start/end times are naive local (Danish) times, so compare with local now.
        now = dt_util.now().replace(tzinfo=None)
        for act in activities:
            if act.type_id not in _MATCH_TYPES or act.match is None:
                continue
            start = act.start_time
            end = act.end_time or (start + timedelta(hours=2))
            if start - MATCH_WINDOW_BEFORE <= now <= end + MATCH_WINDOW_AFTER:
                return act
        return None

    async def async_shutdown(self) -> None:
        """Stop polling, and stop writing the venue cache.

        A refresh can still be waiting on a lookup when the entry is unloaded or removed. Saving after
        that would write the store of a removed entry back to disk, where nothing deletes it again.
        """
        self._venue_store_closed = True
        await super().async_shutdown()

    async def _async_update_data(self) -> KampKlarData:
        """Fetch activities with their match venues for all tracked persons, plus live score in a match window."""
        persons: list[dict] = self.config_entry.data[CONF_PERSONS]
        user_id = self.config_entry.data.get("user_id")
        fetched: KampKlarData = {}
        live: dict[int, MatchLive | None] = {}
        try:
            for person in persons:
                person_id = person[CONF_PERSON_ID]
                activities = await self.client.get_person_activities(person_id)
                fetched[person_id] = activities

                live[person_id] = None
                match_act = self._active_match(activities)
                if match_act is not None and user_id is not None:
                    live[person_id] = await self.client.get_match_live(
                        match_act.match.match_id, match_act.match.pool_id, int(user_id)
                    )
        except KampKlarAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except KampKlarConnectionError as err:
            raise UpdateFailed(f"Connection error: {err}") from err

        await self._async_update_venues([act for activities in fetched.values() for act in activities])
        result = {person_id: [self._with_venue(act) for act in acts] for person_id, acts in fetched.items()}

        self.live_matches = live
        # Poll faster while a match is actually live.
        any_live = any(m is not None and m.is_live for m in live.values())
        self.update_interval = LIVE_SCAN_INTERVAL if any_live else self._base_interval
        return result

    async def _async_update_venues(self, activities: list[Activity]) -> None:
        """Look up the venues that are due, forget those of activities no longer listed, and store the cache.

        A venue is due when it is missing, older than a week, its stadium name changed, or its retry wait
        is over. The due lookups run together, each with its own time limit, and at most
        VENUE_LOOKUPS_PER_REFRESH per refresh with the nearest activities first. A hanging lookup therefore
        delays a refresh by VENUE_LOOKUP_TIMEOUT at most. Activities over the limit are not failures; they
        are looked up on a later refresh.
        """
        now = dt_util.utcnow()
        due: dict[str, VenueTarget] = {}
        listed: set[str] = set()
        for act in sorted(activities, key=lambda a: a.start_time):
            if (target := venue_target(act)) is None:
                continue
            listed.add(target.key)
            if target.key not in due and self._venue_due(target, now):
                due[target.key] = target

        lookups = list(due.values())[:VENUE_LOOKUPS_PER_REFRESH]
        if len(due) > len(lookups):
            _LOGGER.debug("Looking up %s of %s due venues, the rest on a later refresh", len(lookups), len(due))
        await asyncio.gather(*(self._async_lookup_venue(target, now) for target in lookups))

        for key in self.venues.keys() - listed:
            del self.venues[key]
            self._venues_changed = True

        if self._venues_changed and not self._venue_store_closed:
            self._venues_changed = False
            await self._venue_store.async_save(
                {"venues": {key: record.as_dict() for key, record in self.venues.items()}}
            )

    def _venue_due(self, target: VenueTarget, now: datetime) -> bool:
        """Return whether a target's venue should be looked up now."""
        record = self.venues.get(target.key)
        if record is None or not target.is_for(record):
            return True
        if record.retry_after is not None:
            return now >= record.retry_after
        return record.fetched_at is None or now - record.fetched_at >= VENUE_MAX_AGE

    async def _async_lookup_venue(self, target: VenueTarget, now: datetime) -> None:
        """Look up a target's venue and record the result.

        A failed lookup never fails the refresh. The target is retried after a wait that doubles with
        each failure, so a broken match id or an unknown stadium name is not requested on every poll. A
        venue fetched earlier for the same stadium is kept while its refresh keeps failing.
        """
        record = self.venues.get(target.key)
        if record is not None and not target.is_for(record):
            record = None

        try:
            async with asyncio.timeout(VENUE_LOOKUP_TIMEOUT):
                if target.match is not None:
                    venue = await self.client.get_match_venue(target.match.match_id, target.match.pool_id)
                else:
                    venue = await self.client.get_stadium_venue(target.stadium_name)
        except _VENUE_ERRORS as err:
            _LOGGER.debug("Venue lookup for %s failed: %r", target.key, err)
            venue = None

        self._venues_changed = True
        if venue is not None:
            self.venues[target.key] = VenueRecord(target.stadium_name, venue, fetched_at=now)
            return

        failures = (record.failures if record else 0) + 1
        delay = min(VENUE_RETRY_MIN * 2 ** min(failures - 1, 10), VENUE_RETRY_MAX)
        _LOGGER.debug("No venue for %s after %s attempt(s), retrying in %s", target.key, failures, delay)
        self.venues[target.key] = VenueRecord(
            target.stadium_name,
            record.venue if record else None,
            fetched_at=record.fetched_at if record else None,
            failures=failures,
            retry_after=now + delay,
        )

    def _with_venue(self, act: Activity) -> Activity:
        """Return the activity with its venue attached when one is known for its current stadium."""
        if (target := venue_target(act)) is None:
            return act
        record = self.venues.get(target.key)
        if record is None or record.venue is None or not target.is_for(record):
            return act
        return replace(act, venue=record.venue)
