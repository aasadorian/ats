# 10 — Activity Log

A single, append-only record of **everything that happens in a league**: lines being fetched, set
and overridden; picks being made and changed; scores corrected; settings changed; members invited;
and the account security events from [09](09-user-management.md). It answers "who did what, when,
and what did it look like before?", which settles disputes like "I changed my pick before kickoff!"

It replaces the earlier `AuditEvent` table with one `ActivityEvent` table used for everything.

## 1. Principles
- **Everything that changes league state is logged**, whether the actor is a member, a commissioner,
  a site admin or the system (a scheduled job).
- **Written in the same database transaction as the change.** If the change commits, the log entry
  commits; if it rolls back, so does the entry. There's never a change without a record, or a record
  of a change that didn't happen.
- **Explicit, not magic.** Events are written by the service-layer functions that make the change
  (`picks.services.save_pick()` calls `record_event(...)`), not by Django model signals. Signals
  miss bulk updates and don't know who the actor was or why.
- **Append-only.** Entries are never edited or deleted by the app (see §6).
- **Respects pick secrecy.** A pick event is never shown to other members before that game's picks
  are revealed (same rule as [04 §4](04-data-model.md)).

## 2. Event record

| Field | Meaning |
|-------|---------|
| `id` | Sequential ID (also gives a total order) |
| `occurred_at` | UTC timestamp, from the database clock |
| `league_id` | League the event belongs to (null for site-wide events like login) |
| `league_week_id` | Week, when relevant (for filtering) |
| `category` | `lines`, `picks`, `games`, `standings`, `settings`, `membership`, `security`, `notifications` |
| `event_type` | e.g. `pick.changed` (catalog in §3) |
| `actor_type` | `member`, `commissioner`, `admin`, `system` |
| `actor_id` | User who did it (null for `system`) |
| `subject_user_id` | Whose data was affected, when different from the actor (e.g., a commissioner entering a member's pick) |
| `object_type`, `object_id` | The thing changed (`pick` 812, `spread` 77, `game` 401…) |
| `before`, `after` | JSON snapshots of only the fields that changed |
| `summary` | Human-readable line, rendered when written: "Andrew changed BUF +3.5 → KC -3.5" |
| `source` | `web`, `job:lock_spreads`, `job:sync_scores`, `admin`, … |
| `request_id` | Ties together all events from one request or job run |
| `ip_address` | Security events only; dropped after 90 days (see 09 §7) |

Indexes: `(league_id, occurred_at)`, `(league_id, league_week_id, category)`, `(actor_id, occurred_at)`,
`(subject_user_id, occurred_at)`, `(object_type, object_id)`.

## 3. Event catalog

### Lines
| Event | Actor | Logged when |
|-------|-------|-------------|
| `line.fetched` | system | Feed returned lines at spread lock (raw median, book count per game) |
| `line.locked` | system | A game's line was normalized to a half point and locked (raw → locked) |
| `line.off` | system | No line available at spread lock; game unpickable |
| `line.posted_late` | system / commissioner | An OFF game received its line before the cutoff |
| `line.voided` | system | Still no line at the first kickoff of the week; game void for the week |
| `line.overridden` | commissioner | Commissioner changed a line (before → after, with an optional reason) |
| `week.published` | system / commissioner | Week opened for picks |
| `week.lock_times_changed` | commissioner | Per-week override of spread lock or picks deadline |

### Picks
| Event | Actor | Logged when |
|-------|-------|-------------|
| `pick.made` | member | First pick on a game (team, line at the time) |
| `pick.changed` | member | Switched teams on a game (before → after) |
| `pick.cleared` | member | Removed a pick before lock |
| `best_bet.set` / `best_bet.moved` / `best_bet.cleared` | member | Best bet placed, moved from game A to game B, or removed |
| `tiebreaker.set` / `tiebreaker.changed` | member | Tiebreaker guess entered or changed |
| `pick.entered_for_member` | commissioner | Commissioner made or changed a pick for a member (subject = the member; reason required) |
| `pick.rejected_locked` | member | Attempt to change a pick after its lock (useful in disputes: shows they tried, and when) |
| `pick.autopicked` | system | AutoPick filled a missed pick (Later phase) |

### Games and results
| Event | Actor | Logged when |
|-------|-------|-------------|
| `game.rescheduled` | system | Kickoff time changed (flex or schedule update) |
| `game.postponed` / `game.cancelled` | system / commissioner | Status change |
| `game.final` | system | Final score recorded (live score updates are **not** logged; too noisy) |
| `game.score_corrected` | commissioner | Commissioner changed a final score (before → after, reason) |
| `tiebreaker_game.set` / `tiebreaker_game.changed` | system / commissioner | Tiebreaker game chosen or overridden |
| `week.final` | system | Every game in the week is final |
| `week.winners_decided` | system | Weekly winner(s), points and tiebreaker distances |

### Settings and membership
| Event | Actor | Logged when |
|-------|-------|-------------|
| `settings.changed` | commissioner | Any `LeagueSettings` change (before → after; whether it was applied retroactively) |
| `invite.sent` / `invite.resent` / `invite.revoked` / `invite.accepted` | commissioner / member | Invite lifecycle |
| `membership.role_changed` / `membership.deactivated` / `membership.reactivated` | commissioner | Role or status change |
| `member.left` | member | Member left the league |

### Security (from [09 §7](09-user-management.md))
`auth.login`, `auth.login_failed`, `auth.logout_all`, `auth.password_changed`, `auth.password_reset`,
`auth.email_changed`, `auth.mfa_added`, `auth.mfa_removed`, `account.deleted`.

### Notifications
`email.reminders_sent` (one event per run with the count, not one per email), `email.bounced`.

## 4. Who can see what

| Viewer | Sees |
|--------|------|
| **Member** — "My activity" | Their own events: all their pick changes with timestamps, tiebreaker changes, account/security events, and anything a commissioner did to their data |
| **Member** — league feed | League-wide events: lines locked/overridden, week published/final, weekly winners, score corrections, setting changes, members joining. Other members' pick events appear **only after that game's picks are revealed** |
| **Commissioner** | Everything in their league, with filters (member, week, game, category, event type, date range) and **CSV export**. Before a game locks, other members' pick events show *that* a pick changed but **not which team**, so the commissioner can't gain an edge either |
| **Site admin** | Everything, via the admin |

The commissioner restriction in the last row is a deliberate fairness rule; it can be revisited.

### UI entry points
- **Game detail → "Pick history"**: the timeline of every member's pick changes on one game (after lock).
- **Member profile → "Activity"**: one member's timeline (for that member and commissioners).
- **Commissioner → "Activity log"**: full filterable log + export.
- **League home → "Recent activity"**: the public league feed.

## 5. Implementation
```python
def record_event(*, league, event_type, actor, object, before=None, after=None,
                 subject_user=None, league_week=None, source="web") -> ActivityEvent:
    """Must be called inside the transaction that makes the change."""
```
- Each service function that changes state calls `record_event` once per logical change.
- `before`/`after` are computed with a small diff helper, so only changed fields are stored.
- The request ID comes from middleware (and from the job runner for scheduled jobs).
- Volume: about 50 members × ~272 picks plus edits ≈ 30–60k events per season. Trivial for Postgres;
  no partitioning or separate store needed.

## 6. Integrity and retention
- **Append-only at the database level:** a Postgres trigger rejects `UPDATE` and `DELETE` on the
  table. The only exceptions are the two privacy jobs below, which run through a dedicated database
  function.
- **Retention:** league activity events are kept for the life of the league (they're the league's
  history). IP addresses on security events are nulled after **90 days**.
- **Account deletion** ([09 §5](09-user-management.md)): events stay, but the deleted user is shown as
  "Former member #N" and their email is removed from any snapshots.
- Not planned: cryptographic hash-chaining of entries. Append-only plus regular backups is enough for
  a friends' league.

## 7. Testing
- Every service function that changes state has a test asserting the exact event(s) it writes,
  including `before`/`after`.
- A test that the log and the change roll back together.
- Visibility tests: before lock, neither another member nor the commissioner can see which team
  an unlocked pick event was for.
- A test that `UPDATE`/`DELETE` on the table fails.
