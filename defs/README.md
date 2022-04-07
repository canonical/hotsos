# YAML Defs

This directory contains the configuration for yaml-defined analysis.

A number of different ways to define checks are supported. See
[handlers](#handlers) for more information on supported types.

## Writing Checks in YAML

First choose what [type](#handlers) of check you want to write and in which
plugin context the check should be run.

Checks are organised beneath a directory that shares the name of the plugin
that will run them. Files and directories are used to group checks with files
containing one or more checks. All check definitions have the same basic
structure, using a mixture of properties and, if defining a
[scenario](#scenarios), [PropertyCollection](#propertycollection).

This approach provides a way to write checks and analysis in a way that focuses
on the structure and logic of the check rather than the underlying
implementation and is achieved by using library/shared code (e.g.
[core](../core/plugins)) as much as possible.

A handler loads yaml definitions as a tree structure, with leaf nodes
expressing the checks. This structure supports property inheritance so that
globals may be defined and superseded at any level. As a recap:

 * Top directory uses the name of the plugin the checks belong to e.g.
   [openstack](scenarios/openstack).
 * Sub levels contain definitions which can be organised using any
   combination of files and directories e.g. you could put all definitions in
   a single file or you could have one file per definition. You can then use
   directories to logically group your definitions or you can use a tree
   structure within any of the files.
 * This structure uses [ystruct](http://github.com/dosaboy/ystruct) i.e. a
   tree where each level contains override properties and "content".
   Overrides follow an inheritance model so that they can be defined and
   superseded at any level. The content is always found at the leaf nodes of
   the tree.
 * It should always be possible to logically transpose the filesystem tree
   structure to a single (file) yaml tree.

TIP: to use a single quote ' inside a yaml string you need to replace it with
     two single quotes.

## Property Overrides

Property overrides are blocks of yaml with a pre-defined meaning that map to a
Python class that is used by [handlers](#handlers).

Overrides abide by rules of inheritance and can be defined at any level. They
are accessed at leaf nodes and can be defined and overridden at any level.
Since definitions can be organised using files and directories, the latter
requires a means for applying directory globals. To achieve this we put the
overrides into a file that shares the name of the directory e.g.

```
pluginX/groupA/groupA.yaml
pluginX/groupA/scenarioA.yaml
pluginX/groupA/scenarioB.yaml
pluginX/groupA/groupB
```

Here groupA and groupB are directories and groupA.yaml defines overrides that
apply to everything under groupA such that any properties defined in
groupA.yaml will be avaiable in scenarioA.yaml, scenarioB.yaml and any
definitions under groupB.

#### Caching

Every property class has a cache that it can use to store state. This is useful
both within a property class e.g. to avoid re-execution of properties and
between properties e.g. if one property wishes to reference a value within
another property (see [raises](#raises)). Not all properties make use of their
cache but those that do will expose cached fields under a ```CACHE_KEYS```
section.

### List of Available Properties

The following property overrides are available to all types of
definitions provided that their [handlers](#handlers) supports them. The
*format* subsection describes how they can be used in yaml definitions and the
*usage* subsection describes how they are consumed by handlers.

#### decision

A list of logical operators each containing a list of one or more 
check)[#checks] labels. This property is typically used in a
[conclusions](#conclusions) PropertyCollection. The handler
will iterate over the groups, extract their result of each check and apply the
operator to get a final result as to whether the "decision" is True or False.

format

```
decision:
  and|or: [check1, ...]
```

usage

```
<iter>
```

#### input

Provides a common way to define input to other properties. Supports a
filesystem path or [core.cli_helpers.CLIHelper](../core/cli_helpers.py)
command. When a command is provided, its output is written to a
temporary file and *input.path* returns the path to that file. Only one of
*path* or *command* can be provided at once.

This property is required by the [search](#search) property and
allows a search pattern to be applied to the output of a command or the
contents of a file(s) or directory.

format

```
input:
  command: core.cli_helpers.CLIHelpers command
  path: filesystem path (relative to DATA_ROOT)
  options: OPTIONS

OPTIONS
    A dictionary of key: value pairs as follows:

    disable-all-logs: True
      This is used to disable --all-logs for the input. By default
      if --all-logs is provided to the hotsos client that will apply
      to *path* but there may be cases where this is not desired and
      this option allows disabling --all-logs.

    args: [arg1, ...]
      Used in combination with *command*. This is a list of args
      that will be provided to the command.
       
    kwargs: {kwarg1: val, ...}
      Used in combination with *command*. This is a dictionary
      of kwargs that will be provided to the command.

    args-callback: import.path.to.method
      Used in combination with *command*. This is the import path to
      a method that will be called and the return value must be a
      tuple of the form <list>, <dict> where the list is used as args
      to the command and dict is kwargs.
```

usage

```
input.path
```

#### priority

Defines an integer priority. This is a very simple property that is typically
used by (conclusions)[#conclusions] to associate a priority or precendence to
conclusions. 

format

```
priority:
  <int>
```

usage

```
int(priority)
```

#### raises

Defines an issue to raise along with the message displayed. For example a
[check](#checks) may want to raise an issue using an
[issue_types](../hotsos/core/issues/issue_types.py) with a formatted message where
format fields are filled using Python properties or search results.

format

```
raises:
  type: hotsos.core.issues.<type>
  bug-id: <str>
  message: <str>
  format-dict: <dict>
  search-result-format-groups: [<int>, ...]
```

If *type* is a [bug type](../hotsos/core/issues/bug_types.py) then a *bug-id*
must be provided.

If the *message* string contains format fields these can be filled
using one of two methods:

* format-dict - a dictionary of key/value pairs where *key* matches a
format field in the message string and *value* is either a Python property
import path or a ``PROPERTY_CACHE_REF``

* search-result-format-groups - a list of integer indexes representing
search result group IDs from an *expr* property search result. The group
indexes refer to items in a core.searchtools.SearchResult.

```
PROPERTY_CACHE_REF
  This is a reference to a property cache item and can take one of
  two forms:
  
  '@<propertyname>.CACHE_KEY'

  '@checks.<checkname>.<propertyname>.CACHE_KEY'

  The latter is used if the property is within a checks PropertyCollection.

CACHE_KEY
  See individual property CACHE_KEYS for supported cache keys.
```


usage

```
raises.type
raises.message
raises.format_dict
raises.format_groups
```

#### requires
Defines a set of requirements to be executed with a pass/fail result.

If the result is based on the outcome of more than one requirement they
must be grouped using logical operators (see REQ_GROUP) used to determine
the result of each group. The result of all groups are ANDed together to
get the final result for *passes*.

format

```
requires:
  REQ_DEFS

REQ_DEFS
  This must be one (and only one) of the following:
    * single REQ_DEF
    * a REQ_GROUP
    * list containing a mix of REQ_GROUP/REQ_DEF

  The final result of a list is formed of AND applied to the
  individual results of each REQ_DEF or REQ_GROUP.

REQ_DEF
  A single requirement REQ_TYPE.

REQ_GROUP
  A dictionary of lists of one or more REQ_DEF grouped by a
  LOGICAL_OPERATOR which is applied to the set of REQ_DEF results
  in the group e.g.

  and:
    - REQ_DEF1
    - REQ_DEF2
    - ...
  or:
    - REQ_DEF3
    - ...

  AND is then applied to the result of all groups to get the final result.

LOGICAL_OPERATOR
  and|or|not

REQ_TYPE
  PROPERTY
    Calls a Python property and if provided, applies a set of
    operators. If no operators are specified, the "truth" operator
    is applied to get a True/False result.
 
    Format:

    property: <import path to python property>

    or

    property:
      path: <import path to python property>
      ops: OPS_LIST

  APT
    Takes an apt package name or APT_INFO. Returns True if the package
    exists and, if APT_INFO provided, version is within ranges.

    Format:

    apt: [package name|APT_INFO]
  
  SNAP
    Takes an snap package name. Returns True if the package
    exists.

    Format:

    snap: package name

  SYSTEMD
    Takes a systemd service and, optionally, state. Returns True if service
    exists and, if provided, state matches. A short and long form are
    supported as follows where the long form supports provided more than one
    <service>: <state> pair and optionally an operator to be used instead of
    the default 'eq' when comparing state.

    Format:

    systemd: <service name>

    or

    systemd:
      <service name>: <service state>
      op: <python operator>

  CONFIG
    A dictionary containing the information required to perform some
    config checks. The handler is typically a .

    Format:

    handler: <path>
      Import path to an implementation of core.checks.SectionalConfigBase.

    path: <path>
      Optional path (e.g. config file) to use as argument to handler.

    invert-result: True|False
      This can be used to invert the final assertions result e.g.
      setting to False would be like doing not(and(assertions)).
      Defaults to False (which is equiv. to and(assertions)).

    assertions: <assertions>
      A list of assertions where each item is a dicttionary containing:
    
      section: optional config file section name.
      ops: OPS_LIST
      value: expected value. Default is None.
      allow-unset: whether the config key may be unset. Default is False.

OPS_LIST
    List of tuples with the form (<operator>[,<arg2>]) i.e. each tuple has
    at least one item, the operator and an optional second item which is
    the second argument to the operator execution. The first argument is
    always the output of the REQ_DEF or previous operator.

    Operators can be any supported [python operator](https://docs.python.org/3/library/operator.html).

    If more than one tuple is defined, the output of the first is the input
    to the second.

APT_INFO
  dictionary of package name and version ranges e.g.
  
  a-package-name:
    - min: 0.0
      max: 1.0
    - min: 4.0
      max: 5.0

  NOTE: we currently only support a single package.

CACHE_KEYS
  value_actual
  op
  key (only used by config REQ_TYPE)
  passes
```

usage

```
requires.passes
```

### search

Defines a search expression. There are different types of search expression
that can be used depending on the data being searched and how the results will
be interpreted. For example a "simple" search involves a single expression and
is used to match single lines. A "sequence" search is using with
core.filesearcher.SequenceSearchDef to match (non-overlapping) sequences and
then there is also support for analysis overlapping sequences with
[core.analytics.LogEventStats](../core/analytics).

An optional *passthrough-results* key is provided and used with
[event](#events) type definitions to indicate that search results should be
passed to their handler as a raw core.searchtools.SearchResultsCollection. This
is typically so that they can be parsed with core.analytics.LogEventStats.
Defaults to False.

format

```
expr|hint: <str>

start|body|end:
  expr: <int>
  hint: <int>

passthrough-results: True|False
```

usage

```
If value is a string:
  str(expr|hint)

If using keys start|body|end:
  <key>.expr
  <key>.hint

Note that expressions can be a string or list of strings.
```

### check-parameters

These are optional parameters used in a [checks](#checks) check defintion. They
are typically used in conjunction with an [expr]([#expr]) property to apply
constraints to search results.

format

```
search-result-age-hours: <int>
  Age from current date (CLIHelper.date()) that results must fall
  within. Default is infinite. This is used in conjunction with the
  expr property and requires the search pattern to contain a group at
  the start (index 1) to match a timestamp of the form
  YEAR-MONTH-DAY HOUR:MIN:SECS

search-period-hours: <int>
  Period of time within which we expect to find results. Default is
  infinite. Like search-result-age-hours this also requires the search
  pattern to match a datetime at index 1.

min-results: <int>
  Minimum number of search results required. If a search period is
  defined, these must occur within that period. Default is 1.
```

usage

```
check-parameters.min
check-parameters.period
```

### PropertyCollection

These are groupings of properties of different types that are labelled to allow
them to be accessed by name.

#### checks

A dictionary of labelled checks each of which is a grouping of properties (see
Supported Properties). Eack check is executed independently and produces a
boolean *result* of True or False.

Checks are normally implemented in conjunction with [conclusions](#conclusions)
as part of [scenarios](#scenarios).

format

```
checks:
  check1:
    <property1>
    <property2>
  check2:
    <property3>
    <property4>
  ... 
```

usage

```
<checkname>.result
```

Supported Properties
  * [search](#search)
  * [requires](#requires)
  * [input](#input)
  * [check-parameters](#check-parameters)

#### conclusions

This indicates that everything beneath is a set of one or more conclusions to
be used by [core.ycheck.scenarios](../core/ycheck/scenarios). The contents of
this override are defined as a dictionary of conclusions labelled with
meaningful names.

A conclusion is defined as a function on the outcome of a set of checks along
with the consequent behaviour should the conclusion match. This is defined as
an issue type and message that will be raised. If multiple conclusions are
defined, they are given a [priority](#priority) such that the highest one to
match is the one that is executed. See [scenarios](#scenarios) section for more
info and examples.

The message can optionally use format fields which, if used, require
format-dict to be provided with required key/value pairs. The values must be
an importable attribute, property or method. 

format

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

usage

```
<conclusionname>.reached
<conclusionname>.priority
<conclusionname>.issue_message
<conclusionname>.issue_type
```

Supported Properties
  * [priority](#priority)
  * [decision](#decision)
  * [raises](#raises)

## Handlers

The following different ways of defining checks as yaml are provided, each
implemented as a handler. The implementation of each can be found
[here](../core/ycheck).

### Scenarios

Scenarios provide a way to define analysis in terms of [checks](#checks) and
[conclusions](#conclusions) where the latter are derived from decisions based
on the outcome of one or more checks.

Scenarios run automatically and are implemented purely in YAML. See [existing
definitions](scenarios).

Definitions must be grouped by plugin at the top level and groupings beneath are
purely logical i.e. for organisational purposes. A file may contain one or more
scenario where a scenario must define its own set of [checks](#checks) and
[conclusions](#conclusions).

Checks are implemented independently of each other and the results saved for
subsequent [decision](#decision) when forming [conclusions](#conclusions).
Conclusions are defined as a decision based on the outcome of one or more
[checks](#checks) along with information such as the issue and message to
raise if a conclusion is matched. Conclusions can be given
[priorities](#priority) so that one can be selected in the event of multiple
positives. This is helpful for defining fallback conclusions.

Supported Properties
  * none
  
Supported PropertyCollection
  * [checks](#checks)
  * [conclusions](#conclusions)

### Events

Event checks are not run automatically and depend on the implementation of
callbacks to process their results. See [existing definitions](events).

These checks are not currently run automatically and do require custom
callbacks to be implemented in plugin code to process results. Event
definitions can be found [here](events).

An event can be single or multi-line and the data source is defined with an
[input](#input) property. All event checks must have an eponymous callback
method defined in the plugin that handles them.

To define an event first create a file with the name of the check(s) you
want to perform under the directory of the plugin you are using to handle the
event callback.

Supported Properties
  * [input](#input)
  * [search](#search)
  
Supported PropertyCollection
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
    path: path/to/my/file
  expr: <re.match pattern>
  hint: optional <re.match pattern> used as a low-cost filter
```

A multi-line search on a file:

```
myeventname:
  input:
    path: path/to/my/file
  start:
    expr: <re.match pattern>
  end:
    expr: <re.match pattern>
```

A sequence search on a file:

```
myeventname:
  input:
    path: path/to/my/file
  start:
    expr: <re.match pattern>
  body:
    expr: <re.match pattern>
  end:
    expr: <re.match pattern>
```
