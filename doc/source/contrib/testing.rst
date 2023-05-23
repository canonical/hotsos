Testing Checks
==============

All checks contributed to Hotsos should be accompanied by a unit test and there are
two ways to do this. You can write tests the "old" way i.e. as a Python `unittest <https://docs.python.org/3/library/unittest.html>`_
implementation under *tests/unit_tests* or you can write them in yaml
which is explained here.

Writing tests in Yaml
---------------------

Checks written in yaml can have one or more associated unit test also written
in yaml. These will be loaded at runtime into the main unit test runner and run
as part of the existing Python unit tests.

To write a test you must mimic the path to the check under test i.e. the "target".
For example given a scenario check add a single test as follows::

    hotsos/defs/scenarios/myplugin/foo.yaml
    hotsos/defs/tests/scenarios/myplugin/foo.yaml

The point of using the same sub path and filename is that the runner will then assume that the
target has the same name.

To write more than one test for a given target, perhaps to test both pass and fail cases, you
can give the test file a meaningful name and inside your test specify the target file name
using the ``target-name: <name>.yaml`` stanza e.g. ::

    hotsos/defs/scenarios/myplugin/foo.yaml
    hotsos/defs/tests/scenarios/myplugin/foo_pass.yaml
    hotsos/defs/tests/scenarios/myplugin/foo_fail.yaml

Test Reference
--------------

The first line in a test can optionally be a target name. This is required if the path to your
test does not match that used for that check under test:

.. code-block:: yaml

    target-name: <name>.yaml


When a test runs, its environment will have a default path set for HotSOSConfig.data_root (typically
done by the setUp method of that set of tests). We can optionally modify the contents of this path
for the purpose the test using the following.:

.. code-block:: yaml

    data-root:
      files:
        somepath: content
      copy-from-original:
        - anotherpath

The optional *copy-from-original* stanza is a list of files that will be copied
into the temporary data root from the test default data root (so the files need
to exist).

Tests may also want to mock some code and to achieve this we have the following
which provides a way to define mock.patch() and mock.patch.object() calls for
a test:

.. code-block:: yaml

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

Finally, the output of a test can be checked by specifying which issues and/or
bugs we expect to have been raised by the check:

.. code-block:: yaml

    raised-bugs:
      # msg can be a string or a list of strings
      <url>: msg
    raised-issues:
      # msg can be a string or a list of strings
      <issue type>: msg

## Example

Imagine you have a check at ``defs/scenarios/myplugin/mycheck.yaml`` as follows:

.. code-block:: yaml

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

You can then write a test at ``defs/tests/scenarios/myplugin/mycheck.yaml`` as follows:

.. code-block:: yaml

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

Running Tests
-------------

In the Python unit tests code you need to add the following decorator to import
and run these tests:

.. code-block:: python

    import utils

    @utils.load_templated_tests('scenarios/myplugin')
    def MyScenarioTests(utils.BaseTestCase):
       ...

The **MyScenarioTests** class can still define tests in Python if required
although it is recommended that tests for yaml checks use the yaml format as
well.

Troubleshooting Tests
---------------------

By default the unit tests will not output DEBUG level logs but it is possible to force this
for debugging a test by doing:

.. code-block:: console

  export TESTS_LOG_LEVEL_DEBUG=yes

If your test scenario includes verbatim test files, i.e. you are using the
`data-root` key, setting

.. code-block:: console

  export TESTS_LOG_LEVEL_DEBUG=yes
  export TESTS_LOG_TEST_ARTIFACTS=yes

before running the tests will include the contents of the test files in the
debug output.

You can then re-run a failing test directly without running all tests and get the debug output for that test specifically e.g.

.. code-block:: console

  tox -epy3 tests.unit.test_system.TestUbuntuPro.test_ubuntu_pro_attached
