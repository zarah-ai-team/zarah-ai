# Travel Itinerary Chatbot (Dev)

Quick notes for development and troubleshooting:

- This project depends on `python-docx` (package name: `python-docx`, import as `docx`). Some OS/package managers have a conflicting package named `docx` which is broken and causes an import error referencing a non-existent `exceptions` module.

Troubleshooting steps if you see `ModuleNotFoundError: No module named 'exceptions'` when importing `docx`:

1. Uninstall any conflicting `docx` package:

```powershell
python -m pip uninstall docx -y
```

2. Install the correct `python-docx` package:

```powershell
python -m pip install python-docx==0.8.11
```

3. Verify imports work in Python:

```powershell
python -c "import docx; print('docx OK', docx.__version__)"
```

If the import still fails, try creating a clean virtual environment and reinstalling the requirements:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```
