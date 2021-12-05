# YAML Defs

This directory contains the configuration for yaml-defined analysis.

At present the following types of definitions are provided:

 * events
 * bugs
 * config_checks
 * packages_bug_checks
 * scenarios

See core.ycheck for details on the implementation of each.

The type of definitons is characterised by the their top-level directory name
which corresponds to the handler used to process them.

These definitions are used as a way to execute checks and analysis based on an
absolute minimum of code. In other words the majority of contributions should
not require any code other than yaml. A tree structure is used and generally
looks like:

```
<def-type>
  <plugin-name>
    <optional-group>
      <defs-name>
```

 * first subdirectory must use the name of the plugin the checks belong to e.g.
   openstack
 * the next level contains definitions which can be organised using any
   combination of files and directories e.g. you could put all definitions in
   a single file or you could have one file per definition. You can then use
   directories to logically group your defintions or you can use a tree
   structure within any of the files.
 * this structure uses the format provided by github.com/dosaboy/ystruct
   i.e. a tree where each level contains "overrides" and "content". Overrides
   follow an inheritance model so that they can be defined and supersceded at
   any level. The content is always found at the leaf nodes of the tree.
 * it should always be possible to transpose the filesystem tree structure to
   a single (file) yaml tree.

Overrides can be defined at any level in the tree and apply to all
definitions both at the same level and below. Since we have the means to define
this within a single file or using directory to group definitions, the latter
approach means the overrides will need to be in their own file and we therefore
need a way to identify that they apply to all peers and below. To achieve this
we put the overrides into a file that has the same name as their parent
directory e.g.

```
pluginX/groupA/groupA.yaml
pluginX/groupA/scenarioA.yaml
pluginX/groupA/scenarioB.yaml
pluginX/groupA/groupB
```

where the overrides defined in groupA.yaml will apply to scenarioA.yaml,
scenarioB.yaml (as long as they don't define overrides of the same type) and
any definitions under groupB.

TIP: to use a single quote ' inside a yaml string you need to replace it with
     two single quotes.

## Overrides

The following overrides are available to all types of definitions. The params
section described how they can be used in yaml definitions and the usage section
describes how they are consumed in (Python) code.

#### checks
This is a meta definition to indicate that everything beneath it is a tree of
checks to be used by core.ycheck.scenarios.

```
params:
  none

usage:
  checks
```

#### conclusions
This is a meta definition to indicate that everything beneath it is a tree of
conclusions to be used by core.ycheck.scenarios.

```
params:
  none

usage:
  conclusions
```

#### config
Defines a config checker. The handler is normally a plugins' implementation of
core.checks.SectionalConfigBase.

```
params:
  handler: <config-handler>
  path: <config-path>

usage:
  config.actual(key, section=None)
  config.check(actual, value, op, allow_unset=False):
```

#### context
Defines a dictionary of settings. This is  typically defined at a high point in
the tree so that all branches beneath it use as common context. The
structure/content of this dictionary is handler-specific.

```
params:
  <dict>

usage:
  context.<param>
```

#### decision
Defines a decision as a list of boolean operators each associated with a list
of one or more check results.

```
params:
  <bool>: [checkresult, ...]

usage:
  <iter>
```

#### input
Defines a type of input. Currently we support a fileysystem path or command.
When a command is provided, the output of that command is written to a
temporary file the path of which is returned by input.path.

```
params:
  type: filesystem|command
  value: <path or command>
  meta:
    allow-all-logs: True
    args: []
    kwargs: {}
    args-callback: None

usage:
  input.path
```

#### priority
Defines an integer priority.

```
params:
  <int>

usage:
  int(priority)
```

#### raises
Defines the issue or message we want to raise given a match. For example a
check may want to raise an issue using type core.issues.issue_types.Foo with
a message that is created using a template and some format input based on the
results of a search (see expr override).

```
params:
  type: core.issues.issue_types.<type>
  message: <str>
  format-dict: <dict>
  format-groups: [<int>, ...]

usage:
  raises.type
  raises.message
  raises.format_dict
  raises.format_groups
```

#### requires
Defines a requirement or list of requirements. Typically used a way to
determine whether or not to run a check. Currently supports a Python
property (type: property) or name of a package that must be installed for
passes to return True (type: apt).

If a list of requirements is defined, the results are ORed together i.e. if any
return True, the requirement passes.

```
params:
  type: property|apt
  value: <value>

  or

  - type: property|apt
    value: <value>
  - type: property|apt
    value: <value>

usage:
  requires.passes
```

#### settings
Defines a group of settings. Implementation is handler-specific. Settings are
retreived by iterating over the result.

```
params:
  dict

usage:
  iter(settings)
```

### start|body|end|expr|hint
Defines a search expression. There are different types of search expression
that can be used depending on the data being searched and how the results will
be interpreted. For example a "simple" search involves a single expression and
is used to match single lines. A "sequence" search is using with
core.filesearcher.SequenceSearchDef to match (non-overlapping) sequences and
then there is also support for analysis overlapping sequences with
core.analytics.LogEventStats.

An optional passthrough-results key is provided and used with events type
defintions to indicate that search results should be passed to
their handler as a raw core.searchtools.SearchResultsCollection. This is
typically so that they can be parsed with core.analytics.LogEventStats.
Defaults to False.

```
params:
  expr|hint:
    <str>
  start|body|end:
    expr: <int>
    hint: <int>
  passthrough-results: True|False

usage:
  If value is a string:
    str(expr|hint)

  If using keys start|body|end:
    <key>.expr
    <key>.hint

Note that expressions can be a string or list of strings.
```


## Events

These checks are not currently run automatically and do require custom
callbacks to be implemented in plugin code that are used to process the
results.

An event can be single or multi-line and the data source (input) can be a
filesystem path or command. All event checks must have an eponymous callback
method defined in the plugin that handles them.

To define an event first create a file with the name of the check you
want to perform under the directory of the plugin you are using to handle the
event callback.

Supported settings (for more details see core.ycheck.YEventCheckerBase):

Two types of searches are available here; single or multi line. A multi-line
search can be used in two ways; the first use is simply to have a "start" and
"end" expression and the results will have -start and -end appended to their
tags accordingly and the second use is to define a sequence which requires at
least a "start" and "body" with optional "end". Sequences are processed using
searchtools.SequenceSearchDef and all other searches use
searchtools.SearchDef. Single line search is defined using the "expr" key.

An example single-line search on a file path could look like:

```
myeventname:
  input:
    type: filesystem
    value: path/to/my/file
  expr: <re.match pattern>
  hint: optional <re.match pattern> used as a low-cost filter
```

An example multi-line search on a file path could look like:

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

An example sequence search on a file path could look like:

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

NOTE: see core.ycheck.YAMLDefInput for more info on support for input
      types.

## Bugs

These checks are run automatically and do not require implementing in plugin
code.

Each plugin can have an associated set of bugs to identify by searching for a
pattern either in a file/path or command output. When a match is found, a
message is displayed in the 'known-bugs' section of a plugin output.

## Config checks

These checks are run automatically and do not require implementing in plugin
code.

Each plugin can define a set of bugs to identify by searching for a
pattern either in a file/path or command output. When a match is found, a
message is displayed in the 'known-bugs' section of a plugin output.

## Package checks

These checks are run automatically and do not require implementing in plugin
code.

Each plugin can define a set of packages along with associated version ranges
that are known to contain a specific bug. If the package is found to be
installed and fall within the defined range, a message is displayed in the
'known-bugs' section of a plugin output.


## Scenarios

These checks are run automatically and do not require implementing in plugin
code.

Each plugin can define a set of scenarios whereby a scenario comprises of a set
of "checks" and "conclusions". Each check is executed independently and
conlusions are defined as decision based on the outcome of one or more checks.
Conclusions can be given priorities so that one can be selected in the event of
multiple positives. This is helpful for defining fallback conlusions.
