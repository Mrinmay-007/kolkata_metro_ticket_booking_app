# TESTIMONIAL

## Approach

I ran the app first and let it break — errors point straight at bugs faster than reading code cold. Fixed things in the order they surfaced: setup, then verification, then the two features.

## What the Project Is

Two databases doing different jobs: SQLite holds the static metro network (stations, connections, interchanges), Postgres holds live state (tickets, a verification/heartbeat check). The "verification code" is an AES puzzle — two key halves split across both DBs, decrypted once a background thread proves the system's alive.

## Bugs & Fixes

- **Missing deps** — `sqlalchemy` and `lucide-react` were used but never installed. Added both.
- **Wrong SQLite path** — code treated the `.py` file itself as a folder. Fixed the path and filename.
- **Empty endpoints** — `get_all_stations()` and `get_metro_route()` were stubs. Wrote the SQLite query for stations, and Dijkstra (over connections + interchanges) for routing.
- **CORS pointed at port 3000**, frontend actually runs on 5173. Fixed.
- **API base URL pointed at 8080**, backend runs on 8000. Fixed.
- **Response shape mismatch** — my first route response didn't match what `RouteSelector.jsx` already expected. Read the component, conformed the backend to it instead of the reverse.
- **Ticket creation 500 error** on a stray null byte — Postgres can't store it. Added validation so it fails clean with a 422 instead of crashing.
- **"PostgreSQL Config: Failed"** — Postgres was reachable, just never seeded. `create_tables.py` builds empty tables; only `postgres_init.sql` inserts the actual data. Ran the seed script, problem solved.

## Challenges

Some failures looked like connection issues but were seeding issues instead — the per-check breakdown in `/api/status` was the only way to tell "unreachable" apart from "reachable but empty." Took running things end-to-end, not just reading code, to catch the wiring bugs (ports, paths, contracts).

## Assumptions

- Kept the frontend's existing response shape as the real contract rather than changing it.
- Same source/destination returns a trivial zero-fare route, not an error.
- Station matching is case-insensitive and trimmed.

## With More Time

- Tests for the routing logic (interchanges, disconnected stations, edge cases).
- A startup check that fails loudly if Postgres is unseeded, instead of silently surfacing later.
- One setup command (`make setup` or Docker Compose) so table creation and seeding can't drift apart again.
- Retry/backoff on the frontend's status polling so a backend restart doesn't flash "offline."