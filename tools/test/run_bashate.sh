#!/bin/bash

set -e -u

bashate --verbose $(git ls-files \*.sh)
