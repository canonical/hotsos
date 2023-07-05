Background
==========

First choose what type of check you want to write and in which plugin context
the check should be run. The choices are events and scenarios.

Definitions are organised beneath a directory that shares the name of the plugin
that will run them and can be grouped using files and directories. All
definitions have the same basic structure using a mixture of properties.

This approach provides a way to write checks and analysis in a way that focuses
on the structure and logic of the check rather than the underlying
implementation. This is achieved by leveraging the properties provided along
with libraries/shared code (e.g. `core plugins <https://github.com/canonical/hotsos/tree/main/hotsos/core/plugins>`_
as much as possible).

The yaml definitions are loaded into a tree structure, with leaf nodes
containing the consumable information such as checks. This structure supports
property inheritance so that globals may be defined and superseded at any
level.

In summary:

* Top directory shares its name with the plugin the checks belong to e.g.
  `openstack <https://github.com/canonical/hotsos/tree/main/hotsos/defs/scenarios/openstack>`_.
* Sub levels contain definitions which can be organised using any combination of
  files and directories, using them to logically group your definitions.
* The backbone of this approach is
  `propertree <https://github.com/dosaboy/propertree>`_ i.e. a tree where each
  level contains override properties and "content". Overrides follow an
  inheritance model so that they can be defined and superseded at any level. The
  content is always found at the leaf nodes of the tree.

TIP: to use a single quote ' inside a yaml string you need to replace it with
     two single quotes.

Pre-requisites
==============

If you want to gate running the contents of a directory on a pre-requisite you
can do so by putting them in a file that shares the name of its parent directory.
In the following example *mychecks.yaml* contains a :ref:`requires` and
the rest of the directory will only be run if it resolves to *True*:

.. code-block:: console

    $ ls myplugin/mychecks/
    mychecks.yaml myotherchecks.yaml
    $ cat myplugin/mychecks/mychecks.yaml
    requires:
      or:
        - property: hotsos.core.plugins.myplugin.mustbetrue
        - path: file/that/must/exist

