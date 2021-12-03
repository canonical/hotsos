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
absolute minimum of code. In other works the majority of contributions should
not require any code other than yaml. A tree structure is used and follows
these rules:

 * basic structure is:

```
<def-type>
  <plugin-name>
    <optional-group>
      <defs-name>
```

 * first directory must use the name of the plugin the checks belong
   to.
 * next level is the definitions which can use any combination of files and
   directories to organise defintions in a way that makes sense.
 * content of files uses the format provided by github.com/dosaboy/ystruct
   i.e. a tree where each level contains "overrides" and "content". Overrides
   follow an inheritance model so that they can be defined and supersceded at
   any level. The content is always found at the leaf nodes of the tree.
 * it should always be possible to transpose the filesystem tree structure to
   a single (file) yaml tree.

TIP: to use a single quote ' inside a yaml string you need to replace it with
     two single quotes.

## Overrides

The following overrides are available to all types of definitions.

#### input
```
params:
  type: "filesystem"|"command"
  value: path or command
  meta:
    allow-all-logs: True
    args: []
    kwargs: {}
    args-callback: None

usage:
  input.path
```

#### context
```
params:
  <dict>

usage:
  context.<param>
```

#### requires
```
params:
  type: property|apt
  value: <value>

usage:
  requires.passes
```

#### config
```
params:
  handler: <config-handler>
  path: <config-path>

usage:
  config.actual(key, section=None)
  config.check(actual, value, op, allow_unset=False):
```

#### checks
```
params:
  none

usage:
  checks
```

#### conclusions
```
params:
  none

usage:
  conclusions
```

#### priority
```
params:
  <int>

usage:
  int(priority)
```

#### decision
```
params:
  <int>

usage:
  int(priority)
```

#### raises
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

### start|body|end|expr|hint
```
expr|hint:
  <str>
start|body|end:
  expr: <int>
  hint: <int>

usage:
  If value is a string:
    str(expr|hint)

  If using keys start|body|end:
    <key>.expr
    <key>.hint

Note that expressions can be a string or list of strings.
```

#### settings
```
params:
  dict

usage:
  iter(settings)
```

#### releases
```
params:
  dict

usage:
  iter(releases)
```

#### passthrough-results
```
params:
  <bool>

usage:
  bool(passthrough-results)
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

### Adding a new package check categories

- Add a folder under `defs/package_bug_checks`
- Add a all.yaml file with a `context` override

Format:

```yaml
context:
  release: <class.property.that.returns.the.current.release>
  apt-all: <class.property.that.returns.the.list.of.packages>
```

Example:

```yaml
context:
  release: core.plugins.openstack.OpenstackBase.release_name
  apt-all: core.plugins.openvswitch.OpenvSwitchChecksBase.apt_packages_all
```

- Add a new bug definition

### Adding new bug definitions

- Add a new file under `defs/package_bug_checks/new_bug_check.yaml`. The file
can have the following overrides: `raises`, `settings`.

## Scenarios

These checks are run automatically and do not require implementing in plugin
code.

Each plugin can define a set of scenarios whereby a scenario comprises of a set
of "checks" and "conclusions". Each check is executed independently and
conlusions are defined as decision based on the outcome of one or more checks.
Conclusions can be given priorities so that one can be selected in the event of
multiple positives. This is helpful for defining fallback conlusions.
