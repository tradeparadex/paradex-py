# paradex-py

[![Release](https://img.shields.io/github/v/release/tradeparadex/paradex-py)](https://img.shields.io/github/v/release/tradeparadex/paradex-py)
[![Build status](https://img.shields.io/github/actions/workflow/status/tradeparadex/paradex-py/main.yml?branch=main)](https://github.com/tradeparadex/paradex-py/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/tradeparadex/paradex-py/branch/main/graph/badge.svg)](https://codecov.io/gh/tradeparadex/paradex-py)
[![Commit activity](https://img.shields.io/github/commit-activity/m/tradeparadex/paradex-py)](https://img.shields.io/github/commit-activity/m/tradeparadex/paradex-py)
[![License](https://img.shields.io/github/license/tradeparadex/paradex-py)](https://img.shields.io/github/license/tradeparadex/paradex-py)

Paradex Python SDK

- **Github repository**: <https://github.com/tradeparadex/paradex-py/>
- **Documentation** <https://tradeparadex.github.io/paradex-py/>

## Commands

```bash
make install
make check
make test
make build
make clean-build
make publish
make build-and-publish
make docs-test
make docs
make help
```

The CI/CD pipeline will be triggered when you open a pull request, merge to main, or when you create a new release.

To finalize the set-up for publishing to PyPi or Artifactory, see [here](https://fpgmaas.github.io/cookiecutter-poetry/features/publishing/#set-up-for-pypi).
For activating the automatic documentation with MkDocs, see [here](https://fpgmaas.github.io/cookiecutter-poetry/features/mkdocs/#enabling-the-documentation-on-github).
To enable the code coverage reports, see [here](https://fpgmaas.github.io/cookiecutter-poetry/features/codecov/).

## Releasing a new version

- Create an API Token on [Pypi](https://pypi.org/).
- Add the API Token to your projects secrets with the name `PYPI_TOKEN` by visiting [this page](https://github.com/tradeparadex/paradex-py/settings/secrets/actions/new).
- Create a [new release](https://github.com/tradeparadex/paradex-py/releases/new) on Github.
- Create a new tag in the form `*.*.*`.

For more details, see [here](https://fpgmaas.github.io/cookiecutter-poetry/features/cicd/#how-to-trigger-a-release).
