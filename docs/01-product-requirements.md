# 01 — Product Requirements

## 1. Overview

A private web app that runs a season-long NFL "against the spread" (ATS) pick'em league.
It replaces officepoolstop.com for our group. The goal is to match what we use today, remove
manual commissioner work, and be pleasant to use on a phone.

## 2. League rules (as currently understood)

> Items marked **(?)** are assumptions to confirm — see [06 Open Questions](06-open-questions.md).

All league times are **Pacific** (`America/Los_Angeles`); storage is UTC.

> **These rules are our league's defaults, not hard-coded behavior.** Almost every rule below is
> a commissioner setting, modeled on OfficePoolStop's manager options: pick type, points, best bet
> count and bonus, line mode and source, half-point lines and push scoring, lock times, auto-pick,
> tiebreaker game and type, bonuses and prizes. See [08 League Settings](08-league-settings.md).
> The one fixed rule: **ties left after the tiebreaker guess are always split.**

### 2.1 Picks
- Every member picks **every NFL regular-season game** each week (18 weeks, ~272 games).
- A pick is one team **against the spread**, e.g. `KC -3.5` or `BUF +3.5`.
- Each member designates **exactly one best bet** per week.
- Each member enters a **Monday night total-points guess** each week (weekly tiebreaker, §2.5).
- Picks can be changed freely until they lock.

### 2.1.1 Missed picks ✅
- A missed pick simply **earns no points**; it scores the same as a loss. There is **no auto-pick**.
- Example: a member who misses the Thursday game gets 0 for that game but can still pick every
  other game normally.
- Missing picks **never affect prize eligibility**. A member with missed picks who has the most
  points (or ties for it) still wins (or shares) the weekly prize.
- A missed best bet is forfeited: no best bet that week, so no 3-point opportunity. No auto-assign.
- A missed Monday night guess loses any tiebreak it is needed for.

### 2.2 Pick lock rule ✅
Each game has a **lock time**:

```
week_lock_at = Sunday of that NFL week at 10:00 AM Pacific   (configurable)
game_lock_at = min(game.kickoff_at, week_lock_at)
```

- Games that kick off **before** the Sunday lock (Thursday night, Friday/Saturday games,
  Sunday-morning international games) lock **at their own kickoff**.
- **Everything else** — all Sunday games, Sunday night, Monday night — locks at **Sunday 10:00 AM PT**.
- The best bet follows the lock of the game it's on. Moving the best bet requires **both** the old
  and the new game to be unlocked. In practice, after Sunday 10 AM nothing can change.
- The Monday night tiebreaker guess locks with the week (Sunday 10:00 AM PT).

### 2.3 Spreads ✅
- Spreads are **locked once per week** at a configurable time, default **Tuesday 3:00 AM Pacific**, matching when OfficePoolStop captures its fixed opening line.
- After lock, the line does not move in our system even if Vegas moves.
- **Every line is a half point** (e.g. `-3.5`, `+6.5`, never `-3` or `PK`), so **pushes are impossible**.
  The database rejects any line that isn't `x.5`.
- **Rounding rule ✅ — the favorite gives the extra half point.** A whole-number line moves half a
  point against the favorite: `KC -3 / BUF +3` becomes `KC -3.5 / BUF +3.5`, so a 3-point KC win
  covers for BUF. A pick'em (0) becomes `-0.5` for the moneyline favorite (or the home team if even).
- **Games with no line ("OFF") ✅.** If a game has no line at spread lock (e.g., a QB injury takes it
  off the board), it is **unpickable until a line appears**. The rest of the week opens normally.
  - The first line posted after that (or one the commissioner enters) is normalized to a half point
    and locked, like any other line.
  - **Cutoff: kickoff of the first game of the week** (normally the Thursday night game). If no line
    appears by then, the game is **void for the week**: nobody can pick it, it can't be a best bet,
    and it's worth 0 for everyone. A line appearing after the cutoff is ignored.
  - A void game can still be the **tiebreaker game**. The tiebreaker uses its final score, not its line.
- Source of the spread is an odds feed (see [05](05-data-sources.md)); the commissioner can
  override any line (still half-point) before or after lock, with an audit trail.
- Picks can't be made until the week's spreads are locked/published.

### 2.4 Scoring ✅
| Outcome | Normal pick | Best bet |
|---------|-------------|----------|
| Covers (win ATS) | 1 | 3 |
| Fails to cover (loss ATS) | 0 | 0 |
| No pick | 0 | — (best bet forfeited) |
| Game postponed | Pending; scored normally when played | Pending; scored normally when played |
| Game cancelled outright (never played) | 0 for everyone (?) | 0 (?) |

ATS result: `picked_team_score + spread_for_picked_team` vs. `opponent_score`.
Because lines are always half points, the result is always a win or a loss.

### 2.4.1 Postponed games ✅
- A postponed game **stays in its original week** and is **scored when it's actually played**,
  using the spread locked for that week. A best bet on it simply counts at that point.
- Picks on a postponed game **don't reopen**. They stay locked at the game's original lock time,
  because members' picks were made against that week's line.
- The week's **weekly prize waits** until the postponed game is final. Standings show the week as
  "provisional — waiting on X @ Y" in the meantime.
- If the **tiebreaker game** is the one postponed, the weekly tiebreaker waits for it too. The
  tiebreaker game never switches to a different game.

### 2.5 Prizes / leaderboards
1. **Weekly winner** ✅ — most **points** in a single week (1 per correct pick, 3 for a correct
   best bet). Awarded every week, 18 weeks.
   - **Tiebreaker ✅:** closest guess to the **total points scored in the last game of the week**
     (normally Monday night; with a Monday doubleheader it's the later game). Over and under count
     the same: only the distance matters.
   - **Still tied ✅:** if two or more tied members are equally close (e.g. guesses of 40 and 50 on a
     45-point game), **all of them split the weekly prize**. The same applies if all tied members
     missed their guess.
   - A member who missed their guess loses the tiebreak to anyone who entered one.
2. **Best bet champion** — most correct best bets over the season (max 18).
   **Ties ✅:** everyone tied splits the prize.
3. **Season points champion** — most total points over the season.
   **Ties ✅:** everyone tied splits the prize.

## 3. Users and roles

| Role | Can do |
|------|--------|
| **Member** | Make/edit own picks, view standings, view others' picks once locked, manage own profile/notifications |
| **Commissioner** | Everything a member can, plus: invite/remove members, override spreads, correct scores, enter picks on behalf of a member (audited), configure lock times and rules, mark prizes paid |
| **Site admin** | Django admin access (developer). Same person as commissioner initially. |

Expected scale: one league, ~10–50 members. Design for one league but keep a `League`
entity so a second league (or a test league) is trivial later.

## 4. Feature list

### 4.1 MVP (needed to replace the current site)

**Accounts**
- Invite-only signup via a commissioner-generated link
- Login with email + password, plus "magic link" / Google login if cheap to add
- Password reset by email

**Making picks**
- Week view listing every game: kickoff time (local tz), teams, locked spread, pick buttons
- One-tap pick per game; select best bet with a star/toggle
- Clear lock state per game (open / locked / final) and a countdown to next lock
- Monday night total-points guess input (tiebreaker)
- Validation: exactly one best bet; can't change locked picks (enforced server-side)
- "Unpicked games" warning before the first kickoff
- Mobile-first layout

**Viewing results**
- Weekly picks grid: members × games, revealed per-game after kickoff (others' picks hidden before lock)
- Live-ish scores and ATS status (covering / not covering) during games
- Weekly standings with weekly winner highlighted
- Season standings: total points, correct picks, best bet record
- Best bet leaderboard
- Member profile page: season history by week

**Commissioner tools**
- Season setup: import schedule for the season automatically
- Weekly spread review screen: see fetched lines, edit, then publish/lock
- League settings page covering every MVP setting in [08](08-league-settings.md), with defaults
  matching our league, audit history, and the mid-season change rules from 08 §3
- OFF-line handling: games with no line show as "OFF — no line yet" and are unpickable until a line
  is posted or entered; marked "void this week" if there's still no line at the first kickoff of the week.
  Members are emailed when an OFF game becomes pickable.
- Score correction screen for a game (in case a feed is wrong)
- Member management (invite, deactivate, reset)
- Audit log of overrides

**Automation**
- Automatic weekly spread fetch + lock at the configured time
- Automatic score ingestion and grading
- Email reminder to members with missing picks (e.g., Thursday afternoon and Sunday morning)

### 4.2 Later / nice-to-have
- Import historical seasons from officepoolstop (CSV) for all-time records
- Push notifications (PWA) instead of / in addition to email
- Pick-percentage stats ("72% of the league took KC")
- Season recap / fun stats (best/worst team to pick, streaks, contrarian rate)
- Entry fee and payout tracking (record-keeping only — no payment processing)
- League message board / trash talk on each week
- Playoff bonus pool
- Multiple leagues per site / self-serve league creation
- Dark mode

### 4.3 Explicit non-goals
- No real-money handling or payment processing inside the app.
- No public signup; the site is private.
- No native mobile apps — responsive web (optionally installable PWA) only.

## 5. Non-functional requirements
- **Correctness of locks** is the #1 requirement: server-side time checks, all times stored in UTC
  and displayed in Pacific (or the member's local timezone).
- **Auditability**: every spread/score override and commissioner-entered pick is logged.
- **Availability**: must be up around Sunday kickoffs; brief downtime midweek is fine.
- **Cost**: target < $20/month.
- **Low maintenance**: runs unattended through a season; commissioner touch only when a feed fails.
