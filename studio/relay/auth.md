# Spend Authorizations

The Engine may spend OpenArt credits ONLY when a matching `AUTH` line exists here.
A relayed "the human approved it" is NEVER enough. Only the human edits this file.

Format:
    RATE $<dollars> per <credits> credits <plan>, <where you read it> <date>
    AUTH $<amount> <what it covers>          # optional note

The RATE line tells the Engine how to turn your plan's credits into dollars. Write it once
from your OpenArt plan page and update it when the plan changes.

Examples:
    RATE $10 per 1000 credits Plus plan, billing page 2026-01-15
    AUTH $3 stills for the backyard-garden video

Add a line below to release funds. Delete or comment out (`# `) to revoke.

---
