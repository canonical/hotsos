.. hotsos documentation master file, created by
   sphinx-quickstart on Mon Jun 19 09:55:40 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Installing Hotsos
=================

There are a number of supported ways to install Hotsos as follows.

Debian Package (daily build)
----------------------------

This is the recommended way to install and is updated daily.

.. code-block:: bash

    sudo add-apt-repository ppa:ubuntu-support-team/hotsos
    sudo apt install hotsos

Snap Package
------------

A new build is published to the `snap <https://snapcraft.io/hotsos>`_ edge channel after each commit landed in the main development branch. Builds are promoted to stable once tested.

Please note that the snap is now a `strictly confined snap <https://snapcraft.io/docs/snap-confinement>`_ and therefore only supports `sosreport <https://github.com/sosreport/sos>`_ :ref:`data root` since it will not have access outside of $HOME.

.. code-block:: bash

    sudo snap install hotsos

PyPI
----

A new build is published to `PyPI <https://pypi.org/project/hotsos/>`_ after each commit landed in the main development branch.

NOTE: pipx is recommended instead of pip as it is considered more secure and installs in a venv. Requires Python >= 3.8

.. code-block:: bash

    sudo apt install pipx
    pipx install hotsos

