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

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
