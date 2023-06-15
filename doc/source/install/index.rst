.. hotsos documentation master file, created by
   sphinx-quickstart on Mon Jun 19 09:55:40 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Installing Hotsos
=================

There is more than one supported way to install Hotsos as follows:

Debian Package (daily build)
----------------------------

This is the recommended way to install and is updated daily.

.. code-block:: bash

    sudo add-apt-repository ppa:ubuntu-support-team/hotsos
    sudo apt install hotsos

Snap Package
------------

NOTE: this is now a strictly confined snap and so only supports sosreport data root since it will not have access outside of $HOME.

.. code-block:: bash

    sudo snap install hotsos

PyPi
----

NOTE: pipx is recommended instead of pip as it is considered more secure and installs in a venv. Requires Python >= 3.8

.. code-block:: bash

    sudo apt install pipx
    pipx install hotsos

