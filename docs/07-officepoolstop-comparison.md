# 07 — Comparison with OfficePoolStop

How our design compares with OfficePoolStop's (OPS) **NFL Pick'em pool**, based on its public
rules, FAQ, help desk articles and 2026 release notes (researched 2026-10-05; sources at the bottom).

**Caveat:** most OPS rules are *manager-configurable*, and we can't see our league's actual
settings from outside a login. Where OPS offers options, this doc lists them. The league manager
should check **Manager → League Settings** (including **Advanced**) to confirm which ones our league
uses; see the checklist in §4.

> **Update (2026-10-05):** we decided to make our rules as configurable as OPS's
> ([08 League Settings](08-league-settings.md)). Most ⚠️ items below are now **settings**: line mode,
> lock time, line source, half-point lines vs. pushes, OFF-line handling, key-game count and bonus,
> auto-pick, tiebreaker type and the OPS bonuses. Our league's rules are just the defaults. The
> deliberate exception is **tie handling**: we always split after the tiebreaker guess, with no
> SOV / win % chain (§2.5, §2.6).

## 1. Summary

| Area | OPS | Ours | Status |
|------|-----|------|--------|
| Per-game lock + weekly hard deadline | Yes | Yes | ✅ Same model |
| Line capture time | Opening line, captured **Tue ~4:00 AM MT (3:00 AM PT)** | Configurable, default **Tue 3:00 AM PT** | ✅ Same |
| Line source | ESPN (single source) | Median across US sportsbooks | ⚠️ Differs |
| Half points / pushes | Lines used as published; push = tie (½ point) or loss | Every line forced to x.5; no pushes | ⚠️ Differs |
| Best bet | "Key games": configurable count and bonus | Exactly one best bet, worth 3 | ✅ Same if configured as 1 key game, +2 bonus |
| Weekly tiebreaker | Total-points guess on a tiebreaker game, then a chain of further tiebreakers | Guess on last game of the week, then split | ⚠️ Differs after the first tiebreaker |
| Season prize ties | Broken by win %, strength of victory, total tiebreakers | Split | ⚠️ Differs |
| Missed picks | Optional AutoPick (random / home / favorite), with limits | No auto-pick; missed = 0 | ✅ Same if AutoPick is off |
| Cancelled games | Removed; picks discarded "as if a bye" | Assumed void, 0 for everyone | ✅ Effectively the same |
| Postponed games | Added back when rescheduled; same-week cases at admin discretion | Stay in original week; picks stay locked; scored when played | ⚠️ Possibly differs |
| Line unavailable ("OFF") | No picks until posted; straight up (0 line) if still missing at kickoff | No picks until posted; void for the week if still missing at the first kickoff of the week | ⚠️ Fallback differs |
| Pick visibility | Visible when the game starts; all visible after the deadline | Visible when each game locks | ✅ Effectively the same |
| Reminders | 24 h before deadline + 8 h before Thursday game | Thu 12:00 PT + Sun 08:00 PT | Minor difference |

## 2. Divergences in detail

### 2.1 Line capture time and which line ✅
- **OPS:** offers three line settings: *Variable* (the line at the moment each player picks),
  *Fixed Opening Line*, and *Closing Line*. "The opening line is set Tuesday AM around 4am MST."
  Our understanding that "the spread is locked Tuesday morning" matches **Fixed Opening Line**,
  captured at about **3:00 AM Pacific**.
- **Ours (decided):** snapshot at a configurable time, default **Tuesday 3:00 AM PT**, chosen to match
  OPS. (The original noon default was dropped.) Lines can still differ slightly because of the
  line source (§2.2) and half-point rounding (§2.3).

### 2.2 Line source ⚠️
- **OPS:** "Lines sourced from ESPN," which is a single consensus-style feed.
- **Ours:** median of all US books returned by The Odds API.
- **Impact:** lines will usually agree, but can differ by half a point. Low risk.

### 2.3 Half points and pushes ⚠️ (biggest rule change)
- **OPS:** uses the line as published, whole numbers included. A push "is recorded as a Tie," worth
  **half the pick's points**. Managers can instead choose "Count Tie as Loss."
- **Ours:** every line is converted to a half point (favorite gives the extra half, `-3 → -3.5`),
  so pushes can't happen.
- **Impact:** on roughly 10–15% of games (common whole-number lines like 3, 7, 1, 6), our line is
  half a point different from what OPS would show. Results differ only when the final margin lands
  exactly on that number. Where OPS would score ½ point (or a loss), ours scores a full win for the
  underdog side and 0 for the favorite side. Members should be told about this before the season.

### 2.4 Best bet vs. key games ✅
- **OPS:** "Key games": each player checks a configured number of games, and each correct key game
  earns "the configured value as extra points." The 2026 release added season-long key-game
  tracking and key-game wins as a standings tiebreaker.
- **Ours:** one best bet per week, worth 3 total (1 + 2 extra). This is the same thing if our league
  is configured with **1 key game worth 2 extra points**. Our "best bet champion" prize maps to OPS's
  season key-game wins.

### 2.5 Weekly tiebreaker ⚠️
- **OPS:** "Each week you select one tie-breaker game by guessing the total points" (or margin of
  victory, if configured). If still tied, OPS applies, in order: best strength of victory (SOV) for
  the week → best season winning % → best total tiebreakers. Managers can also choose to
  **"chop ties"** (split).
- **Ours:** total-points guess on the last game of the week, then **split** among everyone equally close.
- **Impact:** same, unless our league has the default chain enabled. In that case OPS would have
  picked a single winner where we split.

### 2.6 Season prize ties ⚠️
- **OPS:** final points standings ties are broken by season winning % → overall SOV → total
  tiebreakers. Other season prizes use win % → SOV → total tiebreakers → point total.
- **Ours:** split among everyone tied (decided).
- **Impact:** only matters on an exact tie, but it's a real rule difference unless the league uses "chop ties".

### 2.7 Missed picks ✅ (if AutoPick is off)
- **OPS:** optional AutoPick (Random, Last Home Team, Biggest Favorite, …), limited to a configured
  number of weeks. AutoPick's tiebreaker guess is 40.
- **Ours:** no auto-pick; a missed pick earns 0 (decided).

### 2.8 Postponed and cancelled games
- **Cancelled — ✅ effectively the same.** OPS: "Cancelled games will be as if the teams were on a bye
  week and the pick will simply be discarded." This matches our assumed "void, 0 for everyone."
  If the *tiebreaker game* is cancelled, OPS gives players "a 20-point debit if they don't adjust
  their pick," which suggests OPS lets players re-enter a tiebreaker for another game. We haven't
  decided this yet (06).
- **Postponed — ⚠️ possibly differs.** OPS says postponed games "are added automatically when
  rescheduled," and same-week postponements are handled "at administrative discretion." It isn't
  clear whether picks reopen. **Ours:** the game stays in its week, picks stay locked against the
  original line, and it's scored when played (decided).

### 2.9 Lines that are "OFF" ⚠️ (differs only in the fallback)
- **OPS:** if a game has no line (e.g., a QB injury takes it off the board), "a pick is not allowed
  for that game." When a line is posted it is used; if still missing at kickoff, the game is scored
  **straight up (0-point spread)**.
- **Ours (decided):** same until a line appears: the game is unpickable and the first line posted is
  used. The difference is the cutoff: if no line appears by the **first kickoff of the week**
  (normally Thursday night), the game is **void for the week** rather than picked straight up.

### 2.10 Minor differences
- **Reminders:** OPS sends one reminder 24 h before the league deadline and one 8 h before the
  Thursday game. Ours: Thu 12:00 PT and Sun 08:00 PT. Similar, easy to align.
- **Deadline guidance:** OPS recommends deadlines "no earlier than Sunday 11am MST." That's
  exactly our Sunday 10:00 AM PT lock.
- **Grace period:** OPS can limit edits to N hours after first submitting (mainly for the Bookie pool).
  We don't have this and don't need it.

## 3. OPS features not in our MVP

| OPS feature | Ours |
|-------------|------|
| Over/under bonus, underdog bonus, tiebreaker-exact bonus | Not planned |
| "Bye week" (drop each player's worst week) | Not planned |
| Strength of victory (SOV) stat | Not planned; easy to add as a stat |
| League forum / message board | Later list |
| Payment tracking | Later list (record-keeping only) |
| Career stats, hall of fame/shame, league history | Later list (requires importing history) |
| Co-managers | Covered: multiple members can have the commissioner role |
| Manager entering picks for a player | Covered (audited) |
| "Clones" (multiple entries per person) | Not planned |
| Per-user time zone | Planned: display in the member's local time zone |
| Native mobile app (in development at OPS) | Responsive web / PWA |

## 4. Checklist: confirm our league's current OPS settings

The commissioner should look these up in OPS **Manager → League Settings**:

1. **Line setting:** Variable, Fixed Opening, or Closing?
2. **Push handling:** tie (½ point) or "Count Tie as Loss"?
3. **Key games:** how many per week, and what bonus value?
4. **Weekly tiebreakers:** which tiebreaker game, and is the chain (SOV → win % → total tiebreakers)
   on, or "chop ties"?
5. **Final standings tiebreakers / chop ties.**
6. **AutoPick:** on or off?
7. **Bye week:** is each player's worst week dropped?
8. **League deadline:** day and time.

## Sources
- [Pick'em Pool Rules](https://officepoolstop.com/Rules-Pickem-Pool)
- [FAQ](https://officepoolstop.com/faq)
- [Features](https://officepoolstop.com/info/features)
- [What's New at OfficePoolStop for 2026](https://officepoolstop.com/blog/whats-new-officepoolstop-2026)
- [Help: Against the Spread (using the line)](https://officepoolstop.zohodesk.com/portal/en/kb/articles/against-the-spread-using-the-line)
- [Help: League deadline](https://officepoolstop.zohodesk.com/portal/en/kb/articles/league-deadline)
- [Help: Pick grace period](https://officepoolstop.zohodesk.com/portal/en/kb/articles/pick-grace-period)
- [Help: Football pool cancelled games contingencies](https://officepoolstop.zohodesk.com/portal/en/kb/articles/covid-contingencies)
- [Help: Automatic email reminders](https://officepoolstop.zohodesk.com/portal/en/kb/articles/email-reminders-for-picks)
