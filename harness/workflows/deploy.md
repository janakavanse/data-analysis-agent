# workflow: deploy

Deploy is a **later phase**, run only after the system is built, reconciled, and
qa-signed-off. Invoked by the `deploy` skill. Default target: **Render**.

## Prerequisites

- All build phases complete; gates green; loop closed.
- Secrets configured as environment variables (never committed) — `.env.example` lists
  every one.
- A documented local run path that works (the README commands are true).

## Steps (Render default)

1. Confirm the stack's run command and port from `spec/engineering/tech-stack.md`.
2. Add the deploy manifest (e.g. `render.yaml`) describing the service(s) and the
   managed/local database.
3. Set environment variables in the platform — from `.env.example`, with real values,
   never committed.
4. Deploy; watch the platform logs; hit the health endpoint and one real page.
5. The analyst confirms runtime behavior in `logs/` matches the spec in the deployed
   environment.

Other targets (Docker, another PaaS, a cloud function) are chosen by the architect and
recorded in `spec/engineering/tech-stack.md`. Keep the default simple.
