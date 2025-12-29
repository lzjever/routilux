# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import sys
import os

# Add the project root to the path for local development
# In Read the Docs, the package is installed via pip, so this is mainly for local builds
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import version from package
try:
    from routilux import __version__
except ImportError as e:
    raise ImportError(
        f"Failed to import routilux.__version__: {e}. "
        "Make sure the package is installed or the project root is in sys.path."
    ) from e

project = 'Routilux'
copyright = '2024, Routilux Team'
author = 'Routilux Team'
release = __version__  # Full version (e.g., '0.8.1')
version = '.'.join(__version__.split('.')[:2])  # Major.minor version (e.g., '0.8')

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx.ext.todo',
    'sphinx.ext.coverage',
    'sphinx.ext.mathjax',
    'sphinx.ext.githubpages',
    'sphinx_copybutton',  # Add copy button to code blocks
    'sphinx_design',      # Add design components (cards, badges, etc.)
]

templates_path = ['_templates']
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# Use Furo theme (modern, beautiful, and feature-rich)
html_theme = 'furo'
html_static_path = ['_static']
html_logo = None
html_favicon = None

# Furo theme options
html_theme_options = {
    # Sidebar
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
    
    # Footer
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/lzjever/routilux",
            "html": """
                <svg stroke="currentColor" fill="currentColor" stroke-width="0" viewBox="0 0 16 16">
                    <path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"/>
                </svg>
            """,
            "class": "",
        },
    ],
    
    # Source repository (for edit button)
    "source_repository": "https://github.com/lzjever/routilux",
    "source_branch": "main",
    "source_directory": "docs/source/",
}

# Add custom CSS
html_css_files = [
    'custom.css',
]

# Sidebar configuration (Furo uses default, but we can customize)
# html_sidebars = {}  # Use Furo's default sidebar

# -- Extension configuration -------------------------------------------------

# Napoleon settings for Google/NumPy style docstrings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
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

# Autodoc settings
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': False,
    'exclude-members': '__weakref__',
    'show-inheritance': True,
}

autodoc_mock_imports = []

# Intersphinx mapping
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}

# Todo extension
todo_include_todos = True

# -- Options for autodoc ----------------------------------------------------
# Automatically extract type hints
autodoc_typehints = 'description'
autodoc_typehints_description_target = 'documented'

