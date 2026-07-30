# Work-area accessibility feature — DECISION DEFERRED

Status: **owner to decide later** (2026-07-29). This doc captures the options so we
can resume without re-deriving them.

## Goal
A "commute to work" accessibility feature for each property — e.g.
`transit_min_to_gangnam`, `transit_min_to_nearest_cbd`. One of the three
destination-accessibility signals requested (metro / commercial / **work area**).

## Key principle (already settled)
Distinguish **walk destinations** from **commute destinations**:
- **Nearest metro & nearest commercial = walk** → straight-line (haversine) is the
  standard, correct proxy (walk path ≈ straight-line × ~1.3, ranking preserved).
  **Already built** (`add_transit_features` + commercial to come). Bus itinerary is
  irrelevant here — you walk to the nearest station/store.
- **Work area = commute** → needs *network travel-time*; straight-line is a weak
  proxy. This is the open question.

## Options for the work-area (commute-time) feature

| Option | What it gives | Cost / effort | Notes |
|---|---|---|---|
| **A. ODsay routing API** | real door-to-door transit time (bus+metro+walk, real schedules/transfers) | small code; external API + key; ~free 1k/day | Dedupe to unique complexes × a few CBDs (~few-k calls, cached). Most faithful to "exact route". Needs `ODSAY_API_KEY`. |
| **B. Metro-only travel-time graph** | network travel-time over the subway graph (Dijkstra, adjacency from station order along each line + transfers) | medium; **self-contained**, no API | Uses the 1,099-station file we already have. Captures Seoul's *dominant* commute mode; ignores bus feeders. |
| **C. TAGO 버스노선정보 + self-built multimodal router** | topology only (route→stop sequence) | **large build** + approximate | TAGO gives itinerary/topology but **no timetable** → segment times must be approximated (distance/speed + headway/2). Heavy per-city ingest. Worst effort/accuracy point. |
| **D. Straight-line to nearest CBD** | euclidean distance to nearest 업무지구 | trivial | crude; ignores network entirely. |

## Recommendation
- Want **real route-aware time** → **A (ODsay)**.
- Want **self-contained / no external API** → **B (metro graph)**.
- **Avoid C** — TAGO route data alone is not a shortcut to travel-time; the router +
  time-approximation is the hard part, and the result is still approximate.

## CBD (work-area) anchor candidates
Seoul: 강남역, 여의도, 광화문/시청, 판교, 가산·구로디지털단지, 마곡, 상암, 문정.
Busan: 서면, 센텀시티, 부산역/중앙동.
(For B/D these are graph targets / points; for A these are ODsay destination coords.)

## Resume checklist
1. Pick A / B / D.
2. If A: register at lab.odsay.com → add `ODSAY_API_KEY` to `.env` + `Secrets`.
3. Dedupe geocoded properties to unique complex coords before routing (not 214k rows).
4. Land per-complex `transit_min_to_<cbd>` → join into the feature matrix (build.py).

Related: [[transport-reference-data]] (metro/bus station coords, already landed);
straight-line metro/commercial features live in `features/spatial.py`.
