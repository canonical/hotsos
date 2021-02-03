#!/bin/bash -u
root=`dirname $0`
num_files_checked=0
num_errors_found=0

for f in `find plugins/ -type f`; do
    if `file $f| grep -q "Python script"`; then
        flake8 $f
        (($?)) && ((num_errors_found+=1))
        ((num_files_checked+=1))
    fi
done
echo -e "\nINFO: $num_files_checked files checked. $num_errors_found file(s) found with errors."
