---
key: file-entry
section: 4
title: File entry
enabled: true
brief: **File entry** (`write_entry {lens: "file"}`). Written after a scan, with the scan's id as `trigger_id`: your judgment of the files that matter. `scan_material` carries the instructions.
---

**File entry — `write_entry {lens: "file"}`** (the second half of `#scan`).
The scan says what the work did; the file entry says *where in the code*
and how much each move matters — the judgment only you have. One
`paths` record per file you modified: `importance` 1–5,
`blast_radius` 1–10, `test_coverage` covered/partial/untested, `novelty`
new/pattern-follow/pattern-break, `security_surface`, `why`. Git supplies
what it can (action, line counts, the `diff`) — you supply the
assessment. `trigger_lens` = `"scan"`, `trigger_id` = the scan's id; the
scan answer shows `files_entry: null` until this is written. `summary`:
`N files · +X/−Y · theme`. `narrative`: the overall story, then a line
per file. `per_file`: one item per file, the functions and classes
touched, the ordering, and why.

```json
{"lens":"file","fields":{
  "summary":"3 files · +187/−4 · Redis rate-limit middleware",
  "narrative":"Redis-backed limiter landed on the request path. …",
  "per_file":["app/middleware/rate_limit.py — RateLimitMiddleware.dispatch: INCR+EXPIRE pipeline, 429 with Retry-After",
       "app/main.py — stack order CORS → Auth → RateLimit → router"],
  "trigger_lens":"scan","trigger_id":"sn_…","files_important_n":2,"files_ignored_n":1,
  "paths":[
   {"path":"app/middleware/rate_limit.py","importance":4,"blast_radius":10,
    "test_coverage":"covered","novelty":"new","security_surface":true,
    "why":"Every request passes through it; a bug here is an outage."},
   {"path":"app/main.py","importance":2,"blast_radius":6,"test_coverage":"covered",
    "why":"Middleware order — auth must run before the limiter."}]}}
```
