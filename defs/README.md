# YAML Defs

This directory contains the configuration for yaml-defined analysis.

At present the following types of definitions are provided each with an
associated handler:

 * events
 * bugs
 * config_checks
 * scenarios

See core.ycheck for details on the implementation of each.

The type of definitions is characterised by the their top-level directory name
which corresponds to the handler used to process them.

These definitions provide a way to write checks and analysis with a minimum of
(Python) code. It also has the benefit that we don't need to maintain
check-specific code or metadata in Python code. A tree structure is used and
generally looks like:

```
<def-type>
  <plugin-name>
    <optional-group-name>
      <defs-name>
```

 * first subdirectory must use the name of the plugin the checks belong to e.g.
   openstack
 * the next level contains definitions which can be organised using any
   combination of files and directories e.g. you could put all definitions in
   a single file or you could have one file per definition. You can then use
   directories to logically group your definitions or you can use a tree
   structure within any of the files.
 * this structure uses the format provided by *github.com/dosaboy/ystruct*
   i.e. a tree where each level contains *overrides* and "content". Overrides
   follow an inheritance model so that they can be defined and superseded at
   any level. The content is always found at the leaf nodes of the tree.
 * it should always be possible to transpose the filesystem tree structure to
   a single (file) yaml tree.

TIP: to use a single quote ' inside a yaml string you need to replace it with
     two single quotes.

## Overrides

Overrides are blocks of yaml with a pre-defined meaning. They are used to
provide specific information or structure and must be supported by the
associated handler.

Overrides abide by rules of inheritance and can be defined at any level. They
are accessed at a leaf and can be defined and overridden at any level. Since
definitions can be organised using files and directories, the latter requires a
means for applying directory globals. To achieve this we put the overrides into
a file that shares the name of the directory e.g.

```
pluginX/groupA/groupA.yaml
pluginX/groupA/scenarioA.yaml
pluginX/groupA/scenarioB.yaml
pluginX/groupA/groupB
```

Here groupA and groupB are directories and groupA.yaml defines overrides that
apply to everything under groupA.

### Properties

The following are property overrides available to all types of
definitions provided that their handler supports them. The format section
describes how they can be used in yaml definitions and the usage section
describes how they are consumed in (Python) code i.e. the handlers.

#### config
Defines a config checker. The handler is normally a plugins' implementation of
core.checks.SectionalConfigBase.

##### format
```
config:
  handler: config.handler.import.path
  path: <relative path to config file>
```

##### usage
```
config.actual(key, section=None)
config.check(actual, value, op, allow_unset=False):
```

#### context
Defines a dictionary of settings. This is typically defined at a high point in
the tree so that all branches beneath it use as common context. The
structure/content of this dictionary is handler-specific.

##### format
```
context:
  <key>: <val>
  ...
```

##### usage
```
context.<param>
```

#### decision
Defines a decision as a list of logical operators each associated with a list
of one or more check labels as defined in a *checks* subdef. This property is
typically used in a *conclusions* subdef.

##### format
```
decision:
  and|or: [check1, ...]
```

##### usage
```
<iter>
```

#### input
Defines a type of input. Currently we support a filesystem path or command.
When a command is provided, the output of that command is written to a
temporary file the path of which is returned by input.path. Supported commands
are those provided by core.cli_helpers.CLIHelper.

##### format
```
input:
  type: filesystem|command
  value: <path or command>
  meta:
    # (optional) used with type=filesystem. defines whether to apply
    #            USE_ALL_LOGS to path.
    allow-all-logs: True
    # (optional) used with type=command. The following are used as
    #            input to command.
    args: []
    kwargs: {}
    # (optional) used with type=command. This will be called and the
    #            return is expected to be a tuple of <list>, <dict>
    #            that are used as input to command.
    args-callback: None
```

##### usage
```
input.path
```

#### priority
Defines an integer priority.

##### format
```
priority:
  <int>
```

##### usage
```
int(priority)
```

#### raises
Defines the issue or message we want to raise. For example a check may want to
raise an issue using type core.issues.issue_types.Foo with a message that is
created using a template and some format input based on the results of a search
(see *expr* property).

##### format
```
raises:
  type: core.issues.issue_types.<type>
  message: <str>
  format-dict: <dict>
  format-groups: [<int>, ...]
```

##### usage
```
raises.type
raises.message
raises.format_dict
raises.format_groups
```

#### requires
Defines a set of requirements with a pass/fail result. Typically used a way to
determine whether or not to run a check.

Can be defined as single requirement or sets of requirements grouped by a
logical operator used to determine the result of the group. If multiple groups
are used, their results are ANDed together to get the final result for
*passes*. 


##### format
```
requires:
  TYPE: INPUT
  value: <value>  (optional)
  op: <operator> ([python operator](https://docs.python.org/3/library/operator.html). default is eq.)

  or

  LOGICAL_OPERATOR:
    - TYPE: INPUT
      value: <value>  (optional)
      op: <operator>
    - ...

LOGICAL_OPERATOR
  and
    AND is applied to group.

  or
    AND is applied to group.

  not
    NOT(OR) is applied to group.

  AND is then applied to results of all groups.

TYPE
  property
    INPUT is a Python import path for a property that will be called
    and optionally matched against a provided value: otherwise True. 

  apt
    INPUT is an apt package name. Returns True if package exists
    otherwise False.

  snap
    INPUT is a snap package name. Returns True if package exists
    otherwise False.

  systemd
    INPUT is a systemd service name. Returns True if service exists
    and a service status can be optionally checked using value: in
    which case a match is required to get True.

```

##### usage
```
requires.passes
```

#### settings
Defines a group of settings. Implementation is handler-specific. Settings are
retrieved by iterating over the result.

##### format
```
settings:
  <dict>
```

##### usage
```
iter(settings)
```

### expr|hint|start|body|end
Defines a search expression. There are different types of search expression
that can be used depending on the data being searched and how the results will
be interpreted. For example a "simple" search involves a single expression and
is used to match single lines. A "sequence" search is using with
core.filesearcher.SequenceSearchDef to match (non-overlapping) sequences and
then there is also support for analysis overlapping sequences with
core.analytics.LogEventStats.

An optional passthrough-results key is provided and used with events type
definitions to indicate that search results should be passed to
their handler as a raw core.searchtools.SearchResultsCollection. This is
typically so that they can be parsed with core.analytics.LogEventStats.
Defaults to False.

##### format
```
expr|hint: <str>

start|body|end:
  expr: <int>
  hint: <int>

passthrough-results: True|False
```

##### usage
```
If value is a string:
  str(expr|hint)

If using keys start|body|end:
  <key>.expr
  <key>.hint

Note that expressions can be a string or list of strings.
```

### Subdefs

Subdefs are used as a way to define a sub section of definitions that
are to be treated independently of the rest. This is a way to create a complex
override that is itself comprised of one or more overrides.

#### checks
This indicates that everything beneath is a set of one or more checks to be
used by core.ycheck.scenarios. The contents of this override are defined as a
dictionary of checks labelled with meaningful names that will be used to
reference their outcome when defining *decision* overrides e.g. inside
a *conclusions* subdef.

A check can support any override as long as it is supported by the handler used
to process them. See *Scenarios* section for more info and examples.

```
checks:
  check1:
    <content>
  check2:
    <content>
  ... 
```

#### conclusions
This indicates that everything beneath is a set of one or more conclusions to
be used by core.ycheck.scenarios. The contents of this override are defined as
a dictionary of conclusions labelled with meaningful names.

A conclusion is defined as a function on the outcome of a set of checks along
with the consequent behaviour should the conclusion match. This is defined as
an issue type and message that will be raised. If multiple conclusions are
defined, they are given a priority such that the highest one to match is the
one that is executed. See *Scenarios* section for more info and examples.

The message can optionally use format fields which, if used, require
format-dict to be provided with required key/value pairs. The values must be
an importable attribute, property or method. 

```
conclusions:
  <name>:
    priority: <int>
    decision:
      and|or: [check1, ...]
    raises:
      type: <import-path>
      message: <formattable string>
      format-dict:
        <key>: <value>
```

## Handlers

### Events

These checks are not currently run automatically and do require custom
callbacks to be implemented in plugin code to process results.

An event can be single or multi-line and the data source is defined with an
*input* property. All event checks must have an eponymous callback
method defined in the plugin that handles them.

To define an event first create a file with the name of the check(s) you
want to perform under the directory of the plugin you are using to handle the
event callback.

Supported properties
  * input
  * expr
  
Supported subdefs
  * none

Examples

Two types of searches are available here; single or multi line. A multi-line
search can be used in two ways; the first use is simply to have a "start" and
"end" expression and the results will have -start and -end appended to their
tags accordingly and the second use is to define a sequence which requires at
least a "start" and "body" with optional "end". Sequences are processed using
searchtools.SequenceSearchDef and all other searches use
searchtools.SearchDef. Single line search is defined using the "expr" key.

A single-line search on a file:

```
myeventname:
  input:
    type: filesystem
    value: path/to/my/file
  expr: <re.match pattern>
  hint: optional <re.match pattern> used as a low-cost filter
```

A multi-line search on a file:

```
myeventname:
  input:
    type: filesystem
    value: path/to/my/file
  start:
    expr: <re.match pattern>
  end:
    expr: <re.match pattern>
```

A sequence search on a file:

```
myeventname:
  input:
    type: filesystem
    value: path/to/my/file
  start:
    expr: <re.match pattern>
  body:
    expr: <re.match pattern>
  end:
    expr: <re.match pattern>
```


### Bugs

These checks are run automatically and do not require implementing in plugin
code.

Each plugin can have an associated set of bugs to identify based on the
contents of files, output of commands or versions of installed packages and can
use any combination of these. If package version info is checked and the
package is not installed, any other checks are skipped for that bug. 

Supported properties
  * input
  * expr
  * raises
  * context
  * settings - see SETTINGS
  
Supported subdefs
  * none

```
SETTINGS
  package
    Name of package we want to check. Context must provide apt-all.

  versions-affected
    List of dicts. If a package name is provided we can check its
                   version to see if it contains the bugfix. Each
                   element contains the following:
      min-fixed - minimum version of the package that contains the fix.
      min-broken - minimum version of the package that contains the
                   bug.
```

### Config checks

These checks are run automatically and do not require implementing in plugin
code.

Each plugin can define a set of bugs to identify by searching for a
pattern either in a file/path or command output. When a match is found, a
message is displayed in the 'known-bugs' section of a plugin output.

Supported properties
  * requires
  * config
  * settings - see SETTINGS
  * raises
  
Supported subdefs
  * none

```
SETTINGS
  section - Optional config file section name.
  op - [python operator](https://docs.python.org/3/library/operator.html) to apply. Default is eq.
  value - Expected value.
  allow-unset - Whether the config may be unset. Default is False.
```

### Scenarios

These checks are run automatically and do not require implementing in plugin
code.

Each plugin can define a set of scenarios whereby a scenario comprises of a set
of *checks* and *conclusions*. Each check is executed independently and
conclusions are defined as decision based on the outcome of one or more checks.
Conclusions can be given priorities so that one can be selected in the event of
multiple positives. This is helpful for defining fallback conclusions.

Supported properties
  * none
  
Supported subdefs
  * checks
  * conclusions
