#!/usr/bin/env python3
"""Download the full YGOPRODeck v7 card database to data/cache/ygopro/card_database.json."""

from mobius.ygopro import YgoProDeckClient


def main() -> None:
    client = YgoProDeckClient()
    print("Downloading card database from YGOPRODeck…")
    count = client.ensure_card_database()
    print(f"Saved {count} cards to {client.database_path}")


if __name__ == "__main__":
    main()
