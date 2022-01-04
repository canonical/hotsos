# Contributing to hotsos

Hotsos comprises a set of plugins that collect and analyse application-specific
data. While all plugins and library code are currently written in Python, they
are not necessarily constrained to this as long as their output meets the
standard requirements (see plugins section). It is nevertheless recommended to
write plugins in Python so as to be able to leverage the (core) library code
and unit test facilities.

As a matter of principle, the aim should always be that plugin implementations
contain the least possible code and anything that can be implemented as
shared code should go into the core library code (see core section).

## Key Components:

### defs

This directory contains yaml-defined checks and analysis. See the
[README](defs/README.md) for more information.

### core

This is the home for shared code and includes plugin-specific shared code such
as application primitives as well as hotsos core code.

### plugins

This is where plugins are implemented. A plugin comprises of a high level
eponymous directory containing any number of executable plugin "parts" which
are a way of breaking down the structure of the plugin using meaningfully named
files.

Plugin output must be yaml-formatted. There are tools provided to manage this
for you (see core.plugintools) and the basic workflow is that each plugin part
implement a plugintools.PluginPartBase and is assigned a YAML_PRIORITY which
determines its position within the plugin output. Once all plugins are run,
their respective yaml outputs are aggregated into a master yaml "summary".

Parts that produce output need simply add it to the _output variable or
override the output (dict) property and the rest is taken care of for you.

Some implementations may not produce output directly and instead raise "issues"
using the tools in core.issues. These ultimately translate to yaml as well but
again this is dealt with automatically.

NOTE: do not print anything to standard output.

### tests

All code should be accompanied by unit tests and this is where they live. Tests
are run using tox which is run automatically on every push to the repository.
