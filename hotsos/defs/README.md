# YAML Defs

This directory contains the configuration for yaml-defined analysis.

Two different ways to define checks are supported. See [handlers](#handlers)
for more information on this.

## How to Add or Amend Checks

First choose what [type](#handlers) of check you want to write and in which
plugin context the check should be run.

Definitions are organised beneath a directory that shares the name of the plugin
that will run them and can be grouped using files and directories. All
definitions have the same basic structure using a mixture of properties.

This approach provides a way to write checks and analysis in a way that focuses
on the structure and logic of the check rather than the underlying
implementation. This is achieved by leveraging the properties provided along
with library/shared code (e.g. [core plugins](../hotsos/core/plugins)) as much
as possible.

The yaml definitions are loaded into a tree structure, with leaf nodes
containing the consumable information such as checks. This structure supports
property inheritance so that globals may be defined and superseded at any
level.

In summary:

* Top directory shares its name with the plugin the checks belong to e.g.
  [openstack](scenarios/openstack).
* Sub levels contain definitions which can be organised using any combination of
  files and directories, using them to logically group your definitions.
* The backbone of this approach is
  [propertree](https://github.com/dosaboy/propertree) i.e. a tree where each
  level contains override properties and "content". Overrides follow an
  inheritance model so that they can be defined and superseded at any level. The
  content is always found at the leaf nodes of the tree.

TIP: to use a single quote ' inside a yaml string you need to replace it with
     two single quotes.

## Pre-requisites

If you want to gate running the contents of a directory on a pre-requisite you
can do so by putting them in a file that shares the name of its parent directory.
In the following example *mychecks.yaml* contains a [requires](#requires) and
the rest of the directory will only be run if it resolves to *True*.

```console
$ ls myplugin/mychecks/
mychecks.yaml myotherchecks.yaml
$ cat myplugin/mychecks/mychecks.yaml
requires:
  or:
    - property: hotsos.core.plugins.myplugin.mustbetrue
    - path: file/that/must/exist
```

## Property Overrides

Property overrides are blocks of yaml that map to Python classes that are
consumed by [handlers](#handlers).

### Property Globals

Overrides abide by rules of inheritance. They are accessed at leaf nodes and can
be defined and overridden at any level. Since definitions can be organised using
files and directories, the latter requires a means for applying directory
globals. Similar to pre-requisites, this is done by defining overrides in file
that shares the name of the directory e.g.

```
myplugin/
├── altchecks
└── mychecks
    ├── checkthat.yaml
    ├── checkthis.yaml
    ├── mychecks.yaml
    └── someotherchecks
```

Here *mychecks* and *somemorechecks* are directories and *mychecks.yaml* defines
overrides that apply to everything under *mychecks* such that any properties
defined in *mychecks.yaml* will be available in *checkthis.yaml*,
*checkthat.yaml* and any definitions under *somemorechecks* (but not
*altchecks*).

#### FactoryObjects

Hotsos has support for factory objects. These are objects with which you can
dynamically generate a handler using an input provided as an attribute call
then in turn call to a property on that handler. While a property would
normally be imported as follows:

```python
from mymod import myclass
obj = myclass.myprop
val = obj.myattr
```

A factory is used as follows:

```python
from mymod import myfactoryclass
val = myfactoryclass.inattr.fattr
```

Which would result in a new object created using *inattr* as input and then
*fattr* is called on that object.

This allows us to define a property for import in [vars](#vars) as follows:

```yaml
val: '@mymod.myfactoryclass.fattr:inattr'
```

One benefit of this being that *inattr* can be a string containing any
characters incl. ones that would not be valid in a property name.

#### MappedProperties

Some properties use the [propertree](https://github.com/dosaboy/propertree)
mapped properties feature meaning they are implemented as a root property with
one or more "member" properties and the two map to each other. For example if we
have a property *mainprop* and it has two member properties *mp1* and *mp2* it
can be defined using either of the following formats:

```yaml
myleaf:
  mainprop:
    mp1:
      ...
    mp2:
      ...
```

or

```yaml
myleaf:
  mp1:
    ...
  mp2:
    ...
```

and both formats will be resolved and accessed in the same way i.e.

```
myleaf.mainprop.mp1
myleaf.mainprop.mp2
```

#### Context

Every property object inherits a context object that is shared across all
properties. This provides a way to share information across properties.

#### Caching

Every property class has a cache that it can use to store state. This is useful
both within a property class e.g. to avoid re-execution of properties and
between properties e.g. if one property wishes to reference a value within
another property (see [raises](#raises)). Not all properties make use of their
cache but those that do will expose cached fields under a ```CACHE_KEYS```
section.

#### LogicalCollection

This provides a way for properties to make a decision based on a tree of items
where the items may be a single item, list of items, one or more groups or a
list of groups of items organised by logical operator that will be used to
determine their collective result. For example:

```yaml
and: [C1, C2]
or: [C3, C4]
not: C5
nor: [C1, C5]
```

This would be the same as doing:

```yaml
(C1 and C2) and (C3 or C4) and (not C5) and not (C1 or C5)
```

And this can be implemented as a list of dictionaries for a more complex
operation e.g.

```yaml
- and: [C1, C2]
  or: [C3, C4]
- not: C5
  and: C6
```

Which is equivalent to:

```yaml
((C1 and C2) and (C3 or C4)) and ((not C5) and C6)
```

Any property type can be used and which ones are used will
depend on the property implementing the collection. The final result is
always AND applied to all subresults.

### List of Available Properties

The following property overrides are available to all types of
definitions provided that their [handlers](#handlers) supports them. The
*format* subsection describes how they can be used in yaml definitions and the
*usage* subsection describes how they are consumed by handlers.

#### vars

This property supports defining one or more variables that can be referenced
from other properties. They are defined as a list of key: value pairs where
value can be standard types like str, int, bool etc or it can be a Python
property that is called to get its value.

To set a variable to the value of an imported Python property you need to prefix
the import string with '@'. If the property being imported belongs to an
[factory](#factoryobjects) it must have the following form:

```yaml
@<modpath>.<factoryclassname>.<property>:<inputvalue>
```

Variables are referenced/access in other properties by prefixing their name
with a '$'. See [varops](#varops) for more info.

format:

```yaml
vars:
  <name>: <value>
```

usage:

```yaml
<iter>
```

example:

```yaml
vars:
  myintvar: 10
  mystrvar: 'hello'
  myboolvar: true
  mypropvar: '@hotsos.core.plugins.kernel.sysfs.CPU.smt'
  myfactoryvar: '@hotsos.core.host_helpers.systemd.Service.start_time_secs:sshd'
checks:
  is_smt:
    varops: [[$mypropvar], [eq, $myboolvar]]
  is_started_since:
    varops: [[$myfactoryvar], [gt, 1664391030]]
...
```

#### decision

This property is typically used in [conclusions](#conclusions).
CHECKS refers to a set of one or more [check](#checks) names organised as a
[LogicalCollection](#logicalcollection) to make decision on the outcome of more
checks.

format

```yaml
decision: CHECKS
```

usage

```yaml
<iter>
```

#### input

Provides a common way to define input to other properties. Supports a filesystem
path or [`core.host_helpers.CLIHelper`](../hotsos/core/host_helpers/cli.py)
command. When a command is provided, its output is written to a temporary file
and *input.path* returns the path to that file. Only one of *path* or *command*
can be provided at once.

This property is required by and used as input to the [search](#search)
property.

format

```yaml
input:
  command: hotsos.core.host_helpers.CLIHelper command
  path: FS_PATH
  options: OPTIONS
```

or

```yaml
input: FS_PATH

FS_PATH
  This is either a single or list of filesystem paths that must be
  relative to DATA_ROOT.

OPTIONS
    disable-all-logs: True
      Used to disable --all-logs for the input. By default
      if --all-logs is provided to the hotsos client that will apply
      to *path* but there may be cases where this is not desired and
      this option supports disabling --all-logs.

    args: [arg1, ...]
      Used in combination with *command*. This is a list of args
      that will be provided to the command.

    kwargs: {kwarg1: val, ...}
      Used in combination with *command*. This is a dictionary
      of kwargs that will be provided to the command.

    args-callback: import.path.to.method
      Used in combination with *command*. This is the import path to
      a method that will be called and the return value must be a
      tuple of the form (<list>, <dict>) where the list is used as args
      to the command and dict is kwargs.

CACHE_KEYS
  cmd_tmp_path
```

usage

```
input.paths
```

#### priority

Defines an integer priority. This is a very simple property that is typically
used by [conclusions](#conclusions) to associate a priority or precedence to
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
[check](#checks) may want to raise an [issue_types](../hotsos/core/issues/issue_types.py)
with a formatted message where format fields are filled using Python properties
or search results.

format

```
raises:
  type: <type>
  bug-id: <str>
  message: <str>
  format-dict: <dict>
  search-result-format-groups: [<int>, ...]
```

If *type* is a [bug type](../hotsos/core/issues/issue_types.py) then a *bug-id*
must be provided.

If the *message* string contains format fields these can be filled
using one of two methods:

* format-dict - a dictionary of key/value pairs where *key* matches a
format field in the message string and *value* is either a Python property
import path or a ``PROPERTY_CACHE_REF``

* search-result-format-groups - a list of integer indexes representing
search result group IDs from a [search](#search) result. The group
indexes refer to items in a core.searchtools.SearchResult and tie with those in
the search pattern provided.

```
PROPERTY_CACHE_REF
  A reference to a property cache item that takes one of two forms:

  '@<propertyname>.CACHE_KEY'
  '@checks.<checkname>.<propertyname>.CACHE_KEY'

  The latter is used if the property is within a checks property.

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
must be grouped a [LogicalCollection](#logicalcollection) (see REQ_GROUP). The
final results is either True/False for *passes*.

NOTE: this property is implemented as a [MappedProperty](#mappedproperties)
      meaning that the *requires* key is optional.

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
  A single requirement (see Requirement Types).

REQ_GROUP
  A LOGICAL_COLLECTION of one or more REQ_DEF e.g.

  and:
    - REQ_DEF1
    - REQ_DEF2
    - ...
  or:
    - REQ_DEF3
    - ...

OPS_LIST
    List of tuples with the form (<operator>[,<arg2>]) i.e. each tuple has
    at least one item, the operator and an optional second item which is
    the second argument to the operator execution. The first argument is
    always the output of the REQ_DEF or previous operator.

    Operators can be any supported [python operator](https://docs.python.org/3/library/operator.html).

    If more than one tuple is defined, the output of the first is the input
    to the second.
```

usage

```
requires.passes
```

#### search

Used to define a search expression and its criteria. There are different types of
search expression that can be used depending on the data being searched and how
the results will be interpreted:

A "simple" search ([SearchDef](../hotsos/core/searchtools.py)) involves a single pattern
and is used to match single lines.

A "sequence" search ([SequenceSearchDef](../hotsos/core/searchtools.py)) to match
(non-overlapping) sequences.

A "passthrough sequence" is used for analysing overlapping sequences with
[LogEventStats](../hotsos/core/analytics.py). This requires a
callback method to be implemented to process the results and is designated using
the optional *passthrough-results* option. Search results are passed
to their handler as a raw [SearchResultsCollection](../hotsos/core/searchtools.py).

NOTE: this property is implemented as a [MappedProperty](#mappedproperties)
      meaning that the *search* key is optional.

IMPORTANT: do not use global search properties. If you do this, the same search
           tag will be used for all searches and it will not be possible to
           distinguish results form more than one leaf node.

format

```
search:
  expr|hint: <str> (simple search)
  start|body|end: (sequence search)
    expr: <str>
    hint: <str>
  passthrough-results: True|False (turns sequence search into passthrough)
  constraints: CONSTRAINTS

  NOTE: search expressions can be a string or list of strings.

CONSTRAINTS:
  Optional constraints that can be used to filter search results. This
  is typically used in conjunction with [checks]([#checks]).

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

  min-hours-since-last-boot: <int>
    Search result must be at least this number of hours after the last
    boot time.

CACHE_KEYS
  simple_search
  sequence_search
  sequence_passthrough_search
```

usage

```
You can access each parameter individually:

  search.expr
  search.hint

or when using keys start|body|end:

  search.<key>.expr
  search.<key>.hint

Or you can access as a pre-prepared search type:

  search.simple_search
  search.sequence_search
  search.sequence_passthrough_search

Once results have been obtained they can be filtered using which will
return a True/False value.

  search.apply_constraints(searchtools.SearchResultsCollection)

```

### Requirement Types

#### path

This has the same format as the input property and is used to
assert if a path exists or not. Note that all-logs is not applied
to the path.

format

```
path: <path>
```

```
CACHE_KEYS
  path_not_found
  paths
```


#### property
Calls a Python property and if provided, applies a set of
operators. If no operators are specified, the "truth" operator
is applied to get a True/False result.

format

```
property: <import path to python property>

or

property:
  path: <import path to python property>
  ops: OPS_LIST
```

```
CACHE_KEYS
  property
  ops
  value_actual
```

#### apt
Takes an apt package name or APT_INFO. Returns True if the package
exists and if APT_INFO provided, version is within ranges.

format

```
apt: [package name|APT_INFO]

APT_INFO
  single package name, list of packages or dictionary of
  <package name>: <version ranges> e.g.

  mypackage:
    - min: 0.0
      max: 1.0
    - min: 4.0
      max: 5.0
```

```
CACHE_KEYS
  package
  version
```

#### snap
Takes a snap package name or SNAP_INFO. Returns True if the package
exists and if SNAP_INFO provided, revision is within ranges.

format

```
snap: [package name|SNAP_INFO]

SNAP_INFO
  single package name, list of packages or dictionary of
  <package name>: <revision ranges> e.g.

  mypackage:
    - min: 0.0
      max: 1.0
    - min: 4.0
      max: 5.0
```

```
CACHE_KEYS
  package
  revision
```

#### systemd
Takes a systemd service and optionally some parameters to check.
Returns True if service exists and, if provided, parameters match.
Short and long forms are supported as follows.

If a service name is provided using the started-after parameter,
the start time of that service (if it exists) must be at least
120s behind the primary service. The grace period is to avoid
false-positives on boot where many services are often started at
once.

format

```
systemd: <service name>  (state not checked here)

or

systemd: [svc1, svc2 ...]  (state not checked here)

or

systemd: SVCS

where SVCS is a dict of one or more services e.g.

systemd:
  service_name:
    state: <service state>
    op: <python operator>  (optional. default is 'eq')
    started-after: <other service name>  (optional)
    processes: list of processes we expect to be running  (optional)
  ...
```

```
CACHE_KEYS
  services
```

#### config
A dictionary containing the information required to perform some config checks.
Supports applying assertion rules to the contents of one or more config file.

format:

```
handler: <path>
  Import path to an implementation of core.host_helpers.SectionalConfigBase.

path: <path>
  Optional path or list of paths used as input when creating config
  handlers. Each path must be a file or glob path (wildcard).

assertions: ASSERTION
  One or more ASSERTION can be defined and optionally grouped using
  a [LogicalCollection](#logicalcollection). The
  final result is either True/False for *passes*.

ASSERTION
  key: name of setting we want to check.
  section: optional config file section name.
  value: expected value. Default is None.
  ops: OPS_LIST
  allow-unset: whether the config key may be unset. Default is False.
```

```
CACHE_KEYS
  assertion_results - a string of concatenated assertion checks
  key - the last key to be checked
  ops - the last ops to be run
  value_actual - the actual value checked against
```

#### varops
This provides a way to build an OPS_LIST using [variables](#vars) whereby the
first element must be a variable e.g.

format:

```
OPS_LIST where first element is a variable name (and all vars used are prefixed with $).
```

```
CACHE_KEYS
  name: name of the variable used as input
  value: value of the variable used as input
  ops: str representation of ops list
```

example:

```
vars:
  myvar: 10
  limit: 5
checks:
  checkmyvar:
    varops: [[$myvar], [gt, $limit], [lt, 100]]
conclusions:
  ...
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

CACHE_KEYS
  search
  requires
```

usage

```
<checkname>.result
```

Supported Properties
  * [search](#search)
  * [requires](#requires)
  * [input](#input)

#### conclusions

This indicates that everything beneath is a set of one or more conclusions to
be used by [core.ycheck.scenarios](../hotsos/core/ycheck/scenarios.py). The contents of
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

The following ways of defining checks as yaml are provided, each
implemented as a handler. The implementation of each can be found
[here](../hotsos/core/ycheck).

### Scenarios

Scenarios provide a way to define analysis in terms of [checks](#checks) and
[conclusions](#conclusions) where the latter are derived from decisions based
on the outcome of one or more checks.

Scenarios run automatically and are written in YAML. See [existing
definitions](scenarios) for examples. They grouped by plugin at the top level
and groupings beneath are purely logical/organisational. A file may contain
one or more scenario where a scenario must define its own set of
[checks](#checks) and [conclusions](#conclusions). Typically they are
implemented as a one scenario per file.

Checks are implemented independently of each other and the results saved for
subsequent [decisions](#decision) when forming [conclusions](#conclusions).
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

## Testing

All contributions to checks should be accompanied by a unit test and there are
two ways to do this. You can write a test in Python (see [tests/unit](../tests/unit))
or you can write a test in yaml as a template - see [tests/README.md](tests/README.md) for more info.
