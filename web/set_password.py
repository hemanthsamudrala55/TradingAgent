"""Set the owner password.  Run:  python -m web.set_password

Stores only a hash of the password (and a random SECRET_KEY for login cookies) in .env, which
Git ignores. Run it again to change the password; that also logs out every open session.
"""
from __future__ import annotations

import getpass
import secrets
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

ENV = Path(__file__).resolve().parent.parent / ".env"
MIN_LENGTH = 12


def update_env(text: str, values: dict[str, str]) -> str:
    lines = [ln for ln in text.splitlines() if ln.split("=", 1)[0].strip() not in values]
    return "\n".join(lines + [f"{k}={v}" for k, v in values.items()]) + "\n"


def main() -> None:
    pw = getpass.getpass(f"New owner password (at least {MIN_LENGTH} characters): ")
    if len(pw) < MIN_LENGTH:
        sys.exit("Too short. Nothing was changed.")
    if getpass.getpass("Type it again: ") != pw:
        sys.exit("The two passwords differ. Nothing was changed.")
    text = ENV.read_text() if ENV.exists() else ""
    ENV.write_text(update_env(text, {"OWNER_PASSWORD_HASH": generate_password_hash(pw),
                                     "SECRET_KEY": secrets.token_hex(32)}))
    print(f"Saved to {ENV}. Restart the app for it to take effect.")


if __name__ == "__main__":
    main()
