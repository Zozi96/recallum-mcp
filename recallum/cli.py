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
from pathlib import Path

from recallum.auth.api_keys import UserNotFoundError
from recallum.bootstrap import MAX_CANDIDATES, scan_project
from recallum.config import get_settings
from recallum.container import (
    Container,
    create_container,
    init_container_resources,
    shutdown_container,
)
from recallum.embeddings.ollama import EmbeddingError
from recallum.evaluation import read_dataset, render_report, run_eval
from recallum.hygiene import DEFAULT_MAX_MEMORIES, build_hygiene_report, render_hygiene_report
from recallum.memory import MemoryValidationError
from recallum.memory.schemas import RememberBatchItem
from recallum.memory.service import MemoryService


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {parsed}")
    return parsed


def _unit_float(value: str) -> float:
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError(f"must be between 0.0 and 1.0, got {parsed}")
    return parsed


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

    eval_cmd = subparsers.add_parser(
        "eval",
        help=(
            "Measure retrieval quality against a golden dataset "
            "(needs Ollama; seeds the corpus into the given user)"
        ),
    )
    eval_cmd.add_argument("--email", required=True, help="User whose store hosts the eval corpus")
    eval_cmd.add_argument(
        "--dataset",
        required=True,
        help="Path to a golden dataset JSON (see scripts/eval_dataset.json)",
    )
    eval_cmd.add_argument("--k", type=int, default=10, help="Ranking depth (default 10)")
    eval_cmd.add_argument(
        "--trigram-weight",
        type=_unit_float,
        default=None,
        help="Override recall_trigram_weight for this run",
    )
    eval_cmd.add_argument(
        "--importance-weight",
        type=_unit_float,
        default=None,
        help="Override recall_importance_weight for this run",
    )
    eval_cmd.add_argument(
        "--usage-weight",
        type=_unit_float,
        default=None,
        help="Override recall_usage_weight for this run",
    )
    eval_cmd.add_argument(
        "--freshness-weight",
        type=_unit_float,
        default=None,
        help="Override recall_freshness_weight for this run",
    )
    eval_cmd.add_argument(
        "--vector-min-similarity",
        type=_unit_float,
        default=None,
        help="Override recall_vector_min_similarity for this run",
    )

    hygiene_cmd = subparsers.add_parser(
        "hygiene",
        help=(
            "Read-only corpus-hygiene report: near-duplicate clusters "
            "and contradiction candidates for one user"
        ),
    )
    hygiene_cmd.add_argument("--email", required=True)
    hygiene_cmd.add_argument(
        "--min-similarity",
        type=_unit_float,
        default=None,
        help=(
            "Cosine similarity floor for candidate pairs, in [0.0, 1.0] "
            "(default: limits.similar_min_similarity)"
        ),
    )
    hygiene_cmd.add_argument(
        "--limit",
        type=_positive_int,
        default=DEFAULT_MAX_MEMORIES,
        help=f"Cap on active memories scanned, >= 1 (default {DEFAULT_MAX_MEMORIES})",
    )

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

    bootstrap = subparsers.add_parser(
        "bootstrap",
        help=(
            "Scan a bounded allowlist of well-known project files "
            "(README, AGENTS.md, pyproject.toml, ...) for candidate memories. "
            "Prints candidates by default; --apply persists them"
        ),
    )
    bootstrap.add_argument("--email", required=True, help="User the candidates belong to")
    bootstrap.add_argument("--project", required=True, help="Canonical project key")
    bootstrap.add_argument("--path", required=True, type=Path, help="Project directory to scan")
    bootstrap.add_argument(
        "--apply",
        action="store_true",
        help="Persist candidates via remember_batch instead of printing them (default: dry-run)",
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
        if args.command == "set-password":
            password = getpass.getpass("Password: ")
            confirmation = getpass.getpass("Confirm password: ")
            if password != confirmation:
                print("error: passwords do not match", file=sys.stderr)
                return 1
            max_password_chars = container.config.boundary.request.password_max_chars.as_int()()
            if len(password) > max_password_chars:
                print(
                    f"error: password exceeds configured maximum length ({max_password_chars})",
                    file=sys.stderr,
                )
                return 1
        user = await container.user_repository().get_by_email(args.email.lower())
        if user is None:
            print(f"error: user '{args.email}' does not exist", file=sys.stderr)
            return 1
        if args.command == "set-password":
            await container.password_service().set_password(user, password)
            print(f"password set: {user.email}")
        else:
            is_admin = args.command == "grant-admin"
            await container.user_repository().set_admin(user.id, is_admin)
            print(f"administrator {'granted' if is_admin else 'revoked'}: {user.email}")
        return 0

    if args.command == "eval":
        user = await container.user_repository().get_by_email(args.email.lower())
        if user is None:
            print(f"error: user '{args.email}' does not exist", file=sys.stderr)
            return 1
        dataset = read_dataset(Path(args.dataset))
        overrides = {}
        if args.trigram_weight is not None:
            overrides["recall_trigram_weight"] = args.trigram_weight
        if args.importance_weight is not None:
            overrides["recall_importance_weight"] = args.importance_weight
        if args.usage_weight is not None:
            overrides["recall_usage_weight"] = args.usage_weight
        if args.freshness_weight is not None:
            overrides["recall_freshness_weight"] = args.freshness_weight
        if args.vector_min_similarity is not None:
            overrides["recall_vector_min_similarity"] = args.vector_min_similarity
        if overrides:
            # Same graph, one knob turned: the configured limits with the
            # overrides applied, so an A/B differs only in what was asked.
            service = MemoryService(
                repository=container.memory_repository(),
                embeddings=container.embedding_client(),
                limits=get_settings().limits.model_copy(update=overrides),
            )
        else:
            service = container.memory_service()
        try:
            report = await run_eval(service, user.id, dataset, k=args.k)
        except EmbeddingError as exc:
            print(f"error: embeddings unavailable ({exc}); is Ollama running?", file=sys.stderr)
            return 1
        report.tunables = overrides
        print(render_report(report))
        return 0

    if args.command == "hygiene":
        user = await container.user_repository().get_by_email(args.email.lower())
        if user is None:
            print(f"error: user '{args.email}' does not exist", file=sys.stderr)
            return 1
        min_similarity = args.min_similarity
        if min_similarity is None:
            min_similarity = get_settings().limits.similar_min_similarity
        report = await build_hygiene_report(
            container.memory_repository(),
            user.id,
            min_similarity=min_similarity,
            limit=args.limit,
        )
        print(render_hygiene_report(report))
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

    if args.command == "bootstrap":
        user = await container.user_repository().get_by_email(args.email.lower())
        if user is None:
            print(f"error: user '{args.email}' does not exist", file=sys.stderr)
            return 1
        if not args.path.is_dir():
            print(f"error: path '{args.path}' is not a directory", file=sys.stderr)
            return 1
        scan = scan_project(args.path)
        if not scan.candidates:
            print("no candidates found")
            return 0
        if not args.apply:
            for candidate in scan.candidates:
                print(f"[{candidate.category}] ({candidate.source_ref}) {candidate.content}")
            if scan.omitted:
                print(
                    f"note: {scan.omitted} lower-priority candidate(s) omitted "
                    f"(cap is {MAX_CANDIDATES})",
                    file=sys.stderr,
                )
            return 0
        items = [
            RememberBatchItem(
                content=candidate.content,
                category=candidate.category,
                project=args.project,
                source_type="bootstrap",
                source_ref=candidate.source_ref,
            )
            for candidate in scan.candidates
        ]
        try:
            result = await container.memory_service().remember_batch(user.id, items=items)
        except MemoryValidationError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        for candidate, outcome in zip(scan.candidates, result.results, strict=True):
            if outcome.error is not None:
                print(f"error: ({candidate.source_ref}) {outcome.error}", file=sys.stderr)
                continue
            status = "created" if outcome.created else "deduplicated"
            print(f"{status}: [{candidate.category}] ({candidate.source_ref}) {candidate.content}")
            if outcome.created:
                if outcome.similar:
                    similar_ids = ", ".join(str(similar.id) for similar in outcome.similar)
                    print(f"  similar: {similar_ids}")
                if outcome.language_warning:
                    print(f"  warning: {outcome.language_warning}")
        print(f"stored={result.stored} deduplicated={result.deduplicated} failed={result.failed}")
        if scan.omitted:
            print(
                f"note: {scan.omitted} lower-priority candidate(s) omitted "
                f"(cap is {MAX_CANDIDATES})",
                file=sys.stderr,
            )
        return 0

    return 2  # pragma: no cover - argparse enforces known commands


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    container = create_container(get_settings())

    async def _lifecycle() -> int:
        await init_container_resources(container)
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
