---
name: release
description: "Release: tag and publish with gh, writing English notes from the commits since the last tag. Use when the user wants to cut a release, publish or tag a version, or wants release notes or a changelog generated from commit history."
---

# Release

Cut a tagged GitHub release whose notes come from the commits since the last one. `gh release create` makes the tag itself from `--target`, so there is no separate `git tag` step.

## 1. Establish the baseline

Local tags go **stale**: a tag can exist on the remote and be invisible locally, turning "there is no previous release" into a false premise. Fetch before looking.

```sh
git fetch --tags origin
git tag --sort=-creatordate | head -5
```

The **baseline** is the most recent release tag. With no tag anywhere, this is the first release and the baseline is the root commit (`git rev-list --max-parents=0 HEAD`).

**Done when** you can name the baseline ref and state what `git rev-list --count <baseline>..HEAD` returns.

A count of 0 means the baseline already points at `HEAD` and there is nothing new to tag. Say so and stop — unless uncommitted work is meant to ship, which you commit first.

## 2. Confirm the target is publishable

A release points at a commit the remote already has. Publish from a clean tree that is fully pushed.

```sh
git status --short
git rev-list --count origin/<branch>..HEAD
```

**Done when** the tree is clean and the ahead-count is 0.

## 3. Reconcile the version

The tag and the version declared in the code must agree, or the release **drifts** from what it ships.

Set every file that declares the version to the version you are about to tag — `pyproject.toml`, `package.json`, `Cargo.toml`, app metadata — and regenerate any lockfile that embeds it rather than hand-editing. In this repo the version is declared in **three** places: `pyproject.toml`, the hand-declared `recallum/__init__.py` `__version__`, and the generated `uv.lock`. Edit the first two; for the lock, after editing `pyproject.toml` always run

```sh
uv sync
```

and commit `uv.lock` **in the same bump commit** as `pyproject.toml`. Skipping this leaves the lock stale, and the very next `uv run` regenerates it as an uncommitted side effect — the drift then surfaces as a dirty tree in whatever unrelated work comes later (this bit v0.7.0, whose bump commit shipped a `uv.lock` still claiming 0.6.1).

A tag that already exists forces a bump; pick the level from what actually changed, treating a behaviour change as minor pre-1.0 and major after.

The plugin is a **second, independently versioned artifact**. If anything under `plugins/recallum-memory/` changed since the baseline (`git diff --stat <baseline>..HEAD -- plugins/`), bump the version in every version-bearing client manifest — `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `plugin.json`, and `.cursor-plugin/plugin.json` — and in the version-bearing Grok marketplace/index entries. Cursor's marketplace entry has no version field in its official schema, so do not add one. Keep all declared versions equal; `test_all_client_manifests_describe_the_same_plugin_release` enforces manifest parity. Client update flows key off these versions: shipping changed plugin content under an unchanged version means users never see the update.

**Done when** every version-declaring file states the tag's version, a changed plugin carries a bumped version in every version-bearing client manifest/catalog, `git status` shows no lockfile drift after a `uv run` command, and the test suite still passes (`tests/unit/test_app.py` pins that the app's public version matches the package metadata).

## 4. Read the commits

```sh
git log <baseline>..HEAD --format="%h %s%n%b"
```

Read the bodies, not just the subjects — the reasoning worth putting in notes usually lives there. Where history was squashed, read the diff too.

**Done when** every commit in the range is either represented in the notes or deliberately left out.

## 5. Write the notes

Write them in **English**, whatever language the conversation is in, for a reader who was not in it.

Lead with **what breaks**. Someone upgrading asks first whether anything shifts under them, so behaviour changes come before features and architecture:

- **Behaviour changes** — what a caller observes differently, stating the old behaviour and the new.
- **Features / architecture** — what was added or reshaped.
- **Fixes** — what was broken.
- **Known gaps** — anything shipped unverified, and limitations you are aware of.
- Compare link: `https://github.com/<owner>/<repo>/compare/<baseline>...<tag>`

**Done when** a reader who never saw the work knows whether upgrading changes anything for them.

## 6. Publish

```sh
gh release create <tag> --title "<tag> — <what changed>" --notes-file <file> --target <branch>
gh release view <tag> --json tagName,isDraft,targetCommitish
```

Give the user the release URL. A release is reversible with `gh release delete <tag> --cleanup-tag` — mention that whenever the version or the notes were a judgement call.
