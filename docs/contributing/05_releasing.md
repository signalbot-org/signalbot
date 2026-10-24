---
title: Releasing
---

Releases are automated: pushing a version tag builds the package, publishes it to PyPI, creates the
GitHub release and deploys the documentation.
This page is for maintainers with push access to the
repository.

## Versioning

The package version is not written anywhere in the repository.
It is taken from the git tag at build time by [uv-dynamic-versioning](https://github.com/ninoseki/uv-dynamic-versioning), so tagging a
commit with `v2.2.0` builds signalbot `2.2.0`.
Untagged commits build as a development version of the next patch release, e.g. `2.2.1.dev3+1a2b3c4`.

Versions follow [semantic versioning](https://semver.org/) and are worked out from the
[conventional commit](https://www.conventionalcommits.org/) prefixes since the last tag by
[git-cliff](https://git-cliff.org/): a breaking change (a `!` after the type, e.g. `feat!:`, or a
`BREAKING CHANGE:` footer) bumps the major version, a `feat:` the minor version and anything else the patch
version.

## Steps

1. **Tag the release and push the tag.**
    ```bash
    git switch main
    git pull
    TAG=$(uv run --only-group release git-cliff --bumped-version) && git tag "$TAG" && git push origin "$TAG"
    ```
    To see the tag and the release notes before pushing, run these on their own:
    ```bash
    uv run --only-group release git-cliff --bumped-version
    uv run --only-group release git-cliff --body-file .github/release-notes.md.tera --unreleased --bump
    ```
    Set `GITHUB_TOKEN` (e.g. `GITHUB_TOKEN=$(gh auth token)`) to fill in the PR authors and links as in CI.

2. **Approve the PyPI deployment.** The
   [Release Package](https://github.com/signalbot-org/signalbot/actions/workflows/release.yaml) workflow runs CI and checks that the built version matches the tag.
   Publishing to [pypi.org](https://pypi.org/project/signalbot/) then waits for a maintainer to approve the `pypi.org` environment in the workflow run.

3. **Check the GitHub release.** Once the package is on PyPI, the workflow creates the [GitHub release](https://github.com/signalbot-org/signalbot/releases) with notes generated from the commits since the previous tag.
   Edit the notes on GitHub if anything needs adding.

4. **Check the documentation.** Last, the workflow deploys the [docs](https://signalbot-org.github.io/signalbot/) for the new version and points `latest` at it.

## Release notes

The notes group commits by their [conventional commit](https://www.conventionalcommits.org/) prefix.
PRs to `main` are squash merged, with the PR title as the commit title and the PR description as the commit
body, so each PR is one entry in the notes.
The [PR title](https://github.com/signalbot-org/signalbot/actions/workflows/pr-title.yaml) check makes sure the
title has a prefix, i.e. one of `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`,
`style` or `test`, with an optional scope and `!`:

| Commit prefix                   | Section                  |
| ------------------------------- | ------------------------ |
| `feat:`                         | New features             |
| `fix:`                          | Bug fixes                |
| `docs:`                         | Documentation            |
| `chore(deps):`                  | Dependencies             |
| `chore(deps-dev):`              | Dev dependencies         |
| Anything else, or no prefix     | Other changes            |

Breaking changes are marked **Breaking:** in their section.
To tell users how to migrate, end the PR description with a `BREAKING CHANGE:` footer, after the checklist.
Its text is added to the notes under the entry; anything after it would be added too, so keep it last:

```markdown
- [x] The prek checks pass `uv run prek run --all-files`

BREAKING CHANGE: `context.send` is now `context.reply`.
Rename every call, e.g. `context.send("hi")` becomes `context.reply("hi")`.
```

The sections are set in the `[tool.git-cliff]` section of
[`pyproject.toml`](https://github.com/signalbot-org/signalbot/blob/main/pyproject.toml) and the notes template
in [`.github/release-notes.md.tera`](https://github.com/signalbot-org/signalbot/blob/main/.github/release-notes.md.tera).
