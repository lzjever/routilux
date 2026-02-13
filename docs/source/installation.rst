Installation
============

Routilux can be installed in several ways depending on your needs. This guide covers all installation methods for Mac and Linux.

One-Line Install (Recommended)
------------------------------

The easiest way to install Routilux on Mac or Linux:

.. code-block:: bash

   # Auto-detects best method (uv > pipx > pip)
   curl -fsSL https://raw.githubusercontent.com/lzjever/routilux/main/install.sh | bash

   # Or with wget
   wget -qO- https://raw.githubusercontent.com/lzjever/routilux/main/install.sh | bash

**Options:**

.. code-block:: bash

   # Use pipx instead of uv
   METHOD=pipx curl -fsSL https://raw.githubusercontent.com/lzjever/routilux/main/install.sh | bash

   # Install specific version
   VERSION=0.14.0 curl -fsSL https://raw.githubusercontent.com/lzjever/routilux/main/install.sh | bash

**What the installer does:**

1. Detects your OS and architecture
2. Checks Python version (requires 3.8+)
3. Installs uv (or pipx) if not present
4. Installs routilux with CLI dependencies
5. Verifies the installation

pipx (Recommended for CLI)
--------------------------

`pipx <https://pypa.github.io/pipx/>`_ is the recommended way to install Python CLI tools. It creates an isolated virtual environment for each tool, preventing dependency conflicts.

**Install pipx:**

.. code-block:: bash

   # macOS (with Homebrew)
   brew install pipx
   pipx ensurepath

   # Linux (Ubuntu/Debian)
   sudo apt install pipx
   pipx ensurepath

   # Linux (with pip)
   pip install --user pipx
   pipx ensurepath

**Install Routilux:**

.. code-block:: bash

   # Install CLI with all dependencies
   pipx install "routilux[cli]"

   # Verify installation
   routilux --version

**Benefits:**

- ✅ Completely isolated environment
- ✅ No conflicts with other Python packages
- ✅ Global CLI access
- ✅ Easy updates: ``pipx upgrade routilux``
- ✅ Easy uninstall: ``pipx uninstall routilux``

uv tool (Modern Alternative)
----------------------------

`uv <https://github.com/astral-sh/uv>`_ is a fast Python package installer that can also manage CLI tools.

**Install uv:**

.. code-block:: bash

   # macOS/Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh

**Install Routilux:**

.. code-block:: bash

   uv tool install "routilux[cli]"

   # Verify
   routilux --version

**Benefits:**

- ✅ Very fast (written in Rust)
- ✅ Same isolation as pipx
- ✅ Modern Python tooling

Homebrew (macOS / Linux)
------------------------

For users who prefer native package management.

**Install:**

.. code-block:: bash

   # Add the tap
   brew tap lzjever/routilux

   # Install
   brew install routilux

   # Or install directly
   brew install lzjever/routilux/routilux

**Benefits:**

- ✅ Native package manager feel
- ✅ Automatic updates with ``brew upgrade``
- ✅ Easy uninstall with ``brew uninstall``

pip (Standard Python)
---------------------

For library use or when you want Routilux in your Python environment.

**Library Only:**

.. code-block:: bash

   pip install routilux

**With CLI Support:**

.. code-block:: bash

   pip install "routilux[cli]"

Installing from Source
----------------------

Clone the repository and install:

.. code-block:: bash

   git clone https://github.com/lzjever/routilux.git
   cd routilux

   # Development mode with CLI
   pip install -e ".[cli,dev]"

Requirements
------------

- **Python**: 3.8 to 3.14
- **Core dependency**: `serilux >= 0.3.1`

**CLI Dependencies** (included with ``[cli]`` extra):

- `click >= 8.0`
- `pyyaml >= 6.0`
- `rich >= 13.0.0`

Verifying Installation
----------------------

After installation, verify everything works:

.. code-block:: bash

   # Check version
   routilux --version

   # Show help
   routilux --help

Test the Python import:

.. code-block:: python

   from routilux import Flow, Routine
   print("Installation successful!")

Troubleshooting
---------------

**Command not found: routilux**

- If using pipx: Run ``pipx ensurepath`` and restart your shell
- If using pip: Ensure your Python ``bin`` directory is in PATH

**ImportError**

- Ensure you're using Python 3.8+
- Try reinstalling: ``pipx reinstall routilux``

**Permission denied**

- Use ``pipx`` or ``uv tool`` instead of system pip
- Or use ``pip install --user``

**Version mismatch**

.. code-block:: bash

   # pipx
   pipx upgrade routilux

   # uv
   uv tool upgrade routilux

   # Homebrew
   brew upgrade routilux
