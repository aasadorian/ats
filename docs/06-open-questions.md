# 06 — Open Questions

Decisions to settle before or during build. Most rule questions become `LeagueSeason`
config ([04](04-data-model.md)), so they won't block the architecture, but they need answers
before the first real season. When one is resolved, move it to **Resolved** below, record it in
the decision log in [README](README.md), and update the relevant doc.

## League rules — open
1. **Games cancelled outright** (never played, like 2022 BUF–CIN) — void with 0 points for
   everyone (assumed)? If it's the tiebreaker game, does the tiebreak fall back to the previous
   game, or does the prize just split?
2. **Playoffs** — regular season only (assumed)?

## Product — open
3. Others' picks hidden until each game locks (current design), or visible earlier?
4. Login method preference — email+password, magic link, Google? (Can support several.)
5. Import past seasons from officepoolstop? If so, can we export CSV/HTML from it?
6. Entry fees / payouts — track in-app (record only) or keep off-app?
7. Notification channels — email only for MVP, or also SMS/push?
8. Domain name for the site.
9. How many members do we expect? (Assumed 10–50.)

## Technical — open
10. Confirm hosting choice (Render vs. Railway vs. a VPS) and budget.
11. Email provider choice (Postmark / Resend / SES) — needs a verified sending domain.
12. Target launch: in time for the 2027 season? A soft launch running alongside officepoolstop
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
