# Beta Lab

This directory is for isolated experiments that are not yet part of the
supported `realtime_asr` package surface.

Rules for content here:

- Keep each experiment in its own subdirectory.
- Prefer minimal runnable demos over premature abstractions.
- Do not import Beta Lab code into `src/realtime_asr` until the design is
  validated.
- When an experiment stabilizes, migrate the reusable parts into `src/` and
  keep this area for further prototyping.
