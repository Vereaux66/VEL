# Contributing to ANVEL AI Trading System

Thank you for your interest in contributing to ANVEL! This document provides guidelines and workflows for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Pull Request Process](#pull-request-process)
- [Commit Message Convention](#commit-message-convention)

## Code of Conduct

### Our Standards

- Be respectful and inclusive
- Welcome diverse perspectives
- Focus on constructive criticism
- Prioritize the community's best interests

### Unacceptable Behavior

- Harassment or discrimination
- Trolling or insulting comments
- Publishing private information
- Unprofessional conduct

## Getting Started

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- Git
- AWS CLI (for deployment)
- Terraform (for infrastructure)

### Local Development Setup

1. **Fork and clone the repository**

```bash
git clone https://github.com/YOUR_USERNAME/VEL.git
cd VEL
```

2. **Run bootstrap script**

```bash
./scripts/bootstrap.sh
```

This will:
- Create virtual environment
- Install dependencies
- Set up pre-commit hooks
- Create `.env` from template
- Build Docker images
- Run tests

3. **Start development environment**

```bash
# Option 1: Docker Compose (recommended)
docker-compose --profile local up -d

# Option 2: Manual
source venv/bin/activate
python ANVEL_MASTER.py
```

4. **Verify setup**

```bash
# Check health endpoint
curl http://localhost:8080/health

# Run tests
pytest tests/
```

## Development Workflow

### Branch Strategy

- `main`: Production-ready code
- `develop`: Integration branch for features
- `feature/*`: New features
- `bugfix/*`: Bug fixes
- `hotfix/*`: Urgent production fixes

### Creating a Feature Branch

```bash
# Update main
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/your-feature-name
```

### Making Changes

1. Write code following [Coding Standards](#coding-standards)
2. Add tests for new functionality
3. Update documentation if needed
4. Run linters and tests locally
5. Commit with meaningful messages

```bash
# Format code
black .
isort .

# Lint
flake8 .
ruff check .

# Type check
mypy .

# Security scan
bandit -r . -ll

# Test
pytest tests/ --cov
```

### Pre-commit Hooks

Pre-commit hooks automatically run on every commit:

```bash
# Manually run pre-commit
pre-commit run --all-files
```

Hooks include:
- Black (formatting)
- isort (import sorting)
- Ruff (linting)
- Bandit (security)
- detect-secrets (secret scanning)

## Coding Standards

### Python Style Guide

Follow [PEP 8](https://pep8.org/) with these specifics:

- **Line length**: 88 characters (Black default)
- **Imports**: Sorted with isort (black profile)
- **Type hints**: Use for public functions
- **Docstrings**: Google style for modules, classes, functions

Example:

```python
def calculate_position_size(
    account_balance: float,
    risk_percent: float,
    stop_loss_percent: float
) -> float:
    """Calculate position size based on risk parameters.
    
    Args:
        account_balance: Total account balance in USD
        risk_percent: Percentage of account to risk (0-100)
        stop_loss_percent: Stop loss as percentage (0-100)
    
    Returns:
        Position size in USD
    
    Raises:
        ValueError: If parameters are invalid
    """
    if risk_percent <= 0 or risk_percent > 100:
        raise ValueError("Risk percent must be between 0 and 100")
    
    risk_amount = account_balance * (risk_percent / 100)
    position_size = risk_amount / (stop_loss_percent / 100)
    
    return position_size
```

### File Organization

```
anvel_module_name.py  # Single module per file
tests/
  test_module_name.py  # Corresponding test file
docs/
  module_name.md       # Documentation
```

### Naming Conventions

- **Modules**: `anvel_feature_name.py`
- **Classes**: `PascalCase` (e.g., `ANVELBrain`)
- **Functions**: `snake_case` (e.g., `calculate_position_size`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_POSITION_SIZE`)
- **Private**: Prefix with `_` (e.g., `_internal_method`)

## Testing Guidelines

### Test Structure

```python
# tests/test_feature.py
import pytest
from unittest.mock import Mock, patch


class TestFeatureName:
    """Tests for FeatureName class."""
    
    def test_basic_functionality(self):
        """Test basic functionality works correctly."""
        # Arrange
        input_data = {"key": "value"}
        
        # Act
        result = function_under_test(input_data)
        
        # Assert
        assert result == expected_output
    
    def test_edge_case(self):
        """Test handling of edge cases."""
        with pytest.raises(ValueError):
            function_under_test(invalid_input)
    
    @patch('module.external_dependency')
    def test_with_mock(self, mock_dependency):
        """Test with mocked dependencies."""
        mock_dependency.return_value = mock_data
        result = function_under_test()
        assert result is not None
```

### Test Coverage

- **Target**: ≥80% coverage
- **Required**: All new features must have tests
- **Encouraged**: Test edge cases and error conditions

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_feature.py

# Specific test
pytest tests/test_feature.py::TestFeatureName::test_basic_functionality

# With coverage
pytest --cov --cov-report=html

# Specific markers
pytest -m unit           # Unit tests only
pytest -m integration    # Integration tests only
pytest -m "not slow"     # Skip slow tests
```

## Pull Request Process

### Before Submitting

- [ ] All tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] Commit messages follow convention
- [ ] Branch is up-to-date with main

### Submitting Pull Request

1. Push your branch to GitHub:
```bash
git push origin feature/your-feature-name
```

2. Create Pull Request on GitHub:
   - Use descriptive title
   - Reference related issues
   - Describe changes made
   - List breaking changes (if any)
   - Add screenshots (for UI changes)

3. Request review from maintainers

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing completed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] Documentation updated
- [ ] No new warnings generated
- [ ] Tests pass locally
- [ ] CHANGELOG.md updated
```

### Review Process

1. Automated checks must pass:
   - CI pipeline (linting, tests, security)
   - Code coverage ≥80%
   - No security vulnerabilities

2. Code review by maintainer:
   - Code quality and style
   - Test coverage
   - Documentation
   - Performance implications

3. Feedback addressed and approved

4. Merged to develop branch

## Commit Message Convention

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `ci`: CI/CD changes
- `build`: Build system changes

### Examples

```bash
# Feature
git commit -m "feat(brain): add transformer model for pattern recognition"

# Bug fix
git commit -m "fix(trade-engine): prevent duplicate order submission"

# Documentation
git commit -m "docs(readme): update installation instructions"

# Breaking change
git commit -m "feat(api)!: change authentication to JWT

BREAKING CHANGE: Session-based auth removed. All clients must use JWT tokens."
```

## Issue Reporting

### Bug Reports

Include:
- Description of the issue
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment details
- Error messages/logs
- Screenshots (if applicable)

### Feature Requests

Include:
- Use case description
- Proposed solution
- Alternative solutions considered
- Additional context

## Development Best Practices

### Security

- Never commit secrets or API keys
- Use environment variables for configuration
- Validate all user inputs
- Use parameterized SQL queries
- Keep dependencies updated

### Performance

- Profile code for bottlenecks
- Use async/await for I/O operations
- Cache expensive computations
- Optimize database queries
- Monitor resource usage

### Documentation

- Update README.md for user-facing changes
- Add docstrings to new functions/classes
- Update API documentation
- Include code examples
- Document breaking changes

## Getting Help

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and discussions
- **Documentation**: `/docs` directory
- **Code Examples**: `/examples` directory

## Recognition

Contributors will be recognized in:
- CHANGELOG.md
- GitHub contributors page
- Annual contributor report

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (MIT License).

---

Thank you for contributing to ANVEL! 🚀
