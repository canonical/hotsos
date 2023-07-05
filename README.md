# Hotsos

Use hotsos to implement repeatable analysis and extract useful information from common cloud applications and subsystems. Write analysis Scenarios using a high-level language, leveraging Python helper libraries to extract information. A catalog of analysis implementations is included.

The code is organised as “plugins” that implement functionality specific to an application or subsystem. Hotsos is run against a “data root” which can be a host i.e. ‘/’ or a sosreport. The output is a summary containing key information from each plugin along with any issuses or known bugs detected and suggestions on what actions can be taken to handle them.

## Documentation

Installation and Usage: https://hotsos.readthedocs.io/en/latest/install/index.html

Contributing: https://hotsos.readthedocs.io/en/latest/contrib/index.html

Full documentation: https://hotsos.readthedocs.io/en/latest/
