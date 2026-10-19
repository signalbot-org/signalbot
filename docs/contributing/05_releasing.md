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

Versions follow [semantic versioning](https://semver.org/): bump the major version for breaking changes, the minor version for new features and the patch version for bug fixes.

## Steps

1. **Tag the release and push the tag.**
    ```bash
    git switch main
    git pull
    git tag v2.2.0
    git push origin v2.2.0
    ```

2. **Approve the PyPI deployment.** The
   [Release Package](https://github.com/signalbot-org/signalbot/actions/workflows/release.yaml) workflow runs CI and checks that the built version matches the tag.
   Publishing to [pypi.org](https://pypi.org/project/signalbot/) then waits for a maintainer to approve the `pypi.org` environment in the workflow run.

4. **Check the GitHub release.** Once the package is on PyPI, the workflow creates the [GitHub release](https://github.com/signalbot-org/signalbot/releases) with notes generated from the titles of the merged PRs.
   Edit the notes on GitHub if anything needs adding, e.g. migration steps for breaking changes.

5. **Check the documentation.** Last, the workflow deploys the [docs](https://signalbot-org.github.io/signalbot/) for the new version and points `latest` at it.

## Release notes

The notes group PRs by the [conventional commit](https://www.conventionalcommits.org/) prefix of their
title, so give PRs a prefix before merging them:

| PR title prefix                 | Section                  |
| ------------------------------- | ------------------------ |
| `feat:`                         | New features             |
| `fix:`                          | Bug fixes                |
| `docs:`                         | Documentation            |
| `chore(deps):`                  | Dependencies / Main      |
| `chore(deps-dev):`              | Dependencies / Dev       |
| Anything else, or no prefix     | Other changes            |

The grouping is done by
[`.github/scripts/release_notes.py`](https://github.com/signalbot-org/signalbot/blob/main/.github/scripts/release_notes.py).
