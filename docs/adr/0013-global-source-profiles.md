# Global source profiles replace the session item-count stepper

Status: accepted

ADR-0010 decision 2 stored one item count on each browser conversation because the composer showed a shared stepper. Per-source settings need different counts, and the command-line digest uses the same database. A count saved on one conversation cannot honestly become the count for every conversation, or for the command line.

Output language had the same shape. Storing it on Juya would have changed GitHub and Zhihu whenever Juya was selected. Each source already has a presentation language, so a forced global language would also change current mixed digests.

## Considered options (rejected)

- Keep the session stepper and add per-source counts beside it — two active counts for one source, with no rule for which wins.
- Copy each conversation's old count into the new profiles — conversations disagree, and a profile is archive-wide.
- Leave saved settings web-only — the same database would then run two configurations.
- Store language on the Juya profile and apply it to the whole digest — a Juya preference would change unrelated sources.
- Default the new global language to English or Chinese — either choice rewrites source-default presentation that already exists.
- Treat a numeric count as a promise to return that many rows — filling it would require relaxing filters, widening time, or splitting model families.

## Decision

1. Source profiles and output language are global for a database. The web app and the command line both read them. An explicit message or command-line option wins.
2. ADR-0010 decision 2 is superseded. Source checkboxes remain session preferences. The shared stepper is removed. Old session counts stay historical and are not active preferences. Run again repeats the resolved count from the original request.
3. A numeric item count means up to that many eligible display entries. GitHub has a numeric count. Only Juya offers `all`, and summarizing more than 20 stories requires confirmation.
4. Output language offers source default, English, and Simplified Chinese. Source default is the initial value. A language named in the request overrides it for that run. Entries remember the language they were generated in.

## Consequences

- The first run after this change shows a one-time notice. New requests use the global profiles, initially five items per source unless the owner changes them.
- Resolved requests record each source's count and effective time window so Run again does not re-interpret the old message against later settings.
- Juya `all` is bounded by the issues, topic, and timeframe already selected. It is not an archive crawl.
