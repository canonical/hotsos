#!/bin/bash -eu

files_to_check=($(git ls-files '*.sh'| grep -v fake_data_root || true))
files_to_check+=($(git ls-files --others --exclude-standard '*.sh'| \
                    grep -v fake_data_root || true))

echo ${files_to_check[@]}
bashate --verbose ${files_to_check[@]}
