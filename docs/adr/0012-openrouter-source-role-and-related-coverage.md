# OpenRouter is a callable-model source; hidden is not disabled

Status: accepted

Hugging Face already owns trending open-weight model momentum. OpenRouter answers a different question: which models can be called through one API, whether newly listed, free-priced, or priced. A model may appear in both. We also needed Bilibili out of the default discovery surface without deleting a working connector, and we needed a way to point at the same model or product in two entries without merging them.

## Considered options (rejected)

- Treat OpenRouter as another Hugging Face momentum feed — duplicates a source job and mixes call prices with Hub popularity.
- Use a `:free` id suffix, or a missing price, as proof of free token pricing — the suffix does not establish both prices, and unknown is not zero.
- Apply OpenRouter's seven-day fallback to every source in a mixed digest — silently widens sources that already have their own window.
- Hiding Bilibili disables new requests and settings — conflicts with explicit requests that already work and strands a configured source.
- Link entries by shared title words or broad topic — "M3.1 Flash" and "M3.1 Pro" would look like the same model.

## Consequences

- OpenRouter is its own source kind. Ranking stays kind-aware. Mixed-section fallback order places it after Hugging Face and before GitHub.
- Free token pricing requires both input and output prices to be explicitly zero. The badge states that narrower claim.
- The seven-day window is an OpenRouter-only fallback. An explicit timeframe covers every selected source.
- A hidden source leaves discovery, suggestions, and source-selection lists. Explicit requests, settings, credentials, and historical results remain.
- Related coverage links confidently identical model or product identities and does not change membership or display rank. It is separate from Hugging Face family grouping.
