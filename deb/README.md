# Daily Debian Builds

Daily debian builds are provided in https://code.launchpad.net/~ubuntu-support-team/+archive/ubuntu/hotsos as an alternative to the builds in [pypi](https://pypi.org/project/hotsos)

This directory contains config used by the daily deb builder. The builder uses [git-build-recipe](https://launchpad.net/git-build-recipe) and is configured by https://code.launchpad.net/~ubuntu-support-team/+recipe/hotsos. The git-build-recipe tool does not yet support pyproject.toml so we have to provide these setuptools equivalent configs that must be kept up-to-date with changes made to the former.

