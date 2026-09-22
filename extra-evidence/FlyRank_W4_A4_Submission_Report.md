# FlyRank Internship — Backend Track — Week 4 
## Auth · Login & Protect

**Repository:** https://github.com/AnasAbdelmotelb/task-api  
**Pull Request (merged into `main`):** https://github.com/AnasAbdelmotelb/task-api/pull/2  
**Merge commit:** `69353a2`

---

## Submission Summary

Added Supabase Auth to the existing FastAPI + PostgreSQL Task API, including sign up, log in, log out, JWT-protected routes through a reusable FastAPI dependency, a 403 admin-only route demonstrating the 401-vs-403 distinction, and Swagger UI Bearer authentication at `/docs`.

The implementation was completed through **9 incremental commits** covering the required assignment stages, the optional 403 admin authorization case, and final screenshot evidence. Existing task-management functionality was preserved.

Live verification was performed against a real Supabase project: signup/login succeeded, `/protected/profile` returned authenticated user data, an invalid/tampered token was correctly rejected with `401`, and the admin route correctly enforced authorization with `403`.

No secrets were committed. `.env` is git-ignored and was confirmed absent from the repository history.

---

## What Was Built

- `POST /auth/signup` — create a user via Supabase Auth (`201 / 400`)
- `POST /auth/login` — authenticate and return access + refresh token (`200 / 400 / 401`)
- `POST /auth/logout` — protected logout endpoint (`204`)
- `GET /public/info` — public route, no authentication required (`200`)
- `GET /protected/profile` — JWT-verified route returning safe user metadata (`200 / 401`)
- `GET /protected/dashboard` — second protected route proving auth-guard reuse (`200 / 401`)
- `GET /protected/admin` — admin allowlist on top of authentication (`200 / 401 / 403`)
- Swagger UI Bearer **Authorize** flow at `/docs`

---

## Live Verification

Performed against a real Supabase project:

- Real signup/login against Supabase → `200`
- Swagger UI **Authorize** + **Try it out** with a real bearer token
- `GET /protected/profile` with a valid token → `200`
- Invalid/tampered token → `401`
  ```json
  {"error": "Invalid or expired token"}
  ```
- Non-admin user on `/protected/admin` → `403`
  ```json
  {"error": "Admin access required"}
  ```

---

## Security

- `.env` is git-ignored and was never committed
- Git history was checked for secrets after merge
- Only the Supabase anon/publishable client key is used
- `service_role` key is never used
- Authentication errors return a consistent JSON body:
  ```json
  {"error": "..."}
  ```

---

## Evidence in the Repository

- `swagger-bearer-auth.png`  
  Live Swagger screenshot showing a successful `200` response from `GET /protected/profile` and lock icons on protected routes.

- `README.md`  
  Includes setup instructions, endpoint/auth tables, status codes, curl examples, Supabase configuration, and the `401` vs `403` explanation.

- Git commit history  
  9 incremental commits documenting the assignment progression.

- Existing A1–A3 evidence retained:
  - `clean-clone-test.png`
  - `postgres-database-screenshot.png`
  - `crud-status-codes.png`
  - `database-screenshot.png`
  - `db-browser.png`

- `extra-evidence/FlyRank_W3_A2_Short_Report.pdf`  
  Prior assignment evidence retained for continuity.

---

## Commit History

1. `Stage 0: setup server and supabase client`
2. `Stage 1: signup and login routes working`
3. `Stage 2: public route and unverified protected route`
4. `Stage 3: profile route token verification`
5. `Stage 4: auth middleware and logout endpoint`
6. `Extras: 403 admin authorization case`
7. `Stage 5: Swagger UI documentation with bearer auth`
8. `Stage 6: publish to GitHub and write README`
9. `docs: add Swagger bearer auth screenshot evidence`

---

## Final Status

**Submission complete.**

All required A4 functionality is present on `main`, the required Swagger evidence is included, the merged pull request is available publicly, no secrets were committed, and the existing A1–A3 functionality was preserved.
