# Chess Shorts Studio

One click generates fresh chess puzzles (26 categories) and renders them into
a vertical 1080x1920 YouTube Short (MP4 with sound) plus a thumbnail PNG.

## Run
    ./run.sh
or:  ./.venv/bin/python chess_shorts_studio.py

## Features
- 26 puzzle categories (mates, forks, skewers, pins, smothered, castling
  mate, en passant mate, discovered attacks, ...)
- Expert generation: df-pn proof-number solver, retrograde construction +
  beam search, simulated annealing, composition judge, quiescence defense
- Sound effects (synthesized) + optional background music baked into the MP4
- Eval bar (built-in evaluator or Stockfish path), no-spoiler mode
- 4 board themes, batch mode, title/hashtag generator, PGN export
- Anti-repeat manifest (puzzle_manifest.json): rendered positions are
  never generated again
- Live preview identical to the exported video

## Notes
- Optional: set SYZYGY_PATH in the script for tablebase cross-checks.
- You can also add trending music when uploading; the baked-in track is
  optional and ducked under the sound effects.
