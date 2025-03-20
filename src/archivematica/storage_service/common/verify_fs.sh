#! /bin/bash

set -e

if [ "$#" -ne 1 ];
then
    echo "Usage: $0 <path_to_verify>"
    exit 1;
fi
path=$1
test_file=$path/test_file
touch $test_file 2>/dev/null
echo "Test content" > $test_file 2>/dev/null
rm $test_file 2>/dev/null
