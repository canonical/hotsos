.. hotsos documentation master file, created by
   sphinx-quickstart on Mon Jun 19 15:27:27 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to hotsos's documentation!
==================================

Use hotsos to implement repeatable analysis and extract useful information from common cloud applications and subsystems. Write analyses :ref:`scenarios` using a high-level language, leveraging Python libaries to help extract information. A catalog of analysis implementations is included. The code is organised as “plugins” that implement functionality specific to an application or subsystem.

Hotsos works against a "data root" which can be a host i.e. '/' or a `sosreport <https://github.com/sosreport/sos>`_. The output is a summary containing key information from each plugin along with any issuses or known bugs detected and suggestions on what actions can be taken to handle them.

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

   Architecture <contrib/plugins>


Contributor Guide
-----------------

.. toctree::
   :maxdepth: 2

   Contributor Guide <contrib/index>

