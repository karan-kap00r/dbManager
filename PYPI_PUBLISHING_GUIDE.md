# 🚀 PyPI Publishing Guide for dbPorter

This guide will walk you through the complete process of publishing dbPorter to PyPI.

## 📋 Prerequisites

1. **PyPI Account**: Create accounts on both PyPI and TestPyPI
   - [PyPI](https://pypi.org/account/register/) - Production package index
   - [TestPyPI](https://test.pypi.org/account/register/) - Testing package index

2. **API Tokens**: Generate API tokens for both accounts
   - Go to Account Settings → API tokens
   - Create a new token with appropriate scope

3. **Required Tools**: Install build and upload tools
   ```bash
   pip install build twine
   ```

## 🔧 Pre-Publication Checklist

### ✅ 1. Update Package Metadata

**Update `setup.py` and `pyproject.toml`:**
- [ ] Change `author` and `author_email` to your details
- [ ] Update `url` and `project_urls` with your GitHub repository
- [ ] Verify `description` and `keywords` are accurate
- [ ] Check `classifiers` are appropriate

**Update `dbPorter/__init__.py`:**
- [ ] Update `__author__` and `__email__`
- [ ] Verify `__version__` is correct

### ✅ 2. Test Package Locally

```bash
# Test package installation
pip install -e .

# Test CLI commands
dbporter --help
dbporter status

# Test programmatic import
python -c "from dbPorter import set_database_url; print('Import successful!')"
```

### ✅ 3. Build Package

```bash
# Clean previous builds
rm -rf build/ dist/ *.egg-info/

# Build source and wheel distributions
python -m build

# Verify build contents
ls -la dist/
```

### ✅ 4. Test on TestPyPI

```bash
# Upload to TestPyPI
python -m twine upload --repository testpypi dist/*

# Test installation from TestPyPI
pip install --index-url https://test.pypi.org/simple/ dbporter
```

## 🚀 Publishing to PyPI

### Step 1: Final Build

```bash
# Ensure clean build
rm -rf build/ dist/ *.egg-info/

# Build final package
python -m build

# Verify package contents
python -m twine check dist/*
```

### Step 2: Upload to PyPI

```bash
# Upload to production PyPI
python -m twine upload dist/*
```

### Step 3: Verify Installation

```bash
# Install from PyPI
pip install dbporter

# Test installation
dbporter --help
dbporter status

# Test programmatic usage
python -c "from dbPorter import set_database_url; print('Success!')"
```

## 📦 Package Structure

Your final package structure should look like this:

```
dbPorter/
├── dbPorter/                 # Main package
│   ├── __init__.py          # Package initialization
│   ├── main.py              # CLI entry point
│   ├── commands.py          # CLI commands
│   ├── db.py                # Database utilities
│   ├── applier.py           # Migration application
│   ├── executors.py         # SQL executors
│   ├── migration_loader.py  # Migration file loading
│   ├── planner.py           # Migration planning
│   ├── models.py            # SQLAlchemy models
│   └── utils/               # Utility modules
├── examples/                # Example files
├── setup.py                 # Setup configuration
├── pyproject.toml          # Modern Python packaging
├── MANIFEST.in             # Package data inclusion
├── LICENSE                 # MIT License
├── README.md               # Project documentation
├── CHANGELOG.md            # Version history
└── requirements*.txt       # Dependencies
```

## 🔄 Version Management

### Semantic Versioning

Follow [Semantic Versioning](https://semver.org/):
- **MAJOR**: Incompatible API changes
- **MINOR**: New functionality (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Update Version

1. **Update version in `dbPorter/__init__.py`:**
   ```python
   __version__ = "0.1.1"  # New version
   ```

2. **Update `CHANGELOG.md`** with new changes

3. **Commit and tag:**
   ```bash
   git add .
   git commit -m "Release version 0.1.1"
   git tag v0.1.1
   git push origin main --tags
   ```

4. **Build and upload:**
   ```bash
   python -m build
   python -m twine upload dist/*
   ```

## 🛠️ Development Workflow

### Local Development

```bash
# Install in development mode
pip install -e .

# Run tests
pytest

# Format code
black dbPorter/
isort dbPorter/

# Type checking
mypy dbPorter/
```

### CI/CD Integration

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.8'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install build twine
    - name: Build package
      run: python -m build
    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: python -m twine upload dist/*
```

## 📊 Package Statistics

After publishing, you can monitor your package:

- **PyPI Stats**: https://pypi.org/project/dbporter/#history
- **Download Stats**: https://pepy.tech/project/dbporter
- **GitHub Insights**: Repository insights and traffic

## 🎯 Marketing Your Package

### 1. GitHub Repository
- [ ] Create comprehensive README
- [ ] Add badges for PyPI version, Python support, etc.
- [ ] Include examples and documentation
- [ ] Set up GitHub Pages for documentation

### 2. PyPI Package Page
- [ ] Ensure README renders correctly
- [ ] Add proper keywords for discoverability
- [ ] Include screenshots or GIFs in README

### 3. Community Engagement
- [ ] Share on Reddit (r/Python, r/Database)
- [ ] Post on Twitter/LinkedIn
- [ ] Write blog posts about the tool
- [ ] Submit to Python Weekly newsletter

## 🔍 Troubleshooting

### Common Issues

1. **Package name conflicts**: Ensure `dbporter` is available on PyPI
2. **Build errors**: Check `setup.py` and `pyproject.toml` syntax
3. **Import errors**: Verify all imports use relative paths
4. **Missing files**: Check `MANIFEST.in` includes all necessary files

### Debug Commands

```bash
# Check package metadata
python setup.py --name --version

# Validate package
python -m twine check dist/*

# Test package installation
pip install --force-reinstall dist/*.whl
```

## 🎉 Success!

Once published, users can install and use dbPorter:

```bash
# Install from PyPI
pip install dbporter

# Use the CLI
dbporter --help
dbporter init-db
dbporter autogenerate -m "Initial schema"
dbporter apply

# Use programmatically
from dbPorter import set_database_url
set_database_url("postgresql://user:pass@host:port/db")
```

Congratulations! Your database migration tool is now available to the Python community! 🚀
