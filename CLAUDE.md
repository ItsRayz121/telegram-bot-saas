# Project instructions

## Git workflow

Approved changes should be committed directly to `main` and pushed to `origin/main`,
because Railway and Vercel auto-deploy from `main`.

Do not create feature branches or PRs unless I explicitly ask.

Before pushing to `main`, always:

- run relevant tests/checks
- show changed files
- confirm no secrets are being committed

## REVERT.md

`REVERT.md` at the repo root is the undo playbook. It exists so that when something
breaks in production, we can fix it without reading code.

Any commit that touches **money, data deletion, the bot hot path, or a live plan limit**
must add a `REVERT.md` entry **in the same commit**, using the template at the bottom of
that file. State plainly what a revert does *not* undo — deleted rows, sent messages and
charged cards do not come back.

Prefer a **kill switch** (an env var that disables the feature in ~30 seconds with no
deploy) over a git revert, and write it down. New risky features should ship with one.
