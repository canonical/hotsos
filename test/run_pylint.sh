#!/bin/bash -u
root=`dirname $0`
num_files_checked=0
num_errors_found=0
dirs=( $@ )

echo "INFO: starting pylint tests"
for dir in ${dirs[@]}; do
    for f in `find $dir -type f`; do
        if `file $f| grep -q "Python script"`; then
            pylint $f --errors-only
            (($?)) && ((num_errors_found+=1))
            ((num_files_checked+=1))
        fi
    done
done
echo -e "INFO: $num_files_checked python files checked with pylint. $num_errors_found file(s) found with errors."
((num_errors_found)) && exit 1 || exit 0
