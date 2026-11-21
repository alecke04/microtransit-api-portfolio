"""Generate local-only credentials. Never print them or overwrite an existing .env."""

import json
import os
import secrets
from pathlib import Path


def main():
    password, reader, writer = (secrets.token_urlsafe(32) for _ in range(3))
    path = Path(".env")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(
            f"POSTGRES_PASSWORD={password}\nDATABASE_URL=postgresql+asyncpg://portfolio:{password}@127.0.0.1:55439/portfolio_demo\n"
        )
        file.write(f"READ_API_KEY={reader}\nVALID_API_KEYS_JSON='{json.dumps({'DEMO_TRACKER_01': writer})}'\n")
        file.write("CORS_ORIGINS=http://localhost:3000\nTESTING=false\n")
    print("Generated credentials in untracked .env. Keep this file private.")


if __name__ == "__main__":
    main()
