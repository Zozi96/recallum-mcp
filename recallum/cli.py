"""Minimal stdlib admin CLI: create users, issue API keys, revoke keys.

The CLI talks to the same DI graph as the server. Issued secrets are printed
exactly once; only their SHA-256 hash is persisted.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from recallum.config import get_settings
from recallum.container import Container, create_container, shutdown_container


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recallum-admin",
        description="Recallum administration: users and API keys.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_user = subparsers.add_parser("create-user", help="Create a user account")
    create_user.add_argument("--username", required=True)

    issue_key = subparsers.add_parser(
        "issue-key", help="Issue an API key for a user (printed once)"
    )
    issue_key.add_argument("--username", required=True)
    issue_key.add_argument("--name", default=None, help="Optional label for the key")

    revoke_key = subparsers.add_parser("revoke-key", help="Revoke an API key by id")
    revoke_key.add_argument("--key-id", required=True, type=uuid.UUID)

    list_keys = subparsers.add_parser(
        "list-keys", help="List a user's keys (metadata only, never secrets)"
    )
    list_keys.add_argument("--username", required=True)

    return parser


async def _run(args: argparse.Namespace, container: Container) -> int:
    if args.command == "create-user":
        user = await container.api_key_service().create_user(args.username)
        print(f"user created: {user.id} ({user.username})")
        return 0

    if args.command == "issue-key":
        service = container.api_key_service()
        user = await container.user_repository().get_by_username(args.username)
        if user is None:
            print(f"error: user '{args.username}' does not exist", file=sys.stderr)
            return 1
        issued = await service.issue_key(user.id, args.name)
        print(f"key id:    {issued.key.id}")
        print(f"user:      {user.username}")
        print(f"api key:   {issued.plaintext}")
        print("warning:   this secret is shown only once; store it now.")
        return 0

    if args.command == "revoke-key":
        revoked = await container.api_key_service().revoke_key(args.key_id)
        if not revoked:
            print(f"error: key {args.key_id} not found or already revoked", file=sys.stderr)
            return 1
        print(f"key revoked: {args.key_id}")
        return 0

    if args.command == "list-keys":
        user = await container.user_repository().get_by_username(args.username)
        if user is None:
            print(f"error: user '{args.username}' does not exist", file=sys.stderr)
            return 1
        keys = await container.api_key_service().list_keys(user.id)
        if not keys:
            print("no keys")
            return 0
        for key in keys:
            status = "revoked" if key.is_revoked else "active"
            label = f" ({key.name})" if key.name else ""
            print(f"{key.id}{label}  {status}  created={key.created_at:%Y-%m-%d}")
        return 0

    return 2  # pragma: no cover - argparse enforces known commands


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    container = create_container(get_settings())

    async def _lifecycle() -> int:
        try:
            return await _run(args, container)
        finally:
            await shutdown_container(container)

    try:
        return asyncio.run(_lifecycle())
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
