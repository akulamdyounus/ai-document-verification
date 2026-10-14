#!/usr/bin/env bash
# Build script for native Python deployment on Render (fallback when Docker is not chosen)
set -e

echo "=== Installing Python dependencies ==="
pip install --upgrade pip
pip install -r backend/requirements.txt

echo "=== Verifying model files ==="
python -c "import os; assert os.path.exists('models/document_classifier_v1.joblib'), 'Document classifier model missing'; assert os.path.exists('models/tamper_risk_classifier_v1.joblib'), 'Tamper risk model missing'; print('All ML models verified successfully!')"

echo "=== Build finished successfully ==="
