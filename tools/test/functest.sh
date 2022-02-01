#!/bin/bash
ftmp=`mktemp`
${HOT_DIR}/hotsos.sh ./tests/unit/fake_data_root > $ftmp
diff examples/hotsos-example.summary.yaml $ftmp
exit $?

