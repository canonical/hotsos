# Unit Test Templates

Checks written in yaml can have one or more associated unit test also written
in yaml that will be imported into and run as part of the existing Python unit
tests.

To use this method of writing a unit test for a yaml check you must mimic the
path to the check under test (the "target") by storing it under *defs/tests*.
For example *defs/scenarios/myplugin/foo.yaml* is expected to have
corresponding test at *defs/tests/scenarios/myplugin/foo.yaml*.

To write more than one test for the same check you can give the
test an arbitrary name and use ``target-name: <name>.yaml`` to point to
the correct target. Using the previous example this could look like
*defs/scenarios/myplugin/foo_test1.yaml*
and *defs/scenarios/myplugin/foo_test2.yaml* with both containing
``target-name: foo.yaml``.

## Test Schema

Explicitly set name of target under test. This is useful if you want to write
more than one test for the same check such that the name cannot be inferred
from the test.

```
target-name: <name>.yaml
```

The Python unit tests each have a default DATA_ROOT configured (usually
in the setUp() method) but sometimes we want to use custom data. This can be
done with the following which creates an temporary empty data root and
populates it with content as defined.

```
data-root:
  files:
    somepath: content
  copy-from-original:
    - anotherpath
```

The optional *copy-from-original* stanza is a list of files that will be copied
into the temporary data root from the test default data root (so the files need
to exist).

Tests may also want to mock some code and to achieve this we have the following
which provides a way to define mock.patch() and mock.patch.object() calls for
a test.

```
mock:
  patch:
    path.to.class.property:
      kwargs:
        # this dict allows defining any args/kwargs supported by
        # mock.patch() - see https://docs.python.org/3/library/unittest.mock.html
  patch.object:
    path.to.class:
      kwargs:
        # this dict allows defining any args/kwargs supported by
        # mock.patch.object() - see https://docs.python.org/3/library/unittest.mock.html
```

Finally, the output of a test can be checked by specifying which issues and/or
bugs we expect to have been raised by the check.

```
raised-bugs:
  # msg can be a string or a list of strings
  <url>: msg
raised-issues:
  # msg can be a string or a list of strings
  <issue type>: msg
```

## Example

Imagine you have a check at ``defs/scenarios/myplugin/mycheck.yaml`` as follows:

```
checks:
  check1:
    property:
      path: path.to.class.property
      ops: [[gt, 100]]
  check2:
    input: a/file
    expr: 'hello .+'
conclusions:
  myconc:
    decision: mycheck
    raises:
      type: MyIssue
      msg: it got raised!
```

You can then write a test at ``defs/tests/scenarios/myplugin/mycheck.yaml`` as follows:

```
data_root:
  a/file: |
    hello world
mock:
  patch:
    path.to.class.property:
      kwargs:
        new: 101
raised-issues:
  MyIssue: ->
    it got raised!
```

## Loading Templated Tests

In the Python unit tests code you need to add the following decorator to import
and run these tests:

```
import utils

@utils.load_templated_tests('scenarios/myplugin')
def MyScenarioTests(utils.BaseTestCase):
   ...
```

The **MyScenarioTests** class can still define tests in Python if required
although it is recommended that tests for yaml checks use the yaml format as
well.
