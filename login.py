from pathlib import Path
from getpass import getpass

from instagrapi import Client
from instagrapi.exceptions import LoginRequired, TwoFactorRequired


BASE_DIR = Path(__file__).resolve().parent
SESSION_FILE = BASE_DIR / "session.json"


def main():
    print("=== Reel2Career Instagram Login ===")
    print()
    print("Credentials are entered locally.")
    print("They are never printed or sent to this chat.")
    print()

    username = input("Instagram username: ").strip()

    if not username:
        raise SystemExit("Username cannot be empty.")

    password = getpass("Instagram password: ")

    if not password:
        raise SystemExit("Password cannot be empty.")

    client = Client()

    # Keep the client on a stable configuration for this account.
    client.set_locale("en_US")
    client.set_country("US")
    client.set_country_code(1)

    try:
        print("\nLogging in...")
        client.login(username, password)

        client.dump_settings(str(SESSION_FILE))

        print("\nLOGIN SUCCESSFUL")
        print(f"Session saved locally: {SESSION_FILE}")

    except TwoFactorRequired:
        print("\nInstagram requires 2FA.")
        code = input("Enter your Instagram 2FA code: ").strip()

        if not code:
            raise SystemExit("2FA code cannot be empty.")

        client.login(
            username,
            password,
            verification_code=code,
        )

        client.dump_settings(str(SESSION_FILE))

        print("\nLOGIN SUCCESSFUL")
        print(f"Session saved locally: {SESSION_FILE}")

    except LoginRequired:
        raise SystemExit(
            "\nInstagram rejected the login/session. "
            "Stop here rather than repeatedly retrying."
        )

    except Exception as exc:
        raise SystemExit(
            f"\nLogin failed: {type(exc).__name__}: {exc}"
        )


if __name__ == "__main__":
    main()