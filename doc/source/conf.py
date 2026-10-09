# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import datetime

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "hotsos"
author = "Canonical Ltd."
# The theme appends the author to the copyright line, so keep this to the year.
project_copyright = f"2023-{datetime.date.today().year}"

# The title displayed for the documentation in the sidebar.
html_title = project + " documentation"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "canonical_sphinx",
    "sphinx.ext.autosectionlabel",
    "sphinx_reredirects",
]

# Resolve section labels by their (unique) title across the whole project so
# that the existing :ref:`Title` cross-references keep working after the
# documentation was reorganised.
autosectionlabel_prefix_document = False

# The scenario catalog intentionally repeats subsection titles (e.g. "Common")
# across plugins, so silence autosectionlabel's duplicate-label warnings.
suppress_warnings = ["autosectionlabel.*"]

templates_path = ["_templates"]
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output
#
# canonical-sphinx provides a design override of the Furo theme for
# Canonical-branded documentation. Some settings must be part of the
# html_context dictionary, while others are at root level.

html_static_path = ["_static"]

html_context = {
    # Product website (without "https://").
    "product_page": "github.com/canonical/hotsos",
    # Product tag (the mark shown in the header).
    "product_tag": "_static/hotsos.png",
    # Project author, inherited from above.
    "author": author,
    # Project license.
    "license": {
        "name": "Apache-2.0",
        "url": "https://github.com/canonical/hotsos/blob/main/LICENSE",
    },
    # GitHub project URL, enables the edit and issue links.
    "github_url": "https://github.com/canonical/hotsos",
    "repo_default_branch": "main",
    "repo_folder": "/doc/",
    "github_issues": "enabled",
    # Previous / Next navigation buttons at the bottom of pages.
    "sequential_nav": "both",
    "display_contributors": False,
}

# Enables the "Edit this page" button.
html_theme_options = {
    "source_edit_link": "https://github.com/canonical/hotsos",
}

# Links to ignore when checking links.
linkcheck_ignore = []

# MyST extensions (for any Markdown pages).
myst_extensions = []

# Redirects from the previous documentation layout to the new Diátaxis
# structure so that existing links keep working
# (https://documatt.gitlab.io/sphinx-reredirects/usage.html).
redirects = {
    "install/index": "../how-to/install.html",
    "install/usage": "../how-to/run-an-analysis.html",
    "contrib/index": "../how-to/contributing.html",
    "contributing": "how-to/contributing.html",
    "contrib/scenarios": "../explanation/scenarios.html",
    "contrib/events": "../explanation/events.html",
    "contrib/writing_checks_overview": "../how-to/write-checks.html",
    "contrib/testing": "../how-to/test-checks.html",
    "contrib/internals": "../explanation/architecture.html",
    "contrib/language_ref/index": "../../reference/language/index.html",
    "contrib/language_ref/internals": "../../explanation/how-checks-work.html",
    "contrib/language_ref/property_ref/index":
        "../../../reference/language/index.html",
    "contrib/language_ref/property_ref/main_properties":
        "../../../reference/language/principal-properties.html",
    "contrib/language_ref/property_ref/shared_properties":
        "../../../reference/language/shared-properties.html",
    "contrib/language_ref/property_ref/requirement_types":
        "../../../reference/language/requirement-types.html",
}
