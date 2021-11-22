#!/bin/bash -u
root=`dirname $0`
num_files_checked=0
declare -a files_to_check=()

echo "INFO: starting pylint tests"
files_to_check=($(git ls-files '*.py'))
files_to_check+=($(git ls-files --others --exclude-standard '*.py'))
num_files_checked=${#files_to_check[@]}

pylint --rcfile=${root}/.pylintrc ${files_to_check[@]}
rc=$?
echo -e "INFO: $num_files_checked python files checked with pylint."
exit $rc
