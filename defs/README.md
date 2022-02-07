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


#### decision
Defines a decision as a list of logical operators each associated with a list
of one or more check labels as defined in a *checks* subdef. This property is
typically used in a *conclusions* subdef.

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
Defines a type of input. Currently we support a filesystem path or command.
When a command is provided, the output of that command is written to a
temporary file the path of which is returned by input.path. Supported commands
are those provided by core.cli_helpers.CLIHelper. Only one of *path* or
*command* can be defined for a given input.

format

```
input:
  command: python import path for CLIHelpers command
  path: filesystem path (relative to DATA_ROOT)
  options: OPTIONS

OPTIONS
    This is a dictionary of options with the form key: value.

    allow-all-logs: True|False
      Used in combination with *path* and determines
      whether to apply USE_ALL_LOGS to path. Default is True.

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
Defines an integer priority.

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
Defines the issue and message we want to raise. For example a check may want
to raise an issue using type core.issues.issue_types.Foo with a message that
contains format fields that need to be populated.

format

```
raises:
  type: core.issues.issue_types.<type>
  message: <str>
  format-dict: <dict>
  search-result-format-groups: [<int>, ...]
```

If the *message* string contains format fields these can be filled using either
*format-dict* or *search-result-format-groups*. The former is simply a
dictionary where the keys must match the names used in the format fields within
the *message* string and the latter is a list of integer indexes representing
search result group IDs from an *expr* search result. This is converted
into a list of values and used to format the *message* string (so therefore
fields do not need to be named when using this method). 

usage

```
raises.type
raises.message
raises.format_dict
raises.format_groups
```

#### requires
Defines one or more requirements with a pass/fail result. Typically used a way
to determine whether or not to run a check.

If the result is based on the outcome of more than one requirement they
must be grouped using logical operators used to determine the result of each
group. The result of all groups are ANDed together to get the final result for
*passes*.

format

```
requires:
  REQ_DEPENDS_ON
  REQ_DEFS

REQ_DEPENDS_ON
  An optional dict with format:
  
  depends-on: REQ_DEF

  This allows for a single REQ_DEF to be run before any other as a
  condition for running REQ_DEFS which are only checked if the
  outcome is True otherwise they are skipped and *passes* returns
  True.  

REQ_DEFS
  This must be one (and only one) of the following:
    * single REQ_DEF
    * a single REQ_GROUP
    * list of one or more REQ_GROUP and/or REQ_DEF

  The final result of a list is formed of AND applied to the
  individual results.

REQ_DEF
  A single requirement defined as a dictionary with the following
  key/value pairs:

  TYPE: INPUT
  value: <value> (optional. Default is boolean True.)
  op: <operator> (optional [python standard operator](https://docs.python.org/3/library/operator.html). Default is eq.)

REQ_GROUP
  Requirements can be grouped using a dictionary of LOGICAL_OPERATOR
  keys whose values are lists of requirements to which the operator is
  applied e.g.

  and:
    - REQ_DEF1
    - REQ_DEF2
    - ...
  or:
    - REQ_DEF3
    - ...

  The final result of a group is formed of AND applied to the
  result of each subgroup.

LOGICAL_OPERATOR
  and|or|not

TYPE
  property
    INPUT is a Python import path for a property that will be called
    and optionally matched against a provided value. If no value is
    provided a boolean value of True is results. 

  apt
    INPUT is an apt package name or APT_INFO. Returns True if package
    exists and version is within ranges (if provided) otherwise False.

  snap
    INPUT is a snap package name. Returns True if package exists
    otherwise False.

  systemd
    INPUT is a systemd service name. Returns True if service exists
    and a service status can be optionally checked using value: in
    which case a match is required to get True.

  config
    Defines a config checker where INPUT is CONFIG_INFO.
    
CONFIG_INFO
  A dictionary containing the information required to perform some
  config checks. The handler is typically a .

  handler: import path to plugins' implementation of
           core.checks.SectionalConfigBase.
  path: optional path to use as argument to handler.
  assertions: CONFIG_ASSERTIONS

CONFIG_ASSERTIONS
  A list of assertions to be used with CONFIG_INFO where each item
  contains:

  section - optional config file section name.
  op - [python operator](https://docs.python.org/3/library/operator.html) to apply. Default is eq.
  value - expected value. Default is None.
  allow-unset - whether the config may be unset. Default is False.

APT_INFO
  dictionary of package name and version ranges e.g.
  
  a-package-name:
    - min: 0.0
      max: 1.0
    - min: 4.0
      max: 5.0

  NOTE: we currently only support a single package.
```

usage

```
requires.passes
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

Supported properties
  * expr
  * requires
  * input

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

Supported properties
  * priority
  * decision
  * raises

## Handlers

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


### Bugs

These checks are run automatically and do not require implementing in plugin
code.

Each plugin can have an associated set of bugs to identify based on the
contents of files, output of commands or versions of installed packages and can
use any combination of these. If package version info is checked and the
package is not installed, any other checks are skipped for that bug. 

Supported properties
  * requires - this must "pass" for the bugcheck to complete
  * input - this is required by *expr*
  * expr - optional pattern search in file or command (see *input*)
  * raises - used to define message displayed when bug identified. Note that
             *raises.type* is ignored here since we are always raising a bug.
  
Supported subdefs
  * none


### Config checks

These checks are run automatically and do not require implementing in plugin
code.

These checks are lightweight scenarios in that they don't use the *checks* or
*conclusions* properties and are typically used to perform checks on config.

Supported properties
  * requires
  * raises
  
Supported subdefs
  * none

