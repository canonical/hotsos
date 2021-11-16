# YAML Defintions

This directory contains the configuration for yaml definitions. These
definitons are characterised by the their top-level directory name which
corresponds to the handler used to process them.

These yaml definitions are used as a way to execute checks and analysis without
the need to write code (other than yaml) unless for when the check you are
writing relies on some core library code that does not yet exist.

The structure of these files is as follows:

 * top level directory name must be the name of the plugin the checks belong
   to.
 * contents are files whose name is the check being performed
 * contents can be grouped into directories for organisational purposes
 * content of files uses the format provided by github.com/dosaboy/ystruct
   i.e. a tree where each level contains "overrides" and "content". Overrides
   follow an inheritance model so that they can be defined and supersceded at
   any level. 

At present the following types of definitions are provided:

 * bugs
 * event
 * packages_bug_checks
 * config_checks
 * scenarios  

See core.ychecks for details on the implementation of each.

TIP: to use a single quote ' inside a yaml string you need to replace it with
     two single quotes.

## Events

Definitions for event searches. An event can be single or multi-line and
the data source (input) can be a filesystem path or command. All event checks
must have callback method defined in the plugin that handles them where the
callback method name matches the name of the check.

To define an event check first create a file with the name of the check you
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

myeventname:
  input:
    type: filesystem
    value: path/to/my/file
  expr: <re.match pattern>
  hint: optional <re.match pattern> used as a low-cost filter

An example multi-line search on a file path could look like:

myeventname:
  input:
    type: filesystem
    value: path/to/my/file
  start:
    expr: <re.match pattern>
  end:
    expr: <re.match pattern>

An example sequence search on a file path could look like:

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

NOTE: see core.checks.ycheck.YAMLDefInput for more info on support for input
      types.

## Bugs

Definitions for automated bug checks.

## Config checks

Definitions for automated config checks.

## Package bug checks

Definitions for automated package bug checks.

## Scenarios

Definitions for automated scenario checks.
