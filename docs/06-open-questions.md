# 06 — Open Questions

Decisions to settle before or during build. Most rule questions become `LeagueSettings`
settings ([08](08-league-settings.md)), so they won't block the architecture, but they need answers
before the first real season. When one is resolved, move it to **Resolved** below, record it in
the decision log in [README](README.md), and update the relevant doc.

## League rules — open
1. **Games cancelled outright** (never played, like 2022 BUF–CIN) — void with 0 points for
   everyone (assumed)? If it's the tiebreaker game, does the tiebreak fall back to the previous
   game, or does the prize just split?
2. **Playoffs** — regular season only (assumed)?
3. **Default for lines "OFF" at lock time** — now a setting (`off_line_handling`,
   `off_line_fallback`, see [08](08-league-settings.md)). Confirm the proposed defaults: publish the
   week with the game unpickable until a line appears, and use favorite `-0.5` if none ever does.
4. **Default spread lock time** — now a setting; OPS captures the opening line Tue ~3:00 AM PT and
   our default is noon PT. Keep noon as the default? See [07 §2.1](07-officepoolstop-comparison.md).
5. **MVP vs. Later settings** — confirm the phase split in [08 §1](08-league-settings.md). Is
   anything marked Later (variable/closing lines, auto-pick, bonuses, drop worst week) needed for launch?

## Product — open
6. Others' picks hidden until each game locks (current design), or visible earlier?
7. Login method preference — email+password, magic link, Google? (Can support several.)
8. Import past seasons from officepoolstop? If so, can we export CSV/HTML from it?
9. Entry fees / payouts — track in-app (record only) or keep off-app?
10. Notification channels — email only for MVP, or also SMS/push?
11. Domain name for the site.
12. How many members do we expect? (Assumed 10–50.)

## Technical — open
13. Confirm hosting choice (Render vs. Railway vs. a VPS) and budget.
14. Email provider choice (Postmark / Resend / SES) — needs a verified sending domain.
15. Target launch: in time for the 2027 season? A soft launch running alongside officepoolstop
    for the rest of 2026 would be a great real-world test.

## Resolved
| Date | Question | Decision | Doc |
|------|----------|----------|-----|
| 2026-10-05 | When do picks lock? | Games before Sunday 10:00 AM PT lock at their own kickoff; all others lock Sunday 10:00 AM PT | [01 §2.2](01-product-requirements.md) |
| 2026-10-05 | Best bet lock? | Follows its game's lock; moving it requires both games unlocked | [01 §2.2](01-product-requirements.md) |
| 2026-10-05 | Pushes? | Impossible — all lines are half points | [01 §2.3](01-product-requirements.md) |
| 2026-10-05 | Weekly winner metric | Most points (best bet = 3) | [01 §2.5](01-product-requirements.md) |
| 2026-10-05 | Weekly tiebreaker | Closest guess to total points in the last game of the week | [01 §2.5](01-product-requirements.md) |
| 2026-10-05 | Spread lock time | Configurable; default Tuesday 12:00 PM PT | [01 §2.3](01-product-requirements.md), [04](04-data-model.md) |
| 2026-10-05 | Whole-number line rounding | Favorite gives the half point: `-3 → -3.5`, `+3 → +3.5`; pick'em → moneyline favorite `-0.5` | [01 §2.3](01-product-requirements.md), [05](05-data-sources.md) |
| 2026-10-05 | Monday doubleheaders | Tiebreaker is the last game of the week by kickoff | [01 §2.5](01-product-requirements.md), [04](04-data-model.md) |
| 2026-10-05 | Tie on the tiebreaker | All members equally close split the weekly prize | [01 §2.5](01-product-requirements.md), [04 §3](04-data-model.md) |
| 2026-10-05 | Missed picks | No auto-pick; a missed pick earns 0 (same as a loss); no effect on prize eligibility | [01 §2.1.1](01-product-requirements.md) |
| 2026-10-05 | Missed best bet | Forfeited; no auto-assign | [01 §2.1.1](01-product-requirements.md) |
| 2026-10-05 | Missed tiebreaker guess | Loses the tiebreak to anyone who entered one | [01 §2.1.1](01-product-requirements.md) |
| 2026-10-05 | Season points / best bet prize ties | Split among everyone tied | [01 §2.5](01-product-requirements.md), [04 §3](04-data-model.md) |
| 2026-10-05 | Postponed games | Stay in their week; scored (including best bets) when played; picks don't reopen | [01 §2.4.1](01-product-requirements.md), [04](04-data-model.md) |
| 2026-10-05 | Postponed tiebreaker game | Weekly prize waits until it's played; tiebreaker game doesn't change | [01 §2.4.1](01-product-requirements.md) |
| 2026-10-05 | Canonical spread | Median line across US sportsbooks at lock time | [05](05-data-sources.md) |
| 2026-10-05 | How configurable? | As configurable as OfficePoolStop's manager settings; our rules become the defaults | [08](08-league-settings.md) |
| 2026-10-05 | Tie handling after the tiebreaker | Always split; not configurable (no SOV / win % chain) | [08](08-league-settings.md) |
