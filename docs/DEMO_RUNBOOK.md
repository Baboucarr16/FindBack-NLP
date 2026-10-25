# FindBack local demonstration runbook

This guide describes the verified CSV-mode workflow in the integration
worktree. The checked-in reports are synthetic examples. This is a local demo,
not a live community service or a verified Supabase deployment.

## 1. Start the application

Working directory:

```powershell
cd C:\Users\babou\OneDrive\Desktop\FindBack-integration
```

Set up dependencies if needed, then choose CSV mode explicitly:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FINDBACK_STORE="csv"
python app.py
```

Open <http://127.0.0.1:5000>. Stop the server with **Ctrl+C** in its terminal.
No Supabase credentials are required or used by the CSV store. Do not set
`FINDBACK_STORE=supabase` for this demo.

The Sentence-BERT model loads lazily on the first search. This machine has the
model cached: the search and found-report workflow completed with
`HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`. A fresh machine may need internet
access once to download the model. Do not start a first-time download during the
presentation; warm the cache beforehand.

## 2. Demonstrate search

1. On the home page, enter:
   - Category: **Backpack**
   - Description: `A dark blue bag with a Nike mark near the campus library.`
   - Place type: **University**
   - Place: **Greenfield University**
   - Campus: **Main Campus**
   - Building: **Central Library**
   - Floor: **2nd Floor**
   - Specific area: **Reading Room**
   - Date: **2026-08-18**
   - Approximate time: **16:20**
2. Submit. The verified local run returned HTTP 200 and included synthetic
   candidate **FB002**. Candidate ordering and score can vary with query details.
3. Point out the report fields, weighted component breakdown, evidence notes,
   and disclaimer. Explain that similarity is a ranking aid, not a probability
   or proof of ownership.
4. Say clearly that the checked-in reports are synthetic, not genuine reports
   from members of the public. The current CSV-mode homepage and results page
   also display this notice.

## 3. Demonstrate found-item reporting safely

Open **I found something** and walk through the form. Do not submit it during
the normal demo: CSV mode appends found reports to the checked-in
`dataset/findback_reports.csv`, and the app does not expose a safe CSV-path
override in its launcher.

The complete found-submit-and-search-again path was verified with a disposable
temporary copy of the CSV. It created `FB027` in that temporary copy and the next
search returned it. The checked-in CSV was not written.

For a repeatable regression check that never writes the checked-in CSV, run
the tests that inject a temporary dataset path:

```powershell
python -m pytest tests/test_app.py -k "found_submission" -q --basetemp=.pytest-found-demo
```

This verifies form submissions against test-owned temporary files; it is not a
standalone presentation server launcher for an alternate dataset.

## 4. Themes and responsive layout

The shared shell has a theme toggle, and the JavaScript follows system
preference until a choice is saved in local storage. You can click the toggle
if you want to show the control, but browser rendering was not available during
verification. Review the page in a real browser beforehand; do not claim that
mobile layout or both theme renderings were visually browser-tested here.

## 5. Do not present these as verified features

- Login/registration: no public credential forms are exposed. Direct account
  routes show a notice; the underlying backend handlers were only tested with
  stubs.
- Supabase report persistence, live Auth, RLS behavior, match writes, claims,
  notifications, or owner decisions: SQL migration 004 was not applied and no
  isolated database was available. No production project was accessed during
  this verification.
- Real-world accuracy: the benchmark directories contain only `EXAMPLE`
  placeholders. No Top-1, Top-3, MRR, or accuracy claim is supported.
- Gemini or other external AI services: no experiment or API call was made.

CSV-mode search does not save a Lost report. Found-report submissions do append
to CSV. Those different behaviors should be stated plainly if asked.

## Final verification note — 2026-10-25

The local service on `127.0.0.1:5187` returned 200 for the homepage, found
form, account notice pages, and CSS/theme assets. A CSRF-valid sample query
returned 200 with candidate FB002 and the non-ownership disclaimer. The test
suite had 156 passing tests before this pass and **158 passing tests** after;
the focused theme/template subset had **18 passing tests**. Browser screenshots,
responsive rendering, keyboard traversal, contrast measurement, and console
inspection remain unverified because no browser runtime/tool is available.

## 6. Recovery steps

- **Port 5000 is occupied:** stop the other local server, or run with a free
  port, for example `$env:PORT="5001"`, then open
  <http://127.0.0.1:5001>.
- **Model unavailable while offline:** do not claim that search is working.
  Restore network access before the demo to allow the initial model download,
  or use the already verified environment with its model cache intact.
- **Missing Python package:** activate the project virtual environment and run
  `pip install -r requirements.txt` before presenting.
- **Unexpected storage selection:** set `$env:FINDBACK_STORE="csv"` in the same
  PowerShell session before starting `python app.py`.
- **Authentication notice:** expected in this demo. Continue with anonymous
  CSV search; do not try to configure or connect live Supabase during the demo.

## 7. Data protection

Do not submit a found report to the checked-in CSV during the presentation.
Do not run legacy scripts that previously wrote generated results or hard cases
into `dataset/`; those scripts now route output to the ignored `outputs/`
directory. No SQL migrations or production service operations are part of this
runbook.
