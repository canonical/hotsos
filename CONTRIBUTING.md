# Contributing to hotsos

Hotsos comprises a set of plugins that collect and analyse host and
application-specific data.

Plugin implementations are split across two areas; yaml checks and python
extensions. The yaml checks (defs) are a way to define analysis in a high-level
language with the option to leverage python code (core) and the extensions are
a way to implement functionality like summary output. All output is collected
and output by default as yaml in a "summary".

## Key Components

### defs

This directory contains yaml-defined checks and analysis. See the
[README](hotsos/defs/README.md) for more information.

### core

This is the home for shared code and includes plugin-specific shared code such
as application primitives and hotsos core code.

### plugin_extensions

This is where plugin extensions are implemented. Each plugin has an eponymous
directory containing code that can be executed by the client.

Plugin output format defaults to yaml but can be changed using the `--format`
command line option to one of 'yaml', 'json', 'markdown', 'html'. There are
tools provided to manage this for you (see `core.plugintools`) and the basic
workflow is that plugin extensions are a set of one or more implementations of
`plugintools.PluginPartBase`. Once all plugins are run, their respective outputs
are aggregated into a master yaml "summary".

Parts that produce output can do so in one of two ways; either by implementing a
class property called `summary()` which will put the returned data at the plugin
root in the summary or alternatively can implement properties with name e.g.
`__summary_<key>()` which will put the returned data in the summary under
`<plugin>.<key>`.

Some implementations may not produce output directly and instead raise "issues"
using the tools in `core.issues`. These ultimately translate to yaml as well but
again this is dealt with automatically.

IMPORTANT: do not print anything directly to standard output.

### tests

All code should be accompanied by unit tests and this is where they live. Tests
are run using tox which is run automatically on every push to the repository.
