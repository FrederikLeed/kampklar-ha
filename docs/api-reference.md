# DBU Fodbold App — API Reference

Reverse-engineered from mitmproxy capture of the iOS "Fodbold" app (v6.10, build 2137).

## Authentication

All endpoints use **HTTP Basic Auth** with a shared app-level credential:

- **Header:** `Authorization: Basic QXBwU2VydmljZTohRm9kYm9sZCEyMw==`
- **Decoded:** `AppService:!Fodbold!23`

This is NOT a per-user credential — it's a static app secret. User authentication is done via a separate login endpoint that returns user/person IDs used in subsequent calls.

## Two API Backends

### 1. `dbuappwebapi.dbu.dk` (JSON API — preferred)
- Format: JSON
- Server: IIS/10.0, ASP.NET
- Used for most modern endpoints

### 2. `appservice.dbu.dk` (Legacy XML API)
- Format: XML with `application/xml; charset=utf-8`
- Server: IIS/10.0, ASP.NET 4.0
- XML payloads wrapped in `<Payload>...</Payload>`
- Response uses WCF DataContract serialization namespaces

---

## Key IDs

| Concept | Example | Notes |
|---------|---------|-------|
| `userId` | `100001` | Login account ID |
| `personId` | `200001` | Person in DBU system (parent) |
| `personId` (child) | `300001` | Child player linked to parent account |
| `deviceId` | `100000` | Registered device ID |
| `teamId` | `126` | KampKlar team ID (KO team) |
| `clubId` | `445ca99b-d30c-4998-b540-38130c29b526` | Club GUID (AaB) |
| `clubId` (int) | `2` | Numeric club ID |
| `activityId` | `6446192` | Training/match/tournament activity |
| `matchId` | `430111` | Match in the competition system |
| `poolId` | `476348` | Pool/group in a tournament row |
| `rowId` | `124906` | Tournament row (e.g. "U14 Drenge Liga 3") |

---

## Endpoints — JSON API (`dbuappwebapi.dbu.dk`)

### Authentication

#### POST `/api/User/GetUserByCredentials?deviceId={deviceId}`
Login with username/password.

**Request:**
```json
{"UserName":"username","Password":"password"}
```

**Response:**
```json
{
  "returnValue": 1,
  "messageText": "OK",
  "isSuccess": true,
  "data": {
    "userId": 100001,
    "userName": "testuser",
    "personId": 200001,
    "firstName": "Test",
    "lastName": "Ansen",
    "gender": 0,
    "dob": "1990-01-01T00:00:00",
    "address": "...",
    "zip": "9000",
    "city": "Aalborg",
    "countryId": 1,
    "email": "...",
    "mobile": "...",
    "imageUrl": "https://file.dbu.dk/images/user//100001.jpg?dt=...",
    "refCalendarUrl": "webcal://ical.dbu.dk/...",
    "myTeamCalendarUrl": "webcal://ical.dbu.dk/...",
    "teamActivityCalendarUrl": "webcal://ical.dbu.dk/..."
  }
}
```

#### POST `/api/User/LogoutUser?deviceId={deviceId}`
Logout user.

---

### Person Activities (Main Feed)

#### GET `/api/PersonActivity/GetList?deviceId={deviceId}&personId={personId}`
**Primary endpoint for the integration.** Returns upcoming activities across ALL teams for a person. This is the "KampKlar" feed.

**Response:** Array of activity entries:
```json
[
  {
    "activity": {
      "id": 6446194,
      "name": "AaB - FC Skanderborg",
      "clubId": "445ca99b-...",
      "clubName": "AaB",
      "clubLogoUrl": "https://file.dbu.dk/images/club/2/AaB.png",
      "teamId": 126,
      "teamName": "U14 Drenge",
      "typeId": 2,               // 1=Træning, 2=Kamp, 4=Stævne
      "typeName": "Kamp",
      "startTime": "2026-03-14T11:00:00",
      "endTime": "2026-03-14T12:20:00",
      "meetingTime": "2026-03-12T09:45:00",
      "meetingPlace": "Hornevej 2, 9220 Aalborg Øst",
      "stadiumText": "",
      "match": {                  // null for training
        "matchId": 604671,
        "poolId": 489985,
        "matchDate": "2026-03-14T00:00:00",
        "matchTime": "11:00",
        "homeTeamName": "AaB",
        "homeTeamLogoUrl": "...",
        "awayTeamName": "FC Skanderborg",
        "awayTeamLogoUrl": "...",
        "stadiumName": "AaB's Anlæg",
        "fieldName": "Bane 7 ny kunstgræs",
        "rowName": "U14 Drenge Liga 2A (2012) 11:11 - forår 2026",
        "poolName": "Pulje 611"
      },
      "signupStatusId": 2,        // null, 0=Ikke svaret, 1=Frameldt, 2=Tilmeldt, 3=Til rådighed, 4=Udtaget
      "signupStatusName": "Tilmeldt",
      "isConfirmed": false,
      "personContactId": 300001,
      "personContactName": "Anders Test Rex Ansen",
      "subscribed": 13,
      "subscribedText": "13 tilmeldte",
      "tasks": 0,
      "roleId": 3,
      "isOpenForSignUp": false
    },
    "activityDateTime": "2026-03-14T11:00:00",
    "eType": 2,                   // entry type
    "sortingIndex": 0
  }
]
```

**Activity typeId values:**
| typeId | typeName | Description |
|--------|----------|-------------|
| 1 | Træning | Training session |
| 2 | Kamp | Match |
| 4 | Stævne | Tournament |

**signupStatusId values:**
| id | name | Description |
|----|------|-------------|
| 0 | Ikke svaret | Not responded |
| 1 | Frameldt | Signed off / absent |
| 2 | Tilmeldt | Signed up |
| 3 | Til rådighed | Available (for selection) |
| 4 | Udtaget | Selected |
| 7 | Tilmeldte trænere | Registered coaches |

---

### Team Activities

#### GET `/api/TeamActivity/GetTeamActivityList?deviceId={deviceId}&teamId={teamId}&clubId={clubId}&personId={personId}&isCoach={bool}&all={bool}&fromDate={ticks}`
List activities for a specific team. `fromDate` uses .NET ticks format.

**Response:** Array with richer sign-up count data:
```json
{
  "id": 6446194,
  "name": "AaB - FC Skanderborg",
  "startTime": "2026-03-14T11:00:00",
  "typeId": 2,
  "teamId": 126,
  "clubId": "445ca99b-...",
  "isPublic": true,
  "isLocked": true,
  "signUpStatus": {"id": 2, "name": "Tilmeldt"},
  "signUpCountList": [
    {"signUpStatus": {"id": 0, "name": "Ikke svaret"}, "count": 21},
    {"signUpStatus": {"id": 2, "name": "Tilmeldt"}, "count": 13},
    {"signUpStatus": {"id": 1, "name": "Frameldt"}, "count": 3},
    {"signUpStatus": {"id": 7, "name": "Tilmeldte trænere"}, "count": 0}
  ],
  "matchId": 604671,
  "homeTeamName": "AaB",
  "awayTeamName": "FC Skanderborg",
  "rowName": "U14 Drenge Liga 2A (2012) 11:11 - forår 2026",
  "poolName": "Pulje 611"
}
```

#### GET `/api/TeamActivity/GetTeamActivityPerson?activityId={id}&personId={personId}&isTeamPerson={bool}&deviceId={deviceId}&appversion=6.10`
Get activity details for a specific person (sign-up status, description, deadlines, etc.).

**Response includes:**
- `signUpStatusId/Name` — current sign-up status
- `teamActivity.description` — full activity description text
- `teamActivity.startTime/endTime/meetingTime/meetingPlace`
- `teamActivity.signUpCountList` — attendance counts
- `teamActivity.maxParticipants` — max player slots
- `teamActivity.subscriptionDeadline` — sign-up deadline
- `teamActivity.isOpenForSignup/isOpenForSignoff`
- `teamActivity.match` — match details if type=Kamp
- `createdByPerson` — who created the sign-up entry

#### GET `/api/TeamActivity/GetListTeamActivityTeamMemberPerson?activityId={id}&isTeamPerson={bool}&deviceId={deviceId}&appversion=6.10`
Get all team members and their sign-up status for an activity. Returns full roster.

**Response:** Array of:
```json
{
  "person": {
    "id": 300002,
    "firstName": "Spiller",
    "lastName": "Eksansen",
    "gender": 0,
    "dob": "2012-01-01T00:00:00",
    "imageUrl": "...",
    "email": "...",
    "mobile": "..."
  },
  "teamActivityPerson": {      // null if no response yet
    "id": 124426558,
    "signUpStatusId": 1,
    "signUpStatusName": "Frameldt",
    "isConfirmed": false,
    "createdByPerson": {...},
    "created": "2026-02-25T15:56:19.08"
  },
  "hasAbsence": true,
  "showWarning": true,
  "warningText": "Personen har fravær i denne periode"
}
```

#### GET `/api/TeamActivity/GetTeamActivityPersonPageNotification?activityId={id}&personId={personId}&isContactPerson={bool}&deviceId={deviceId}`
Get notification settings for an activity person.

---

### Matches

#### GET `/api/Match/GetMatchExtended?deviceId={deviceId}&matchId={matchId}&poolId={poolId}`
Full match details including venue, referee, kit colors, GPS coordinates.

**Response:**
```json
{
  "id": 430111,
  "round": 6,
  "poolId": 476348,
  "matchDate": "2026-03-08T00:00:00",
  "matchTime": "13:00",
  "homeTeamId": 734134,
  "homeTeamName": "AaB (2)",
  "awayTeamId": 733867,
  "awayTeamName": "LKB/VFB",
  "homeScore": null,
  "awayScore": null,
  "stadium": {
    "id": 848,
    "name": "AaB's Anlæg",
    "address": "Hornevej 2",
    "zip": "9220",
    "city": "Aalborg Øst",
    "latitude": 57.043410,
    "longitude": 10.019530,
    "isArtificialTurf": false,
    "imageList": [...]
  },
  "fieldName": "Bane 7 ny kunstgræs",
  "homeShirt": {"id": 7, "name": "Rød/Hvid", "hexValue": "#f51b1b/#ffffff"},
  "homeShorts": {"id": 12, "name": "Hvid/Rød", "hexValue": "#ffffff/#f51b1b"},
  "matchRefereeList": [
    {"personId": 300003, "personName": "Dommer Hansen", "refereeTypeId": 1, "refereeTypeName": "Dommer"}
  ],
  "shareLink": "http://www.dbujylland.dk/resultater/kamp/430111_476348",
  "iCalUrl": "webcal://ical.dbu.dk/Match.ashx?match=...",
  "hasMatchVideo": false,
  "allowMatchLiveScore": true
}
```

#### GET `/api/Match/GetMatchProgramTeam?deviceId={deviceId}&poolId={poolId}&teamId={teamId}`
Match program for a team in a pool — all matches with results.

**Response:** Array of:
```json
{
  "matchId": 430089,
  "poolId": 476348,
  "matchDate": "2025-12-03T00:00:00",
  "matchTime": "18:45",
  "homeTeamName": "AaB (2)",
  "awayTeamName": "TSV",
  "stadiumName": "AaB's Anlæg",
  "matchResult": "6-3",
  "isMatchPlayed": true
}
```

#### GET `/api/Match/GetMatchProgramLiveScoreUser?deviceId={deviceId}&userId={userId}`
Get live matches for a user.

#### GET `/api/Match/HasTeamCardAccess?deviceId={deviceId}&matchId={matchId}&poolId={poolId}&personId={personId}`
Check if person can manage team card.

---

### League Standings

#### GET `/api/PoolScore/GetPoolScore?DeviceId={deviceId}&PoolId={poolId}`
League table / standings.

**Response:** Array sorted by position:
```json
{
  "teamId": 736187,
  "teamName": "Team Østvendsyssel",
  "logoUrl": "...",
  "matches": 6,
  "point": 15,
  "score": 18,
  "scoreAgainst": 8,
  "position": 1
}
```

---

### Feed Endpoints

#### GET `/api/Feed/GetListPreTask?deviceId={deviceId}&personId={personId}`
Pre-activity tasks (e.g., KampKlar tasks before a match).

#### GET `/api/Feed/GetListPostTask?deviceId={deviceId}&personId={personId}`
Post-activity tasks.

#### GET `/api/Feed/GetListTask?userId={userId}&deviceId={deviceId}`
All pending tasks.

#### GET `/api/Feed/GetListFavoriteMatches?deviceId={deviceId}&personId={personId}`
Favorite team matches.

#### GET `/api/Feed/GetListBirthdays?deviceId={deviceId}&personId={personId}`
Upcoming birthdays in teams.

#### GET `/api/Feed/GetListNationalTeamMatches?deviceId={deviceId}`
National team upcoming matches.

#### GET `/api/Feed/GetListSystemMessage?personId={personId}&deviceVersion=6.10&platform=1&deviceId={deviceId}`
System messages.

#### GET `/api/Feed/GetListDelighters?deviceId={deviceId}&personId={personId}`
"Delighter" promotional content.

---

### Other Endpoints

#### GET `/api/News/GetFeedList?deviceId={deviceId}&userId={userId}`
News feed.

#### GET `/api/Message/GetUnReadMessageCount?deviceId={deviceId}&personId={personId}`
Unread message count.

#### GET `/api/Menu/GetMenuList?UserId={userId}&DeviceId={deviceId}`
Full app menu structure.

#### GET `/api/Union/GetUnion?id={id}&deviceId={deviceId}`
Union info (e.g., DBU Jylland = id 3).

#### GET `/api/Person/GetListGender?DeviceID={deviceId}`
Gender list for forms.

#### GET `/api/Condition/GetCurrentCondition?UserID={userId}&DeviceID={deviceId}`
Current pitch condition status.

---

## Endpoints — XML API (`appservice.dbu.dk`)

All XML endpoints use Basic Auth and `Content-Type: application/xml; charset=utf-8`.
POST bodies wrapped in `<?xml version="1.0" encoding="UTF-8" ?><Payload>...</Payload>`.

### Device Registration

#### POST `/UpdateDeviceData/xml`
Register/update device.

**Request:**
```xml
<Payload>
  <Token>HEX_PUSH_TOKEN</Token>
  <Name>iPhone15_2</Name>
  <Version>6.10</Version>
  <OS>26.3.1</OS>
  <PhoneId>UUID</PhoneId>
  <Device>100000</Device>
  <Platform>1</Platform>
  <IsNewInstalled>False</IsNewInstalled>
</Payload>
```

### Weather

#### POST `/GetWeather/xml`
Get weather for a match venue.

**Request:**
```xml
<Payload><Match>604671</Match><Pool>489985</Pool></Payload>
```

**Response:**
```xml
<Weather>
  <Temperature>5.8</Temperature>
  <WindSpeed>2.9</WindSpeed>
  <WindDirection>SSV</WindDirection>
  <Pressure>1000.7</Pressure>
  <Rain>0.0</Rain>
  <SunRise>2026-03-14T06:39:00</SunRise>
  <SunSet>2026-03-14T18:21:00</SunSet>
  <SymbolCode>04</SymbolCode>
</Weather>
```

### Team Card (Match Lineup)

#### POST `/GetMatchTeamCard/xml`
Get team lineup for a match.

**Request:**
```xml
<Payload>
  <Match>604671</Match>
  <Pool>489985</Pool>
  <Team>52</Team>
  <User>100001</User>
  <ClubGuid>00000000-0000-0000-0000-000000000000</ClubGuid>
</Payload>
```

**Response includes:** Player list with shirt numbers, substitutes, dispensations, profile images, min/max player counts.

#### POST `/GetMatchTeamCardFormation/xml`
Get formation for a match.

#### POST `/GetMatchTeamCardPlayerPerson/xml`
Get detailed player info for team card.

### Live Score

#### GET `/GetLiveScoreAndComment/{matchId}/{poolId}/{userId}/{type}/{param1}/{param2}/{personId}/xml`
Get live score events and comments. Returns event list with:
- Goals (Mål), own goals (Selvmål)
- Cards (Gult kort, Rødt kort)
- Substitutions (Udskiftning)
- Match periods (Kamp start, 1. halvleg slut, etc.)
- Penalty shootout events

#### GET `/GetLiveScoreInfo/{matchId}/{poolId}/{userId}/{personId}/xml`
Live score info.

### Other XML Endpoints

#### GET `/GetHOTeams/{personId}/xml`
Get KampKlar teams for a person.

#### GET `/GetHOActivityTaskList/{activityId}/xml`
Activity tasks.

#### GET `/GetHOCommentList/{activityId}/{personId}/{bool}/xml`
Activity comments.

#### POST `/GetHOActivityTaskPersonList/xml`
Task person list for an activity.

#### GET `/GetUserContent/{userId}/xml`
User content.

#### GET `/GetUserTypeList/{userId}/xml`
User type list (roles).

#### GET `/GetCountries/xml`
Country list.

#### GET `/GetTeamInfo/{teamId}/{poolId}/xml`
Team info in a pool.

#### GET `/GetPoolInfo/{poolId}/xml`
Pool/league info with rules and comments.

#### GET `/GetMatchRules/{rowId}/{bool}/xml`
Match rules link.

#### GET `/GetMatchWithPerson/{matchId}/{param}/{personId}/xml`
Match with person context.

#### GET `/GetMatchCheckApp/{matchId}/{deviceId}/{userId}/xml`
Match check status.

#### GET `/GetSharedInformation/{poolId}/{teamId}/xml`
Shared info for a team in a pool.

#### POST `/GetTeamBoardMessageList/xml`
Team board messages.

**Request:**
```xml
<Payload>
  <ClubId>445ca99b-d30c-4998-b540-38130c29b526</ClubId>
  <Team>126</Team>
  <User>100001</User>
</Payload>
```

#### POST `/GetSponsorBanners/xml`
Sponsor banner ads (called frequently).

#### POST `/GetHasAccessToMatchTeamCard/xml`
Check team card access.

#### POST `/GetUserNotificationMatch/xml`
Match notification preferences.

---

## Static Resources

- **Images:** `https://file.dbu.dk/images/...`
  - Club logos: `/images/club/{clubId}/{name}.png`
  - User photos: `/images/user//{userId}.jpg`
  - Stadium images: `/images/stadium/{id}/...`
  - Flags: `/images/flag//{countryId}.jpg`
- **iCal feeds:** `webcal://ical.dbu.dk/...`

---

## Notes for Integration Development

1. **Primary data source:** Use `PersonActivity/GetList` for the main activity feed — it returns cross-team data for a person.
2. **Polling:** The app makes many calls on launch; for HA integration, focus on `PersonActivity/GetList` and `TeamActivity/GetTeamActivityList` with reasonable polling intervals.
3. **Authentication flow:** Login → get `userId` + `personId` → use these in all subsequent calls. The Basic Auth header is always the same static app credential.
4. **Device registration:** The app registers devices via `UpdateDeviceData/xml` to get a `deviceId`. The integration may need to simulate this.
5. **Date format:** .NET ticks for `fromDate` parameter (e.g., `639089568000000000`). Standard ISO 8601 in responses.
6. **Sign-up status tracking** is the core "KampKlar" feature — knowing who's attending training/matches.
7. **The XML API has richer match/livescore data**, but the JSON API is cleaner and should be preferred where both exist.
