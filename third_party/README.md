# Third-party code

## day-trader-skill

- Source: https://github.com/Jakeschincariol/day-trader-skill
- Commit: `3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd` (20 Oct 2026), copied 24 Nov 2026
- License: MIT, Copyright (c) 2026 Jake Schincariol. See `day-trader-skill/LICENSE`, which must stay with the code.
- Changes: none. The folder is an exact copy without its git history.

It is reference code. Nothing in `master_agent/` or `web/` imports it, and the dashboard does not run it.
It is built for US markets (New York hours, SEC, Nasdaq lists, Alpaca), so it does not work on NSE as it is.

Its own tests are not part of this project's `pytest` run (see `pytest.ini`). To run them:

```bash
cd third_party/day-trader-skill
python -m unittest discover -s tests -v
```
