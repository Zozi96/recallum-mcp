"""Minimal stdlib admin CLI: users, API keys, and embedding maintenance.

The CLI talks to the same DI graph as the server. Issued secrets are printed
exactly once; only their SHA-256 hash is persisted. ``reembed`` needs the
same Ollama the server uses reachable from this process's environment.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import uuid

from recallum.auth.api_keys import UserNotFoundError
from recallum.config import get_settings
from recallum.container import Container, create_container, shutdown_container


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recallum-admin",
        description="Recallum administration: users and API keys.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_user = subparsers.add_parser("create-user", help="Create a user account")
    create_user.add_argument("--email", required=True)

    issue_key = subparsers.add_parser(
        "issue-key", help="Issue an API key for a user (printed once)"
    )
    issue_key.add_argument("--email", required=True)
    issue_key.add_argument("--name", default=None, help="Optional label for the key")

    revoke_key = subparsers.add_parser("revoke-key", help="Revoke an API key by id")
    revoke_key.add_argument("--key-id", required=True, type=uuid.UUID)

    list_keys = subparsers.add_parser(
        "list-keys", help="List a user's keys (metadata only, never secrets)"
    )
    list_keys.add_argument("--email", required=True)

    set_password = subparsers.add_parser(
        "set-password", help="Set a user's web password interactively"
    )
    set_password.add_argument("--email", required=True)
    grant_admin = subparsers.add_parser("grant-admin", help="Grant web administrator status")
    grant_admin.add_argument("--email", required=True)
    revoke_admin = subparsers.add_parser("revoke-admin", help="Revoke web administrator status")
    revoke_admin.add_argument("--email", required=True)

    reembed = subparsers.add_parser(
        "reembed",
        help=(
            "Re-embed memories whose vectors came from another embedding model "
            "(run after changing RECALLUM__OLLAMA__MODEL)"
        ),
    )
    reembed_target = reembed.add_mutually_exclusive_group(required=True)
    reembed_target.add_argument("--email", help="Re-embed one user's memories")
    reembed_target.add_argument(
        "--all-users", action="store_true", help="Re-embed every user's memories"
    )
    reembed.add_argument(
        "--batch-size", type=int, default=50, help="Rows fetched per batch (default 50)"
    )

    return parser


async def _run(args: argparse.Namespace, container: Container) -> int:
    if args.command == "create-user":
        user = await container.api_key_service().create_user(args.email)
        print(f"user created: {user.id} ({user.email})")
        return 0

    if args.command == "issue-key":
        service = container.api_key_service()
        try:
            issued = await service.issue_key_for_email(args.email, args.name)
        except UserNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"key id:    {issued.key.id}")
        print(f"user:      {issued.user.email}")
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
        try:
            result = await container.api_key_service().list_keys_for_email(args.email)
        except UserNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if not result.keys:
            print("no keys")
            return 0
        for key in result.keys:
            status = "revoked" if key.is_revoked else "active"
            label = f" ({key.name})" if key.name else ""
            print(f"{key.id}{label}  {status}  created={key.created_at:%Y-%m-%d}")
        return 0

    if args.command in {"set-password", "grant-admin", "revoke-admin"}:
        user = await container.user_repository().get_by_email(args.email.lower())
        if user is None:
            print(f"error: user '{args.email}' does not exist", file=sys.stderr)
            return 1
        if args.command == "set-password":
            password = getpass.getpass("Password: ")
            confirmation = getpass.getpass("Confirm password: ")
            if password != confirmation:
                print("error: passwords do not match", file=sys.stderr)
                return 1
            await container.password_service().set_password(user, password)
            print(f"password set: {user.email}")
        else:
            is_admin = args.command == "grant-admin"
            await container.user_repository().set_admin(user.id, is_admin)
            print(f"administrator {'granted' if is_admin else 'revoked'}: {user.email}")
        return 0

    if args.command == "reembed":
        users_repo = container.user_repository()
        if args.all_users:
            users = list(await users_repo.list_users())
        else:
            user = await users_repo.get_by_email(args.email.lower())
            if user is None:
                print(f"error: user '{args.email}' does not exist", file=sys.stderr)
                return 1
            users = [user]
        service = container.memory_service()
        total_failed = 0
        for user in users:
            reembedded, failed = await service.reembed_stale(
                user.id, batch_size=max(1, args.batch_size)
            )
            total_failed += failed
            print(f"{user.email}: reembedded={reembedded} failed={failed}")
        if total_failed:
            print(
                f"error: {total_failed} memories could not be re-embedded; "
                "rerun once Ollama is reachable",
                file=sys.stderr,
            )
            return 1
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
