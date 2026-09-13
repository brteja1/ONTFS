#!/usr/bin/env bash
set -e

# Change to the parent directory (project root) so it can be run from anywhere
cd "$(dirname "$0")/.."

echo "Running OntFS test suite..."

# Ensure PYTHONPATH includes the current directory
export PYTHONPATH="."

# Run the unittests with verbose output
python3 -m unittest discover -s tests -v

echo "All tests passed successfully!"
