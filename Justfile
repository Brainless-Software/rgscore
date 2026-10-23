#!/usr/bin/env -S just --justfile

set default-list := true

mkdocs:
    mkdocs build & sleep 1 & mkdocs gh-deploy

test:
    pytest tests/test_register.py tests/test_reglist.py

test-cov:
    pytest --cov=rgscore --rootdir=src --cov-report=html tests/test_register.py tests/test_reglist.py; xdg-open htmlcov/index.html

test-cov-all:
    pytest --cov=rgscore --rootdir=src --cov-report=html; xdg-open htmlcov/index.html