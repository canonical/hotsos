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

In order reduce/remove the need to carry metadata such as search definitions in
code, they are instead stored as yaml. Currently we have the following yaml
definitions categories:

* bugs - Defines search criteria used to identify bugs in files. Includes
         information such as search expression and output message. These
         searches do not require accompanying code and are run automatically
         per plugin. See yaml file for full description. 

* events - Defines search criteria used to identify events in files. Events
           can be characterised as single or multi-line with the latter
           referred to in hotsos as a "sequence". Events are defined as a
           search expression used to identify them and are accompanied by a
           callback method in plugin code that is used to perform some
           operation on the information retreived.  See yaml file for full
           description.

* config_checks - Defines criteria for indentifying invalid application
                  configuration. See yaml file for full description. 
 
* package\_bug\_checks - Defines criteria for identifying whether installed
                         packages contain known bugs. See yaml file for full
                         description.

* plugins - This is the high level Python plugin driver as is consumed by
            core.plugintools.PluginRunner as a means of knowing how to execute
            a plugin.

### core

This is the home for shared code and includes plugin-specific shared code such
as application primitives as well as hotsos core code.

### plugins

This is where plugins are implemented. A plugin comprises of a high level
eponymous directory containing any number of executable plugin "parts" which
are a way of breaking down the structure of the plugin using meaningfully named
files.

### tests

All code should be accompanied by unit tests and this is where they live. Tests
are run using tox which is run automatically on every push to the repository.
