#!/bin/bash -u
root=`dirname $0`
num_files_checked=0
num_errors_found=0
dirs=( $@ )
declare -a files_to_check=()

echo "INFO: starting pylint tests"
for dir in ${dirs[@]}; do
    for f in `find $dir -type f`; do
        if `file $f| grep -q "Python script"`; then
            files_to_check+=( $f )
            ((num_files_checked+=1))
        fi
    done
done
pylint --rcfile=${root}/.pylintrc ${files_to_check[@]}
rc=$?
echo -e "INFO: $num_files_checked python files checked with pylint."
exit $rc
