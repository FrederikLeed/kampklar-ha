# DBU Fodbold app - full reverse-engineering analysis

App: **Fodbold** (`dk.dbu.Fodbold`) version 6.16.2, Android. Built with **.NET / Xamarin**
(Second Screen Mobile framework, `SSMobile.*`). Analysis date 2026-09-15. Read-only throughout:
the package was decompiled and the live API was probed with the account's own credentials using
GET only. Nothing was written to DBU.

## How the analysis was done

1. Pulled the APK (`apkeep`, apk-pure), 86 MB, 3088 files.
2. The logic is not in the dex files. It is 180 .NET assemblies packed in
   `lib/arm64-v8a/libassemblies.arm64-v8a.blob.so` (Xamarin AssemblyStore, each assembly
   LZ4-compressed under an `XALZ` header). Extracted all 180 via the store descriptors.
3. The app itself is `DBU.Fodbold.Droid.dll`. Decompiled to C# with the ICSharpCode decompiler:
   2209 types, 13 MB of source.
4. Parsed the API layer into a structured catalogue: **359 unique endpoints across 46 controllers**,
   and **338 data classes with 2858 fields**.
5. Live-probed all 229 GET endpoints with the account and real IDs: **91 returned data**.

Working files: `/shared/kampklar-re/` (`src/` decompiled source, `endpoints.json`, `dtos.json`,
`enums.json`, `probe_results.json`, `endpoints_table.md`). The decompiled source is the authoritative
map; the live probe confirms what actually works and what real data comes back.

## Backends and authentication

Two backends, selected per call:

| Backend | Base URL | Format | Use |
|---|---|---|---|
| JSON API (`Lib.DbuWebApi`) | `https://dbuappwebapi.dbu.dk/api` | JSON | Everything modern (357 of 359 endpoints) |
| Legacy XML (`appservice.dbu.dk`) | `https://appservice.dbu.dk` | XML | A couple of legacy calls |

Test hosts also exist in the binary: `dbuappwebapitest.dbu.dk`, `mit2.dbu.dk`, `appservicetest.dbu.dk`.

**Auth is two-layer:**
- **App-level HTTP Basic** on every request: `Authorization: Basic AppService:!Fodbold!23` (static, baked in).
- **User identity by ID, not token.** `POST User/GetUserByCredentials` (JSON body `{UserName, Password}`,
  plus `deviceId` query) returns the `UserProfileModel` with `userId` and `personId`. Those IDs are then
  passed to every other call. There is no bearer token or session cookie; the app is trusted by the
  static Basic secret and simply sends the IDs. This is why the current Home Assistant integration works
  with username + password alone.

Common query params on most calls: `deviceId`, `platformId` (2 = Android), `appVersion`, and the relevant
`personId` / `userId` / `teamId` / `matchId` / `poolId` / `clubId`.

## Data model: activities are polymorphic

`PersonActivity/GetList?personId=&deviceId=` is the KampKlar feed. Each entry is an `ActivityList`
`{ Activity (object), ActivityDateTime, eType, ShowTeamAssignmentName, SortingIndex }`, and `eType`
selects the concrete shape of `Activity`:

| eType (ActivityType) | Activity payload class |
|---|---|
| Kamp (match) | `MatchActivity` |
| KampKlar (team activity, training) | `TeamActivity` |
| Dommerkamp (referee match) | `RefereeMatchActivity` |
| Dommerstaevne (referee indoor) | `RefereeIndoorActivity` |
| KlubAktivitet (club activity) | `ClubActivity` |
| Info | `ImageLinkDTO` |

`TeamActivity` (31 fields) is the rich one: `Id, Name, ClubId, ClubName, ClubLogoUrl, TeamId, TeamName,
TypeId, TypeName, HideSelection, ConfirmSelection, StartTime, EndTime, SubscriptionDeadline, MeetingTime,
MeetingPlace, StadiumText, Match, StadiumRound, SignupStatusId, SignupStatusName, IsConfirmed,
IsOpenForSignUp, PersonImageUrl, PersonContactId, PersonContactName, Subscribed, SubscribedText, Tasks,
RoleId, TeamAssignmentName`. `TypeId`: 1 Traening, 2 Kamp, 4 Staevne, 5 Traeningskamp, 7 DBU-Staevne.
`SignupStatusId`: null unanswered, 1 frameldt, 2 tilmeldt, 3 til raadighed, 4 udtaget. Which of those
an activity can reach depends on its mode, which only `SubscribedText` names ("8 udtaget" = the coach
picks a squad, "14 tilmeldte" = people sign up, and then 4 never appears). Per activity, not per team.

## Sign-up / cancel (the write path the integration is missing)

KampKlar attendance is written with:

```
POST TeamActivity/UpdateTeamActivityPerson?userId={userId}&deviceId={deviceId}&appversion={ver}
POST TeamActivity/InsertTeamActivityPerson    (same query, first response)
Body (KOTeamActivityPersonModel):
  { ActivityId, PersonId, SignUpStatusId, TeamPersonId?, Comment, IsPrivateComment, CreatedByTeamPerson }
```

Set `SignUpStatusId` to 2 to tilmeld, 1 to afmeld. `RevertTeamActivityPerson` clears it.
`GetTeamActivitySignUpTypeList` returns the allowed status list. This is exactly what issues #14 and #26
need for `kampklar.tilmeld` / `kampklar.afmeld` services. (These live under the head-office/KlubOffice area,
so writing may require the person to have the right role on the team; verify against a real signup before
shipping.)

## iCal calendar URLs (the fallback data source, issue #10 / #16)

`GetUserByCredentials` already returns three ready-made webcal feeds in the profile:
`RefCalendarUrl`, `MyTeamCalendarUrl`, `TeamActivityCalendarUrl` (host `ical.dbu.dk`). No extra API needed
for a calendar fallback; they come back with login.

## What the app can do (feature map by controller)

46 controllers. Grouped:

- **Identity/User/Person/Device** (53 endpoints): login, user profile, person search, gender/zip/country
  lookups, device registration and notification prefs, Didomi/Gemius consent flags.
- **Teams & Players** (47): team lists and members, player clubs, player certificates
  (spillercertifikat) request/approve/reject, bookings (disciplinary), practice matches.
- **Matches & Live score** (30): match programmes, results, team cards (lineups), and the full
  live-score reporting system (events, goals, cards) - the app can referee-report a match live.
- **Tournaments & venues** (15): pools, standings, rows, stadiums, statistics, national-team matches.
- **Clubs & KlubOffice** (58): club directory (1492 active clubs), club office/CMS admin, member and
  team-assignment requests, player certificate workflows, image-consent.
- **Messaging & notifications** (24): the person activity feed, push notifications, a message centre,
  mail to team members.
- **Content & app shell** (35): news, feed delighters, sponsor banners/advertising, marketing, the
  dynamic menu, help content, app settings, images, weather.
- **Referee & education** (40): referee development, questionnaires, pitch condition, laws of the game
  (football and futsal), courses, a 1921-item training-exercise library.
- **Head office (HO)** (3 top-level, plus the large HOTeamActivity block): team-activity administration
  (create/update activities, manage attendees, car-pooling, tasks, deposits, absence).

## Live probe: what returns real data without extra context

91 of 229 GET endpoints returned data with just the account and a handful of IDs. Highlights (sizes are
one live response): `Club/GetListActive` 1492 clubs (377 KB), `Exercise/GetListTraining` 1921 exercises
(1.2 MB), `Identity/GetCountryList` 252, `Identity/GetZipList` 1095 Danish postcodes,
`Booking/GetListBookingType` 30 disciplinary types, `Condition/GetCurrentCondition` (pitch conditions),
`App/GetAppSettings`, `Feed/GetListNationalTeamMatches`, `Match/GetMatchProgramPool`,
`MatchLiveScore/GetListMatchLiveScoreEvent`. The full status per endpoint is in
`endpoints_table.md` (Live column) and `probe_results.json`.

## Relevance to the Home Assistant integration

Already shipped (v0.2.1): `PersonActivity/GetList` -> next activity, next match, pending signups, calendar.

Clear next steps this analysis unlocks:
1. **Write services** (#14, #26): `kampklar.tilmeld` / `kampklar.afmeld` via
   `TeamActivity/UpdateTeamActivityPerson` with `SignUpStatusId` 2/1. Highest-value feature.
2. **iCal fallback** (#10, #16): the three webcal URLs are already in the login response - no new API.
3. **Richer sensors**: `SubscriptionDeadline`, `MeetingTime`/`MeetingPlace`, `Subscribed` count,
   `IsOpenForSignUp` are all in `TeamActivity` and already fetched; expose them.
4. **Handle all activity types**: referee matches (Dommerkamp), club activities and staevne all come
   through the same feed with different payloads. A referee/coach account would surface them.
5. **Team-wide view**: `TeamActivity/GetListTeamActivityTeamMemberPerson` gives who-is-attending per
   activity, for an attendance sensor (#24).

## MITM note

A live man-in-the-middle capture was not run, and would add little here: static decompilation already
gives the exact URL, verb, params and response type of all 359 endpoints, and the live probe confirmed 91
of them against production - far more than any one app session would exercise. MITM only shows the handful
of calls the app happens to make while you click around. The app uses .NET `HttpClient` (not OkHttp) with
the static Basic secret and no certificate pinning config in the manifest, so if a live capture is ever
wanted, mitmproxy with the CA trusted on a rooted device or an emulator would work; the blocker in this
environment is only that the emulator needs KVM (`/dev/kvm` is absent here). It is not needed to complete
the map.

## Identity/User/Person/Device

| Endpoint | Verb | Query params | Returns | Live (GET) |
|---|---|---|---|---|
| `Device/GetDevice` | GET | id | DeviceModel | 200 (125b) |
| `Device/GetDidomiCmpEnabled` | GET | deviceId | bool | 200 (4b) |
| `Device/GetGemiusEnabled` | GET | deviceId | bool | 200 (4b) |
| `Device/GetListTutorialUrl` | GET | deviceId, platformId, version | List<TutorialUrlModel> | 400 |
| `Device/InsertUpdateDevice` | POST(form) | deviceId | DBReturnStatus |  |
| `Device/UpdateDeviceAcceptNotification` | POST(form) | acceptnotification, deviceId | DBReturnStatus |  |
| `Identity/GetColorList` | GET | deviceId | List<ColorModel> | 200 (575b) |
| `Identity/GetCountryList` | GET | deviceId | List<CountryModel> | 200 (11988b) |
| `Identity/GetZipList` | GET | - | List<ZipModel> | 200 (37947b) |
| `Person/DeletePersonClubAssignment` | DELETE | deviceId, personClubAssignmentId, userId | DBReturnStatus |  |
| `Person/DeletePersonContact` | DELETE | deviceId, personId, playerPersonId | DBReturnStatus |  |
| `Person/DeletePersonProfileImage` | DELETE | DeviceID, PersonID | DBReturnStatus |  |
| `Person/DeletePersonTeamAssignment` | DELETE | deviceId, personTeamAssignmentId | DBReturnStatus |  |
| `Person/DeletePlayerContact` | DELETE | contactPersonId, deviceId, personId | DBReturnStatus |  |
| `Person/GetClubPersonByDBUId` | GET | clubId, dbuId, deviceId | PersonModel | 400 |
| `Person/GetConfirmDeletePersonClubAssignment` | GET | deviceId, personClubAssignmentId | DBReturnStatus | 200 (94b) |
| `Person/GetListGender` | GET | DeviceID | Response<List<PersonGender>> | 200 (73b) |
| `Person/GetListPersonClubAssignmentByClub` | GET | clubId, deviceId | List<PersonClubAssignmentModel> | 400 |
| `Person/GetListPersonContact` | GET | deviceId, personId | List<PersonModel> | 200 empty |
| `Person/GetListPersonPlayerContact` | GET | deviceId, personId | List<PersonModel> | 200 (300b) |
| `Person/GetListPersonTeamAssignmentByTeam` | GET | deviceId, rowId, teamId | List<PersonTeamAssignmentModel> | 200 empty |
| `Person/GetPassport` | GET | DeviceID, UserID | Response<Passport> | 200 (38b) |
| `Person/GetPersonClubAssignments` | GET | DeviceID, PersonID | Response<List<ClubAssignment>> | 200 empty |
| `Person/GetPersonClubRelationsDistinctClubs` | GET | DeviceID, PersonID | Response<List<ClubModel>> | 200 empty |
| `Person/GetPersonTeamAssignments` | GET | deviceId, includeKOTeam, personId | Response<List<TeamAssignment>> | 200 empty |
| `Person/GetProfileImg` | GET | DeviceID, PersonID | Response<string> | 204 |
| `Person/InsertPersonClubAssignmentRequest` | POST(form) | DeviceID, clubAssignmentId, clubId, personId | DBReturnStatus |  |
| `Person/InsertPersonContact` | POST(json) | deviceId, personId | DBReturnStatus |  |
| `Person/InsertPlayerContact` | POST(json) | deviceId, personId | DBReturnStatus |  |
| `Person/InsertTeamPersonInvite` | POST(form) | DeviceID, clubId, email, message, teamAssignmentId, teamId,  | DBReturnStatus |  |
| `Person/SendPersonPlayerContactInvite` | POST(json) | deviceId, emails, personId, userId | DBReturnStatus |  |
| `Person/UpdatePersonProfileImage` | POST(form) | DeviceID, PersonID | DBReturnStatus |  |
| `Person/UpdatePersonValidation` | POST(json) | deviceId, personId, typeId | DBReturnStatus<int> |  |
| `Person/UpdateSecondaryEmail` | POST(json) | deviceId, email, personId | DBReturnStatus |  |
| `PersonActivity/GetList` | GET | deviceId, personId | ServiceResult<ActivityList> | 200 (27529b) |
| `PersonActivity/GetListAll` | GET | deviceId, personId | ServiceResult<ActivityList> | 200 (39296b) |
| `User/CheckEmailExists` | POST(form) | email, role | DBReturnStatus |  |
| `User/DeleteUser` | POST(form) | deviceId, userId | DBReturnStatus |  |
| `User/DeleteUserTeam` | DELETE | deviceId, id, userId | DBReturnStatus |  |
| `User/GetListUserTeam` | GET | deviceId, userId, withArchived | List<UserTeamModel> | 200 (1852b) |
| `User/GetListUserType` | GET | deviceId, userId | List<UserTypeModel> | 200 (178b) |
| `User/GetUser` | GET | deviceId, userId | UserProfileModel | 200 (695b) |
| `User/GetUserByCredentials` | POST(json) | deviceId | DBReturnStatus<UserProfileModel> |  |
| `User/GetUserBySSO` | GET | deviceId | UserProfileModel | 204 |
| `User/GetUserTracking` | GET | deviceId, userId | UserTrackingDTO | 204 |
| `User/InsertUser` | POST(form) | deviceId | DBReturnStatus |  |
| `User/InsertUserTeam` | POST(form) | deviceId, poolId, teamId, userId | DBReturnStatus |  |
| `User/LogoutUser` | POST(json) | deviceId | DBReturnStatus |  |
| `User/ResetPwd` | GET | deviceId, identity | DBReturnStatus | 400 |
| `User/ShowPersonAddressChangeWarning` | POST(form) | address, deviceId, personId, zip | DBReturnStatus |  |
| `User/UpdateUser` | POST(form) | deviceId | DBReturnStatus |  |
| `User/UpdateUserPwd` | POST(json) | deviceId, userId | DBReturnStatus |  |
| `User/UpdateUserTeamPriority` | POST(form) | deviceId, id, priority, userId | DBReturnStatus |  |

## Teams & Players

| Endpoint | Verb | Query params | Returns | Live (GET) |
|---|---|---|---|---|
| `Booking/GetClubPlayerBooking` | GET | ClubId, DeviceID | Response<List<PlayerBooking>> | 200 empty |
| `Booking/GetListBookingPerson` | GET | - | Response<List<BookingPerson>> | 200 (89b) |
| `Booking/GetListBookingSpecification` | GET | - | Response<List<BookingSpecification>> | 200 (4908b) |
| `Booking/GetListBookingType` | GET | - | Response<List<BookingType>> | 200 (6220b) |
| `Booking/GetListBookingTypeCategory` | GET | - | Response<List<BookingTypeCategory>> | 200 (81b) |
| `Booking/GetListBookingVictim` | GET | - | Response<List<BookingVictim>> | 200 (272b) |
| `Booking/GetListPlayerBookingMisconduct` | GET | IsPlayer | Response<List<PlayerBookingMisconduct>> | 200 (6807b) |
| `Booking/GetPoolPlayerBooking` | GET | DeviceID, PoolId | Response<List<PlayerBooking>> | 500 |
| `Booking/GetTransferredPlayerBooking` | GET | DeviceId, GenderId | Response<List<PlayerBooking>> | 200 (8304b) |
| `Booking/InsertBooking` | POST(form) | DeviceID | DBReturnStatus |  |
| `Player/ApproveRejectPlayerCertificateRequest` | POST(form) | approve, deviceId, id, userId | DBReturnStatus |  |
| `Player/GetIsNationalPlayer` | GET | deviceId, personId | bool | 200 (5b) |
| `Player/GetListPlayerMatch` | GET | assists, deviceId, goals, hasMOM, hasRed, hasYellow, opponen | List<PlayerMatchModel> | 200 (4065b) |
| `Player/GetListPlayerNationalMatch` | GET | deviceId, personId, teamtypeId, yearFrom, yearTo | List<PlayerNationalMatchModel> | 200 empty |
| `Player/GetPlayerCertificateAdditional` | GET | DeviceID, PersonID | Response<List<AdditionalPlayerCertificat | 200 empty |
| `Player/GetPlayerCertificateList` | GET | DeviceID, PersonID | Response<List<ClubModel>> | 200 empty |
| `Player/GetPlayerCertificateRequestList` | GET | deviceId, personId | List<DBU.Fodbold.BLL.DAL.AppService.Mode | 200 empty |
| `Player/GetPlayerClubSportsType` | GET | DeviceID, MemberId | Response<List<SportsType>> | 500 |
| `Player/GetPlayerClubs` | GET | DeviceID, PersonID | Response<List<ClubMemberModel>> | 200 empty |
| `Player/GetPlayerMatchSearchFilter` | GET | deviceId, personId | PlayerMatchSearchFilterModel | 200 (1594b) |
| `Player/ResignPlayerClub` | POST(form) | Comment, DeviceID, KOID, MemberId, PersonID, SportId | DBReturnStatus |  |
| `PracticeMatch/GetClubMatchTime` | GET | clubId, deviceId, teamId | List<MatchTime> | 400 |
| `PracticeMatch/GetInitial` | GET | deviceId, personId | PracticeMatchInit | 200 (94631b) |
| `PracticeMatch/GetList` | GET | deviceId, userId | List<PracticeMatchWish> | 200 empty |
| `PracticeMatch/GetListPracticeMatchDivision` | GET | deviceId, genderId, unionId | List<DivisionModel> | 200 (460b) |
| `PracticeMatch/GetListPracticeMatchFieldType` | GET | deviceId, divisionId, genderId, levelId, unionId | List<FieldType> | 200 empty |
| `PracticeMatch/GetListPracticeMatchLevel` | GET | deviceId, divisionId, genderId, unionId | List<Level> | 200 empty |
| `PracticeMatch/GetListRefereeSettlementType` | GET | deviceId | List<RefereeSettlementType> | 200 (154b) |
| `PracticeMatch/GetListRefereeType` | GET | clubId, deviceId, divisionId, genderId, levelId, teamId, uni | List<RefereeType> | 400 |
| `PracticeMatch/InsertWish` | POST(form) | deviceId | DBReturnStatus |  |
| `Team/GetKOTeam` | GET | clubId, deviceId, id | KOTeam | 500 |
| `Team/GetListTeamAssignment` | GET | clubId, deviceId | List<Assignment> | 400 |
| `Team/GetListTeamByPool` | GET | deviceId, poolId | List<TeamModel> | 200 (2764b) |
| `Team/GetListTeamByRow` | GET | deviceId, rowId | List<TeamModel> | 200 empty |
| `Team/GetListTeamTournamentByPerson` | GET | deviceId, personId | List<TeamTournamentModel> | 200 empty |
| `Team/GetListTeamsByClub` | GET | clubId, deviceId | List<KOTeam> | 200 (8182b) |
| `Team/GetTeam` | GET | deviceId, rowId, teamId | TeamExtendedModel | 204 |
| `TeamMember/DeleteTeamMember` | DELETE | clubId, deviceId, memberId, memberPersonId, removeFromActivi | DBReturnStatus |  |
| `TeamMember/DeleteTeamMemberGroup` | DELETE | deviceId, id | DBReturnStatus |  |
| `TeamMember/GetMemberSearch` | GET | birthYearFrom, birthYearTo, clubId, departmentId, deviceId,  | List<MemberModel> | 500 |
| `TeamMember/GetTeamMemberGroupList` | GET | clubId, deviceId, teamId | List<TeamMemberGroupModel> | 200 empty |
| `TeamMember/GetTeamMemberList` | GET | clubId, deviceId, teamId | List<TeamMemberModel> | 200 empty |
| `TeamMember/InsertTeamMember` | POST(json) | clubId, deviceId, memberClubId, memberId, memberPersonId, te | DBReturnStatus |  |
| `TeamMember/InsertTeamMemberGroup` | POST(json) | deviceId | DBReturnStatus |  |
| `TeamMember/UpdateTeamMemberGroup` | POST(json) | deviceId | DBReturnStatus |  |
| `TeamMember/UpdateTeamMemberShirtNumber` | POST(json) | clubId, deviceId, personId, shirtNumber, teamId | DBReturnStatus |  |
| `TeamMember/UpdateTeamMemberTeamMemberGroup` | POST(json) | clubId, deviceId, groupId, personId, teamId, userId | DBReturnStatus |  |

## Matches & Live score

| Endpoint | Verb | Query params | Returns | Live (GET) |
|---|---|---|---|---|
| `Match/GetListAvailableLiveScore` | GET | deviceId, includeTeamCooperation, personId | List<MatchProgramExtendedModel> | 200 empty |
| `Match/GetListAvailableMatchResult` | GET | deviceId, includeTeamCooperation, personId | List<MatchProgramModel> | 200 (22332b) |
| `Match/GetListAvailableMatchTeamCard` | GET | deviceId, includeTeamCooperation, personId | List<MatchProgramModel> | 200 empty |
| `Match/GetListMatchVideo` | GET | deviceId, matchId, poolId | List<MatchVideoModel> | 200 empty |
| `Match/GetMatch` | GET | deviceId, matchId, poolId | ServiceResult<DBU.Fodbold.BLL.DAL.AppSer | 204 |
| `Match/GetMatchExtended` | GET | deviceId, matchId, poolId | ServiceResult<MatchExtended> | 204 |
| `Match/GetMatchProgramIsLive` | GET | clubName, division, gender, union, userId | ServiceResult<MatchProgramExtendedDTO> | 200 empty |
| `Match/GetMatchProgramLiveScoreUser` | GET | deviceId, userId | ServiceResult<MatchProgramLiveScoreDTO> | 200 empty |
| `Match/GetMatchProgramLocation` | GET | days, deviceId, distance, divisionGroup, gender, latitude, l | ServiceResult<MatchProgramExtendedDTO> | 200 empty |
| `Match/GetMatchProgramPool` | GET | deviceId, poolId | ServiceResult<MatchProgramDTO> | 200 (39864b) |
| `Match/GetMatchProgramStadium` | GET | deviceId, endDate, stadiumId, startDate | ServiceResult<MatchProgramExtendedDTO> | 500 |
| `Match/GetMatchProgramTeam` | GET | deviceId, poolId, teamId | ServiceResult<MatchProgramDTO> | 200 empty |
| `Match/GetMatchProgramUser` | GET | deviceId, endDate, startDate, type, userId | ServiceResult<MatchProgramExtendedDTO> | 500 |
| `Match/HasLiveScoreAccess` | GET | deviceId, matchId, personId, poolId | ServiceResult<MatchAssignment> | 500 |
| `Match/HasTeamCardAccess` | GET | deviceId, matchId, personId, poolId | ServiceResult<MatchAssignment> | 500 |
| `MatchLiveScore/DeleteMatchLiveScoreByGuids` | DELETE | deviceId, userId | DBReturnStatus |  |
| `MatchLiveScore/DeleteMatchLiveScoreById` | DELETE | deviceId, id, userId | DBReturnStatus |  |
| `MatchLiveScore/DeleteMatchLiveScoreByMatch` | DELETE | deviceId, matchId, poolId | DBReturnStatus |  |
| `MatchLiveScore/DeleteMatchLiveScoreMoM` | DELETE | deviceId, matchId, poolId, teamId, userId | DBReturnStatus |  |
| `MatchLiveScore/DeleteMatchLiveScorePerson` | DELETE | deviceId, matchId, poolId | DBReturnStatus |  |
| `MatchLiveScore/GetListMatchLiveScore` | GET | deviceId, isReferee, matchId, poolId, userId | List<MatchLiveScoreModel> | 500 |
| `MatchLiveScore/GetListMatchLiveScoreEvent` | GET | deviceId | List<MatchLiveScoreEventModel> | 200 (3288b) |
| `MatchLiveScore/GetMatchLiveScoreData` | GET | deviceId, matchId, poolId, userId | MatchLiveScoreDataModel | 500 |
| `MatchLiveScore/InsertMatchLiveScore` | POST(form) | deviceId, isReferee, userId | DBReturnStatus |  |
| `MatchLiveScore/InsertMatchLiveScoreList` | POST(form) | deviceId | DBReturnStatus<List<(Guid, int)>> |  |
| `MatchLiveScore/InsertMatchLiveScoreMoM` | POST(form) | deviceId, matchId, personId, poolId, teamId, userId | DBReturnStatus |  |
| `MatchLiveScore/InsertMatchLiveScorePerson` | POST(form) | deviceId, extratime, halftime, matchId, ordinary, poolId, us | DBReturnStatus |  |
| `MatchLiveScore/UpdateMatchLiveScore` | POST(form) | deviceId, isReferee, userId | DBReturnStatus |  |
| `MatchTeamCard/GetListMatchTeamCardWarning` | GET | deviceId, matchId, poolId, teamId | List<MatchTeamCardWarningModel> | 500 |
| `MatchTeamCard/SendTeamCardAsMail` | POST(form) | deviceId, matchId, personId, poolId | DBReturnStatus |  |

## Tournaments & venues

| Endpoint | Verb | Query params | Returns | Live (GET) |
|---|---|---|---|---|
| `NationalTeam/GetListTeamType` | GET | deviceId, personId | List<TeamType> | 200 (389b) |
| `Pool/GetListPools` | GET | deviceId, rowId | List<PoolBaseModel> | 500 |
| `Pool/GetPool` | GET | deviceId, id | PoolModel | 500 |
| `Row/GetListRowGameRules` | GET | deviceId, isPublic, rowId | List<RowGameRulesModel> | 200 empty |
| `Row/GetListRowGender` | GET | deviceId | List<PersonGender> | 200 (91b) |
| `Row/GetListRows` | GET | area, deviceId, divisionId, genderId, unionId, year | List<RowModel> | 200 (17860b) |
| `Row/GetListSeason` | GET | deviceId | List<SeasonModel> | 200 (1361b) |
| `Stadium/GetListByClub` | GET | clubId, deviceId | List<StadiumModel> | 400 |
| `Stadium/GetListKOFieldsByStadiumClub` | GET | clubId, deviceId, stadiumId | List<KOField> | 400 |
| `Stadium/GetListStadiumSearch` | GET | deviceId, name, zipFrom, zipTo | List<StadiumModel> | 200 (920319b) |
| `Stadium/GetStadiumImages` | GET | stadium | List<StadiumImageModel> | 200 (86b) |
| `Statistic/GetListElitePlayerStatistic` | GET | poolId | PlayerEliteStatisticModel | 200 (41b) |
| `Statistic/GetListPlayerStatistic` | GET | deviceId, poolId, teamId | List<PlayerStatisticModel> | 200 empty |
| `Statistic/GetRefereeStatistic` | GET | deviceId, personId, season | RefereeStatisticModel | 200 (208b) |
| `Tournament/GetListDivision` | GET | - | List<DivisionModel> | 200 (920b) |

## Clubs & KlubOffice

| Endpoint | Verb | Query params | Returns | Live (GET) |
|---|---|---|---|---|
| `Card/DeleteCompanySharePerson` | DELETE | appVersion, deviceId, id, platformId | DBReturnStatus |  |
| `Card/GetAllCards` | GET | - | Response<List<Card>> | 404 |
| `Card/GetCardDescription` | GET | CardID, DeviceID | Response<Description> | 404 |
| `Card/GetCards` | GET | DeviceID, PageID | Response<List<Card>> | 404 |
| `Card/GetListDBUCardSponsor` | GET | cardId, deviceId, isCardList, personId | ServiceResult<ClubCardSponsorDTO> | 200 empty |
| `Card/UpdateCompanySharePerson` | POST(json) | appVersion, deviceId, id, platformId, username | DBReturnStatus |  |
| `Club/GetClub` | GET | clubId, deviceId | ClubExtendedModel | 400 |
| `Club/GetClubCoopList` | GET | clubId, teamId | List<ClubModel> | 200 (241b) |
| `Club/GetKOClub` | GET | clubId, deviceId | KOClub | 200 (126b) |
| `Club/GetKOClubDepartmentList` | GET | clubId, sportId | List<KOClubDepartment> | 200 empty |
| `Club/GetKOClubTeamList` | GET | clubId, sportId | List<KOClubTeam> | 200 empty |
| `Club/GetListActive` | GET | deviceId | List<ClubModel> | 200 (377491b) |
| `Club/GetListByUnion` | GET | deviceId, unionId | List<ClubModel> | 200 (214125b) |
| `Club/GetListClubAssignmentByKOClub` | GET | clubId, deviceId | List<AssignmentModel> | 200 (2311b) |
| `Club/GetListClubSearch` | GET | deviceId, name | List<ClubModel> | 400 |
| `Club/GetListClubTeam` | GET | clubId, deviceId | List<ClubTeamModel> | 400 |
| `Club/GetListSportByKOClub` | GET | clubId, deviceId | List<SportsType> | 200 (180b) |
| `Club/GetListUnionRelatedClubAssignment` | GET | clubAssignmentId, clubId, deviceId | List<AssignmentModel> | 200 (606b) |
| `ImageAccept/GetDisplayPersonClubImageAcceptClubType` | GET | DeviceID, PersonID | Response<bool> | 200 (5b) |
| `ImageAccept/GetPersonClubImageAccept` | GET | DeviceID, PersonID | Response<List<ClubImageAccept>> | 200 empty |
| `ImageAccept/GetPersonClubImages` | GET | DeviceID, PersonID | Response<List<ClubImage>> | 200 empty |
| `ImageAccept/SavePersonClubImageAccept` | POST(form) | DeviceID, HasAccepted, PersonID, SystemID, TypeID | DBReturnStatus |  |
| `KlubOffice/ApproveClubAssignmentRequest` | POST(form) | deviceId, id, userId | DBReturnStatus |  |
| `KlubOffice/ApproveNewMemberRequest` | POST(form) | appversion, deviceId | DBReturnStatus |  |
| `KlubOffice/ApprovePlayerCertificateRequest` | POST(form) | appversion, deviceId | DBReturnStatus |  |
| `KlubOffice/ApproveResignMemberRequest` | POST(form) | deviceId | DBReturnStatus |  |
| `KlubOffice/ApproveTeamAssignmentRequest` | POST(json) | clubAssignmentId, clubId, deviceId, id, userId | DBReturnStatus |  |
| `KlubOffice/CreatePracticeMatch` | POST(form) | clubId, deviceId | DBReturnStatus |  |
| `KlubOffice/GetClubAssignmentRequest` | GET | deviceId, id | ClubAssignmentRequestModel | 500 |
| `KlubOffice/GetListClubAccess` | GET | deviceId, userId | List<ClubAccessModel> | 200 empty |
| `KlubOffice/GetListClubAssignmentRequest` | GET | clubId, deviceId, statusId | List<ClubAssignmentRequestModel> | 200 empty |
| `KlubOffice/GetListClubAssignmentRequestStatus` | GET | deviceId | List<RequestStatusModel> | 200 (92b) |
| `KlubOffice/GetListMatchMovementRequest` | GET | clubId, deviceId | List<MatchMovementRequestModel> | 400 |
| `KlubOffice/GetListMemberByBirthDate` | GET | birthdate, clubId, deviceId, fromResignMember, sportId | List<MemberModel> | 500 |
| `KlubOffice/GetListMenu` | GET | clubId, deviceId, userId | List<Menu> | 500 |
| `KlubOffice/GetListNewMemberRequest` | GET | clubId, departmentId, deviceId, sportId, statusId | List<NewMemberRequestModel> | 200 empty |
| `KlubOffice/GetListNewMemberRequestStatus` | GET | deviceId | List<RequestStatusModel> | 200 (92b) |
| `KlubOffice/GetListPlayerCertificateAdditionalPermission` | GET | clubId, deviceId, statusId | List<PlayerCertificateAdditionalPermissi | 400 |
| `KlubOffice/GetListPlayerCertificateAdditionalPermissionStatus` | GET | deviceId | List<RequestStatusModel> | 200 (118b) |
| `KlubOffice/GetListPlayerCertificateRequest` | GET | clubId, dateFrom, dateTo, deviceId, statusId | List<DBU.Fodbold.BLL.DAL.AppService.Mode | 400 |
| `KlubOffice/GetListPlayerCertificateRequestStatus` | GET | deviceId | List<RequestStatusModel> | 200 (350b) |
| `KlubOffice/GetListPracticeMatchRequest` | GET | clubId, dateFrom, dateTo, deviceId | List<PracticeMatchRequestModel> | 400 |
| `KlubOffice/GetListResignMemberRequest` | GET | clubId, deviceId, sportId, statusId | List<ResignMemberRequestModel> | 200 empty |
| `KlubOffice/GetListResignMemberRequestStatus` | GET | deviceId | List<RequestStatusModel> | 200 (92b) |
| `KlubOffice/GetListTeamAssignmentRequest` | GET | clubId, deviceId, statusId | List<TeamAssignmentRequestModel> | 200 (5989b) |
| `KlubOffice/GetListTeamAssignmentRequestStatus` | GET | deviceId | List<RequestStatusModel> | 200 (92b) |
| `KlubOffice/GetListTemplateText` | GET | clubId, deviceId, typeId | List<TemplateTextModel> | 200 empty |
| `KlubOffice/GetNewMemberMailRecievers` | GET | clubId, deviceId, teamId | MailRecieversModel | 400 |
| `KlubOffice/GetQuestionnaireClubPlayerCertificateRequest` | GET | birthdate, deviceId | DBReturnStatus | 200 (108b) |
| `KlubOffice/GetResignMemberMailRecievers` | GET | clubId, deviceId, memberId, sportId | MailRecieversModel | 200 (164821b) |
| `KlubOffice/GetTeamAssignmentRequest` | GET | clubId, deviceId, id | TeamAssignmentRequestModel | 500 |
| `KlubOffice/GetTemplateTextBody` | GET | clubId, deviceId, templateTextId | string | 200 empty |
| `KlubOffice/InsertNewMemberRequestQuestionnaire` | POST(form) | deviceId, newmemberId, userId | DBReturnStatus |  |
| `KlubOffice/RejectClubAssignmentRequest` | POST(json) | deviceId, id, userId | DBReturnStatus |  |
| `KlubOffice/RejectPlayerCertificateRequest` | POST(form) | appversion, deviceId | DBReturnStatus |  |
| `KlubOffice/RejectPracticeMatch` | POST(form) | clubId, deviceId | DBReturnStatus |  |
| `KlubOffice/RejectTeamAssignmentRequest` | POST(json) | deviceId, id, userId | DBReturnStatus |  |
| `KlubOffice/UpdateClubAccessSelected` | POST(form) | deviceId, systemAccountId, userId | DBReturnStatus |  |

## Messaging & notifications

| Endpoint | Verb | Query params | Returns | Live (GET) |
|---|---|---|---|---|
| `Communication/DeleteThread` | POST(json) | deviceId, threadId | DBReturnStatus |  |
| `Communication/GetRefereeUnionList` | GET | deviceId, personId | List<UnionBaseModel> | 500 |
| `Communication/GetThreadList` | GET | deviceId, personId | List<ThreadModel> | 200 empty |
| `Communication/GetThreadMessageList` | GET | deviceId, personId, threadId | List<ThreadMessageModel> | 200 empty |
| `Communication/InsertThread` | POST(form) | deviceId | DBReturnStatus |  |
| `Communication/InsertThreadMessage` | POST(form) | deviceId | DBReturnStatus |  |
| `Message/DeleteNotificationSettingCommunication` | DELETE | deviceId, userSettingId | DBReturnStatus |  |
| `Message/GetMessage` | GET | deviceId, id | MessageModel | 204 |
| `Message/GetMessageInboxList` | GET | dateFrom, dateTo, deviceId, notificationSettingId, personId | List<MessageModel> | 200 (47808b) |
| `Message/GetMessageList` | GET | deviceId, isArchived, numberOfMessages, personId | List<MessageModel> | 200 empty |
| `Message/GetMessageSentList` | GET | deviceId, numberOfMessages, personId | List<MessageSentModel> | 200 empty |
| `Message/GetMessageSetting` | GET | deviceId, userId | MessageSetting | 200 (1138b) |
| `Message/GetMessageSettingHOTeamList` | GET | clubId, deviceId, teamId, userId | MessageSettingHOTeamMessage | 200 (5200b) |
| `Message/GetNotificationSettingList` | GET | deviceId, notificationSettingId, userId | NotificationSetting | 200 (10780b) |
| `Message/GetUnReadMessageCount` | GET | deviceId, personId | ServiceResult<int> | 200 empty |
| `Message/InsertNotificationSettingCommunication` | POST(form) | communicationTypeId, deviceId, id, userId | DBReturnStatus |  |
| `Message/UpdateHOTeamOnlyMessageOnSignUp` | POST(form) | clubId, deviceId, isChecked, teamId, userId | DBReturnStatus |  |
| `Message/UpdateMessageList` | POST(form) | archived | DBReturnStatus |  |
| `Message/UpdateMessageSettingExerciseDivision` | POST(form) | deviceId, exerciseDivisionId, isChecked, userId | DBReturnStatus |  |
| `Message/UpdateMessageSettingHOTeamType` | POST(form) | clubId, deviceId, isChecked, messageTypeId, teamId, userId | DBReturnStatus |  |
| `Notification/GetListNotificationTeam` | GET | deviceId, userId | List<NotificationTeamModel> | 200 (452b) |
| `Notification/GetNotificationMatch` | GET | deviceId, matchId, poolId, userId | NotificationMatchModel | 204 |
| `Notification/InsertUpdateNotificationMatch` | POST(form) | deviceId, livescore, matchId, poolId, userId | DBReturnStatus |  |
| `Notification/InsertUpdateNotificationTeam` | POST(form) | changes, deviceId, entirePool, livescore, poolId, result, st | DBReturnStatus |  |

## Content & app shell

| Endpoint | Verb | Query params | Returns | Live (GET) |
|---|---|---|---|---|
| `Advertising/GetListBanner` | GET | clubId, deviceId, genderId, rowId, teamTypeId, typename, use | List<BannerModel> | 400 |
| `Advertising/GetListLocation` | GET | deviceId | List<LocationModel> | 200 empty |
| `App/GetAppSettings` | GET | deviceId | AppSettingsModel | 200 (684b) |
| `App/GetOperationStatuses` | GET | - | Response<List<OperationStatus>> | 200 (200b) |
| `Feed/GetListBirthdays` | GET | deviceId, personId | ServiceResult<BirthDay> | 200 empty |
| `Feed/GetListDelighters` | GET | deviceId, personId | ServiceResult<Delighter> | 200 (865b) |
| `Feed/GetListFavoriteMatches` | GET | deviceId, personId | ServiceResult<FavoriteMatch> | 200 empty |
| `Feed/GetListNationalTeamMatches` | GET | deviceId | ServiceResult<NationalTeamMatch> | 200 (6148b) |
| `Feed/GetListPostTask` | GET | deviceId, personId | ServiceResult<DBU.Fodbold.BLL.DAL.AppSer | 200 empty |
| `Feed/GetListPreTask` | GET | deviceId, personId | ServiceResult<DBU.Fodbold.BLL.DAL.AppSer | 200 empty |
| `Feed/GetListSystemMessage` | GET | deviceId, deviceVersion, personId, platform | ServiceResult<SystemMessageDTO> | 400 |
| `Feed/GetListTask` | GET | deviceId, userId | ServiceResult<ImageTile> | 200 empty |
| `Marketing/GetListMarketingInterest` | GET | deviceId, personId | List<MarketingInterestModel> | 200 empty |
| `Marketing/GetMarketingConsent` | GET | deviceId, personId | MarketingConsentModel | 204 |
| `Marketing/UpdateMarketingConsent` | POST(form) | consentId, deviceId, hasConsent, personId | DBReturnStatus |  |
| `Marketing/UpdateMarketingInterest` | POST(form) | deviceId, interestId, isSubscribed, personId | DBReturnStatus |  |
| `Menu/DeleteUserMenu` | DELETE | menuId, userId | ServiceResult<DBReturnStatus> |  |
| `Menu/GetFavoriteList` | GET | deviceId, showAll, userId | Response<List<MenuUser>> | 200 empty |
| `Menu/GetMenuList` | GET | DeviceId, UserId | Response<List<Menu>> | 200 empty |
| `Menu/GetUserMenuMainItem` | GET | deviceId, userId | Menu | 200 (301b) |
| `Menu/InsertUserMenu` | POST(form) | menuId, priority, userId | ServiceResult<DBReturnStatus> |  |
| `Menu/UpdateUserMenu` | POST(form) | menuId, priority, userId | ServiceResult<DBReturnStatus> |  |
| `Menu/UpdateUserMenuMainItem` | POST(form) | deviceId, menuId, userId | DBReturnStatus |  |
| `News/DeleteFavorite` | POST(form) | deviceId, unionId, userId | DBReturnStatus |  |
| `News/Get` | GET | dbuId, deviceId | ServiceResult<NewsItemModel> | 400 |
| `News/GetFeedList` | GET | deviceId, latitude, longitude, userId | ServiceResult<NewsModel> | 200 (1236b) |
| `News/GetList` | GET | deviceId, union | ServiceResult<NewsModel> | 200 empty |
| `News/GetListFavorite` | GET | deviceId, userId | ServiceResult<FavoriteNewsModel> | 200 empty |
| `News/GetListNewsUnion` | GET | deviceId | ServiceResult<NewsUnionModel> | 200 (606b) |
| `News/InsertUpdateFavorite` | POST(form) | deviceId, notification, unionId, userId | DBReturnStatus |  |
| `Page/GetListPageAds` | GET | deviceId, pagename | List<PageAdsModel> | 400 |
| `Page/GetPageHeader` | GET | DeviceId, KOClubId, KOTeamId, MatchId, PageName, PersonId, P | ServiceResult<PageHeaderDTO> | 400 |
| `Url/GetShareImageMatch` | GET | deviceId, matchId, poolId | DBReturnStatus | 200 (120b) |
| `Url/GetShareImagePoolPosition` | GET | deviceId, poolId, teamId, unionId | DBReturnStatus | 200 (133b) |
| `Weather/GetWeather` | GET | DateTime, Zip | ServiceResult<WeatherDTO> | 404 |

## Referee & education

| Endpoint | Verb | Query params | Returns | Live (GET) |
|---|---|---|---|---|
| `Condition/GetCurrentCondition` | GET | DeviceID, UserID | Response<Condition> | 200 (51546b) |
| `Condition/GetCurrentEnglishCondition` | GET | DeviceID, UserID | Response<Condition> | 200 (207b) |
| `Condition/SaveUserConditionRead` | POST(form) | ConditionID, DeviceID, SystemID, UserID | DBReturnStatus |  |
| `Condition/SendConditionToPerson` | POST(form) | DeviceID, PersonID | DBReturnStatus |  |
| `Course/GetCoachLicenses` | GET | deviceId, personId | List<CoachLicenseModel> | 404 |
| `Course/GetCourseLicenseMaintenance` | GET | deviceId, personId, typeId | ServiceResult<CourseLicenseMaintenanceMo | 500 |
| `Course/GetListCoachLicense` | GET | deviceId, personId | ServiceResult<CoachLicenseModel> | 200 empty |
| `Course/GetListCourseCompleted` | GET | deviceId, personId | ServiceResult<CourseModel> | 200 empty |
| `Course/GetListCourseManagerCourse` | GET | deviceId, personId | ServiceResult<CourseExtendedModel> | 200 empty |
| `Course/GetListCourseMember` | GET | courseDateId, courseId, deviceId | ServiceResult<CourseMemberModel> | 200 empty |
| `Course/UpdateCourseMemberArrival` | POST(form) | arrived, courseDateId, courseMemberId, deviceId, userId | DBReturnStatus |  |
| `Exercise/DeleteFavoriteExercise` | POST(form) | deviceId, exerciseId, userId | DBReturnStatus |  |
| `Exercise/DeleteFavoriteTraining` | POST(form) | deviceId, trainingId, userId | DBReturnStatus |  |
| `Exercise/DeleteTraining` | POST(form) | deviceId, id, userId | DBReturnStatus |  |
| `Exercise/DeleteTrainingExercise` | POST(form) | deviceId, exerciseId, trainingId | DBReturnStatus |  |
| `Exercise/GetExercise` | GET | deviceId, id, userId | ServiceResult<ExerciseDTO> | 500 |
| `Exercise/GetListExercise` | GET | deviceId, divisionId, name, sourceId, themeId, underThemeId, | ServiceResult<ExerciseDTO> | 200 (962258b) |
| `Exercise/GetListExerciseDivision` | GET | - | ServiceResult<ExerciseDivision> | 200 (356b) |
| `Exercise/GetListOfUsersExerciseTraining` | GET | deviceId, sourceId, userId | ServiceResult<UserExerciseTrainingDTO> | 200 empty |
| `Exercise/GetListTheme` | GET | - | ServiceResult<ExerciseThemeDTO> | 200 (166b) |
| `Exercise/GetListTraining` | GET | deviceId, divisionId, name, themeId, underThemeId, userId | ServiceResult<ExerciseTrainingDTO> | 200 (1200237b) |
| `Exercise/GetListUnderTheme` | GET | - | ServiceResult<ExerciseSubThemeDTO> | 200 (613b) |
| `Exercise/GetTraining` | GET | deviceId, id, userId | ServiceResult<ExerciseTrainingDTO> | 500 |
| `Exercise/InsertFavoriteExercise` | POST(form) | deviceId, exerciseId, userId | DBReturnStatus |  |
| `Exercise/InsertFavoriteTraining` | POST(form) | deviceId, trainingId, userId | DBReturnStatus |  |
| `Exercise/InsertTraining` | POST(form) | deviceId, exerciseDivisionId, name, themeId, underThemeId, u | DBReturnStatus |  |
| `Exercise/InsertTrainingExercise` | POST(form) | deviceId, exerciseId, priority, trainingId | DBReturnStatus |  |
| `Exercise/UpdateTraining` | POST(form) | deviceId, exerciseDivisionId, id, name, themeId, underThemeI | DBReturnStatus |  |
| `Exercise/UpdateTrainingExercisePriority` | POST(form) | deviceId, id, priority | DBReturnStatus |  |
| `Questionnaire/GetNextQuestion` | GET | answeroptionId, deviceId, questionId, questionnaireId | QuestionModel | 500 |
| `Questionnaire/GetQuestionnaire` | GET | deviceId, id | QuestionnaireModel | 500 |
| `Referee/DeleteRefereeMatchSelect` | POST(form) | deviceId, matchId, personId, poolId, userId | DBReturnStatus |  |
| `Referee/GetInitialRefereeMatchDeleteCheck` | GET | deviceId, matchId, personId, poolId | DBReturnStatus | 200 (149b) |
| `Referee/GetInitialRefereeMatchSelect` | GET | deviceId, personId | Response<RefereeMatchSelectInitial> | 500 |
| `Referee/GetInitialRefereeMatchSelectCheck` | GET | deviceId, matchId, personId, poolId | DBReturnStatus | 500 |
| `Referee/GetListRefereeMatchSelectSearch` | GET | dateFrom, dateTo, deviceId, divisionId, genderId, maxDistanc | Response<List<RefereeMatchSelect>> | 500 |
| `Referee/InsertRefereeMatchSelect` | POST(form) | deviceId, hasAbsence, isAccessible, matchId, personId, poolI | DBReturnStatus |  |
| `RefereeDevelopment/GetRefereeDevelopmentForm` | GET | deviceId, matchId, personId, poolId | DBU.Fodbold.BLL.DAL.AppService.Models.Re | 200 (3769b) |
| `RefereeDevelopment/InsertRefereeDevelopmentForm` | POST(form) | deviceId | DBReturnStatus |  |
| `RefereeDevelopment/IsRefereeDevelopmentFormCompleted` | GET | deviceId, matchId, poolId | DBReturnStatus | 200 (73b) |

## Head office (HO)

| Endpoint | Verb | Query params | Returns | Live (GET) |
|---|---|---|---|---|
| `Union/GetListUnion` | GET | deviceId | List<UnionBaseModel> | 200 (228b) |
| `Union/GetListUnionContact` | GET | deviceId | List<UnionModel> | 200 (3081b) |
| `Union/GetUnion` | GET | deviceId, id | UnionModel | 500 |

## Other

| Endpoint | Verb | Query params | Returns | Live (GET) |
|---|---|---|---|---|
| `?` | DELETE | appversion, deviceId, userId | DBReturnStatus |  |
| `?` | POST(json) | deviceId, userId | DBReturnStatus |  |
| `?` | POST(form) | - | DBReturnDTO |  |
| `?` | GET | +2 path seg | ServiceResult<(List<PersonTeamAssignment | 404 |
| `PoolScore/GetPoolScore` | GET | DeviceId, PoolId | ServiceResult<PoolScoreModel> | 500 |
| `PoolScore/GetSubPoolScores` | GET | DeviceId, PoolId | ServiceResult<SubPoolScoreModel> | 200 empty |
| `TeamActivity/DeleteAbsence` | DELETE | deviceId, id, userId | DBReturnDTO |  |
| `TeamActivity/DeleteCarPassenger` | DELETE | deviceId, person, teamActivityId, userId | DBReturnStatus |  |
| `TeamActivity/DeleteTeamActivity` | DELETE | deleteRecurrence, deviceId, id, logInMessageCenter, userId | DBReturnStatus |  |
| `TeamActivity/DeleteTeamActivityPerson` | DELETE | appversion, deviceId, userId | DBReturnStatus |  |
| `TeamActivity/DeleteTeamActivityPersonAccess` | DELETE | deviceId, personId, teamActivityId | DBReturnStatus |  |
| `TeamActivity/DeleteTeamActivityPersonPaymentUrl` | DELETE | activityId, appversion, deviceId, personId | DBReturnStatus |  |
| `TeamActivity/DeleteTeamActivityTask` | DELETE | deviceId, teamActivityId, teamtaskId | DBReturnStatus |  |
| `TeamActivity/DeleteTeamActivityTeamMemberGroupAccess` | DELETE | deviceId, teamActivityId, teamMemberGroupId | DBReturnStatus |  |
| `TeamActivity/GetAbsences` | GET | clubId, deviceId, personId, teamId | List<HOTeamAbsenceDTO> | 200 empty |
| `TeamActivity/GetConflict` | GET | deviceId, teamActivityId | TeamActivityConflictHandlingModel | 500 |
| `TeamActivity/GetDriverPassengerList` | GET | deviceId, driverPersonId, teamActivityId | List<HOTeamActivityPassenger> | 500 |
| `TeamActivity/GetInitialTeamActivityDeposit` | GET | activityId, appversion, deviceId, personId | TeamActivityDepositDialogModel | 200 (141b) |
| `TeamActivity/GetListTeamActivityDeposit` | GET | activityId, appversion, deviceId | List<TeamActivityDepositModel> | 200 empty |
| `TeamActivity/GetListTeamActivityDepositPerson` | GET | appversion, depositId, deviceId | List<TeamActivityDepositPersonModel> | 200 empty |
| `TeamActivity/GetListTeamActivityTeamMemberPerson` | GET | activityId, appversion, deviceId, isTeamPerson | List<TeamActivityTeamMemberPersonModel> | 204 |
| `TeamActivity/GetTeamActivity` | GET | deviceId, id | TeamActivityModel | 204 |
| `TeamActivity/GetTeamActivityAllList` | GET | deviceId, personId | List<TeamActivityListModel> | 200 (33139b) |
| `TeamActivity/GetTeamActivityList` | GET | all, clubId, deviceId, fromDate, isCoach, personId, teamId | List<TeamActivityListModel> | 500 |
| `TeamActivity/GetTeamActivityPerson` | GET | activityId, appversion, deviceId, isTeamPerson, personId | TeamActivityPersonModel | 204 |
| `TeamActivity/GetTeamActivityPersonAccessList` | GET | clubId, deviceId, teamActivityId, teamId | List<TeamMemberModel> | 200 empty |
| `TeamActivity/GetTeamActivityPersonPageNotification` | GET | activityId, deviceId, isContactPerson, personId | PageNotificationModel | 500 |
| `TeamActivity/GetTeamActivityPersonPaymentUrl` | POST(form) | appversion, clubId, deviceId, userId | DBReturnStatus |  |
| `TeamActivity/GetTeamActivityPersonUnsubscripeButton` | GET | activityId, appversion, deviceId, isTeamPerson, personId | TeamActivityPersonButtonModel | 200 (272b) |
| `TeamActivity/GetTeamActivitySignUpTypeList` | GET | deviceId | List<SignUpTypeModel> | 200 (108b) |
| `TeamActivity/GetTeamActivityTaskList` | GET | clubId, deviceId, teamActivityId, teamId | List<TeamTasksModel> | 200 (866b) |
| `TeamActivity/GetTeamActivityTeamMemberGroupAccessList` | GET | clubId, deviceId, teamActivityId, teamId | List<TeamMemberGroupModel> | 200 empty |
| `TeamActivity/GetTeamActivityTypeList` | GET | clubId, deviceId, teamId | List<TypeModel> | 200 (853b) |
| `TeamActivity/InsertAbsence` | POST(form) | deviceId | DBReturnDTO<bool> |  |
| `TeamActivity/InsertCarPassenger` | POST(form) | deviceId, driverPersonId, isTeamPerson, passengerPersonId, t | DBReturnStatus |  |
| `TeamActivity/InsertConflictHandling` | POST(form) | reset, stadiumAndRound, teamActivityId, userId | DBReturnStatus |  |
| `TeamActivity/InsertTeamActivity` | POST(form) | deviceId, userId | DBReturnStatus |  |
| `TeamActivity/InsertTeamActivityDeposit` | POST(form) | activityId, appversion, bankAccountNo, bankRegNo, deviceId,  | DBReturnStatus |  |
| `TeamActivity/InsertTeamActivityPerson` | POST(form) | appversion, deviceId, userId | DBReturnStatus |  |
| `TeamActivity/InsertTeamActivityPersonAccess` | POST(form) | deviceId, personId, teamActivityId, userId | DBReturnStatus |  |
| `TeamActivity/InsertTeamActivityTask` | POST(form) | deviceId, teamActivityId, teamtaskId | DBReturnStatus |  |
| `TeamActivity/InsertTeamActivityTeamMemberGroupAccess` | POST(form) | deviceId, teamActivityId, teamMemberGroupId, userId | DBReturnStatus |  |
| `TeamActivity/InsertTeamVisit` | POST(form) | clubId, isCoach, personId, teamId | DBReturnStatus |  |
| `TeamActivity/RevertTeamActivityPerson` | POST(form) | appversion, deviceId, userId | DBReturnStatus |  |
| `TeamActivity/UpdateAbsence` | POST(form) | deviceId | DBReturnDTO<bool> |  |
| `TeamActivity/UpdateTeamActivity` | POST(form) | deviceId, userId | DBReturnStatus |  |
| `TeamActivity/UpdateTeamActivityCarSelection` | POST(form) | deviceId, id, useCarSelection | DBReturnStatus |  |
| `TeamActivity/UpdateTeamActivityLimitedAccess` | POST(form) | deviceId, hasLimitedAccess, id | DBReturnStatus |  |
| `TeamActivity/UpdateTeamActivityMinCarSeats` | POST(form) | id, minCarSeats | DBReturnStatus |  |
| `TeamActivity/UpdateTeamActivityPerson` | POST(form) | appversion, deviceId, userId | DBReturnStatus |  |
| `TeamActivity/UpdateTeamActivityPersonRefundPayment` | POST(form) | appversion, deviceId, refund, userId | DBReturnStatus |  |
| `TeamActivity/UpdateTeamActivityTaskPersonCarSeats` | POST(form) | carSeats, deviceId, id, userId | DBReturnStatus |  |
| `TeamActivity/UpdateTeamActivityVisibleToAll` | POST(form) | deviceId, id, visibleToAll | DBReturnStatus |  |
| `Test/SendEmail` | GET | content, emailTo, subject | DBReturnStatus | 404 |