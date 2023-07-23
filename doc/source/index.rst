.. hotsos documentation master file, created by
   sphinx-quickstart on Mon Jun 19 15:27:27 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to hotsos's documentation!
==================================

Use hotsos to implement repeatable analysis and extract useful information from
common cloud applications and subsystems. Write analysis
:ref:`Scenarios <scenarios overview>` using a high-level language and helpful
Python libraries. A catalog of analysis implementations is included.

The design of hotsos is oriented around “plugins” that provide easy access to
the state of applications and subsystems. Hotsos is run against a
:ref:`data root` which can either be the host it is run on or a
`sosreport <https://github.com/sosreport/sos>`_. The output is a summary
containing key information from each plugin along with any issuses or known
bugs detected and suggestions on what actions can be taken to handle them.

Installation Guide
------------------

.. toctree::
   :maxdepth: 2

   install/index
   install/usage

Internals
---------

.. toctree::
   :maxdepth: 2

   contrib/internals


Contributor Guide
-----------------

.. toctree::
   :maxdepth: 2

   Contributor Guide <contrib/index>

