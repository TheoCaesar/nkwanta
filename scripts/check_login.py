"""Work out why a sign-in is being refused.

    python -m scripts.check_login
    python -m scripts.check_login commuter@nkwanta.demo NkwantaDemo2026

Login deliberately gives the same answer for "no such account" and "wrong password", so
that the form cannot be used to discover which email addresses are registered. That is
correct, and it makes diagnosing your own database awkward — hence this script, which
looks at the database directly and says which it actually is.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import Report, User
from app.security import verify_password
from app.services.seed import DEMO_PASSWORD, SEED_USERS, _id


async def main(email: str | None, password: str) -> int:
    settings = get_settings()
    if not settings.database_configured:
        print("DATABASE_URL is not set. Copy .env.example to .env first.", file=sys.stderr)
        return 1

    engine = create_async_engine(settings.sqlalchemy_url, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with maker() as session:
            total = await session.scalar(select(func.count()).select_from(User))
            reports = await session.scalar(select(func.count()).select_from(Report))
            print(f"database holds {total} account(s), {reports} report(s)\n")

            if not total:
                print("There are no accounts at all — the seed has not run successfully.")
                print("Run:  python -m scripts.seed_demo --reset")
                return 2

            print("Demonstration accounts:")
            print(f"  {'email':<34}{'role':<11}{'active':<8}{'password matches'}")
            print(f"  {'-'*34}{'-'*11}{'-'*8}{'-'*16}")

            missing = 0
            for seed_user in SEED_USERS:
                user = await session.get(User, _id("user", seed_user.key))
                if user is None:
                    print(f"  {seed_user.key + '@nkwanta.demo':<34}{'—':<11}{'—':<8}NOT CREATED")
                    missing += 1
                    continue
                ok = verify_password(DEMO_PASSWORD, user.password_hash)
                print(f"  {user.email:<34}{user.role.value:<11}"
                      f"{'yes' if user.is_active else 'NO':<8}{'yes' if ok else 'NO'}")

            if email:
                print(f"\nChecking {email} specifically:")
                user = await session.scalar(
                    select(User).where(User.email == email.strip().lower())
                )
                if user is None:
                    print("  No account with that email exists.")
                    print("  Note the address is stored lowercase — check for a typo or stray space.")
                    return 3
                print(f"  found: {user.display_name} ({user.role.value})")
                print(f"  active: {user.is_active}")
                print(f"  hash starts: {user.password_hash[:7]}…  (bcrypt hashes start '$2b$12$')")
                if verify_password(password, user.password_hash):
                    print("\n  The password is CORRECT. If sign-in still fails, the problem is")
                    print("  not the credentials — check the browser network tab for the actual")
                    print("  request being sent.")
                else:
                    print(f"\n  The password does NOT match. Reseed with:")
                    print("    python -m scripts.seed_demo --reset")
                    return 4

            if missing:
                print(f"\n{missing} demonstration account(s) are missing. Run:")
                print("  python -m scripts.seed_demo --reset")
                return 2

        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    args = sys.argv[1:]
    raise SystemExit(asyncio.run(main(
        args[0] if args else "commuter@nkwanta.demo",
        args[1] if len(args) > 1 else DEMO_PASSWORD,
    )))
