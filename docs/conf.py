# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import sys
from pathlib import Path

# Add the project root to the Python path
docs_dir = Path(__file__).parent
project_root = docs_dir.parent
sys.path.insert(0, str(project_root / "src"))

project = "FolioClient"
copyright = "2025, EBSCO Information Services, Inc."
author = "Brooks Travis"

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
# Read version from pyproject.toml
try:
    import tomllib
except ImportError:
    import tomli as tomllib

with open(project_root / "pyproject.toml", "rb") as f:
    pyproject_data = tomllib.load(f)

version = pyproject_data["project"]["version"]
release = version

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",  # Automatic documentation from docstrings
    "sphinx.ext.autosummary",  # Generate autodoc summaries
    "sphinx.ext.viewcode",  # Add links to highlighted source code
    "sphinx.ext.napoleon",  # Support for Google and NumPy style docstrings
    "sphinx.ext.intersphinx",  # Link to other project's documentation
    "sphinx.ext.githubpages",  # GitHub Pages support
    "sphinx.ext.coverage",  # Check documentation coverage
    "sphinx.ext.doctest",  # Test snippets in the documentation
    "myst_parser",  # Markdown support
]

coverage_show_missing_items = True

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Source file suffixes ---------------------------------------------------
source_suffix = {
    ".rst": None,
    ".md": "myst_parser",
}

# -- MyST configuration ------------------------------------------------------
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "html_admonition",
    "html_image",
    "tasklist",
]
myst_heading_anchors = 3

# -- HTML output configuration -----------------------------------------------
html_title = "FolioClient Documentation"

# -- Options for HTML output -------------------------------------------------
html_theme = "sphinx_book_theme"
html_static_path = ["_static"]

# Theme options for sphinx-book-theme
html_theme_options = {
    "repository_url": "https://github.com/FOLIO-FSE/FolioClient",
    "use_repository_button": True,
    "use_issues_button": True,
    "use_edit_page_button": True,
    "repository_branch": "master",
    "path_to_docs": "docs",
    "home_page_in_toc": True,
    "show_navbar_depth": 3,
    "show_toc_level": 2,
    "navigation_with_keys": True,
    "collapse_navigation": True,
    "use_sidenotes": False,
    "toc_title": "Contents",
}

# -- Extension configuration -------------------------------------------------

# -- Options for autodoc ----------------------------------------------------
autodoc_member_order = "bysource"
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}

# -- Options for autosummary ------------------------------------------------
autosummary_generate = True

# -- Options for napoleon (Google/NumPy docstring support) ------------------
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = False
napoleon_type_aliases = None
napoleon_attr_annotations = True

# -- Options for intersphinx extension ---------------------------------------
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# -- Options for doctest ----------------------------------------------------
doctest_global_setup = """
import asyncio
from unittest.mock import Mock, patch
from folioclient import FolioClient

# Mock the authentication for doctests
def mock_folio_client():
    client = Mock(spec=FolioClient)
    client.folio_get.return_value = {"users": [{"username": "admin"}], "totalRecords": 1}
    return client
"""

# -- Custom configuration ---------------------------------------------------
# The suffix(es) of source filenames.
source_suffix = {
    ".rst": "restructuredText",
    ".md": "markdown",
}

# The master toctree document.
master_doc = "index"
root_doc = "index"

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = ["_build", "**.ipynb_checkpoints"]

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "sphinx"

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = False

# -- Options for HTML output -------------------------------------------------
html_title = f"{project} {version} documentation"
html_short_title = project

# Custom sidebar templates, must be a dictionary that maps document names
# to template names.
# Note: sphinx-book-theme handles its own sidebar navigation automatically
# html_sidebars = {
#     '**': [
#         'relations.html',  # needs 'show_related': True theme option to display
#         'searchbox.html',
#     ]
# }

# Additional templates that should be rendered to pages, maps page names to
# template names.
# html_additional_pages = {}

# If false, no module index is generated.
html_domain_indices = False

# If false, no index is generated.
html_use_index = False

# If true, the index is split into individual pages for each letter.
html_split_index = False

# If true, links to the reST sources are added to the pages.
html_show_sourcelink = True

# If true, "Created using Sphinx" is shown in the HTML footer. Default is True.
html_show_sphinx = True

# If true, "(C) Copyright ..." is shown in the HTML footer. Default is True.
html_show_copyright = True

# If true, an OpenSearch description file will be output, and all pages will
# contain a <link> tag referring to it. The value of this option must be the
# base URL from which the finished HTML is served.
# html_use_opensearch = ''

# Language to be used for generating the HTML full-text search index.
# Sphinx supports the following languages:
#   'da', 'de', 'en', 'es', 'fi', 'fr', 'hu', 'it', 'ja'
#   'nl', 'no', 'pt', 'ro', 'ru', 'sv', 'tr', 'zh'
html_search_language = "en"
