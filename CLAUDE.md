# absolved

Mobile-first web app at <https://absolved.be> for preparing for confession: tracks each user's confession dates, holds
an examination of conscience for the next one, and shows it during confession with the Act of Contrition.

## Stage

`0.0.x` - alpha, greenfield, no users. No backward compatibility or data migrations to preserve yet.

## Decisions

- Stack: Django, SQLite, Tailwind (standalone CLI), Lucide icons; Fly.io, one 256 MB machine in `fra`.
- The examination is encrypted in the browser; the server never sees it or the password. Username and password only, no
  email, no recovery. English only for now, with every string translatable.
- What determines the keys (listed at the top of `static/js/keys.js`) and the question and statement ids in
  `absolved/examination.py` must never change: users would lose their accounts or their answers. The browser tests
  pin the keys.
- Avoid writing our own JavaScript where a library or the platform does the job; no HTMX (see `docs/plan.md`).
- Plan, privacy model and data model: `docs/plan.md`. Commands, configuration and deployment: `README.md`. Backups
  and restoring: `docs/backup.md`.
- Repository: <https://github.com/Ch00k/absolved.be>, public. No commits, pushes or deploys until asked.
