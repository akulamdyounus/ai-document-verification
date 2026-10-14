# AI Document Verification & Classification System

An enterprise-ready, modular platform for automated document classification, OCR text extraction, structured field parsing, and multi-dimensional digital forensics and tamper analysis.

> **Project Goal**: Enable users to upload any PDF or image document (JPG, JPEG, PNG), detect its category across 10 official types, extract key information with privacy masking, inspect for anomalies across 7 forensic dimensions, and deliver an objective verification verdict.
>
> **Anti-Hallucination & Conservative Verification Policy**:
> - Automated digital forensics and heuristic checks cannot definitively prove legal authenticity or fraud without authoritative registry access.
> - ELA, noise variance, compression artifacts, and metadata editing signatures are **indicators only**.
> - **Absence of detected anomalies is NOT proof of authenticity**. Clean documents default to **"Unable to Verify"** with full transparent check explanations.
> - **"Suspicious"** is returned when meaningful anomalies or contradictions are detected.
> - **"Likely Fake"** is strictly reserved for concurring multi-dimensional evidence (e.g. impossible chronological dates + severe metadata/cloning anomalies).

---

## System Architecture

```
vasim2/
├── backend/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py            # /api/health, /api/upload, /api/analyze/{file_id}
│   │   └── deps.py              # Dependency injection (Database session provider)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── upload_service.py    # Validation, MIME inspection, unique UUIDs, safe storage
│   │   ├── pdf_service.py       # PyMuPDF digital text extraction & page rasterization
│   │   ├── ocr_service.py       # Tesseract OCR engine with OpenCV image preprocessing
│   │   ├── text_normalizer.py   # OCR artifact cleanup, character confusion repair, hyphenation
│   │   ├── document_signatures.py # Signatures & keywords for 10 document categories
│   │   ├── document_classifier.py # Multi-signal scoring engine, ambiguity detection & fallback
│   │   ├── field_extractor.py   # Type-specific regex extractor with PII privacy masking
│   │   ├── image_forensics.py   # Error Level Analysis (ELA) & Local Noise Variance analysis
│   │   ├── copy_move_detector.py # OpenCV ORB 2D keypoint displacement cluster matching
│   │   ├── pdf_forensics.py     # PDF metadata, design tool signatures, timestamp inversion, fonts
│   │   ├── content_consistency.py # Chronological date logic, statement periods, identifier syntax
│   │   ├── fraud_detector.py    # Unified evidence aggregator calculating objective risk score
│   │   └── verification_engine.py # Conservative safety evaluator producing final verdicts
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py           # Pydantic models (AnalysisResponse, ForensicReport, ForensicCheck)
│   │   └── database.py          # SQLite persistence for documents & analysis records
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── file_utils.py        # Magic bytes, extension validation, safe naming
│   │   └── logger.py            # Sanitized logging without exposing sensitive document content
│   ├── main.py                  # FastAPI application with CORS and error handlers
│   ├── config.py                # Pydantic Settings configuration from .env
│   ├── requirements.txt         # Backend Python packages
│   └── tests/
│       ├── __init__.py
│       ├── test_api.py          # API health, upload validation, error flows
│       ├── test_classifier.py   # Classification benchmarks & field masking tests
│       └── test_forensics.py    # Multi-dimensional forensic, copy-move & consistency tests
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Navbar.jsx            # Header with backend and OCR status indicators
│   │   │   ├── FileUpload.jsx        # Drag-and-drop file upload with format/size checks
│   │   │   ├── UploadedPreview.jsx   # Document summary card with Analyze CTA
│   │   │   ├── ProgressStages.jsx    # Visual multi-stage progress tracker
│   │   │   ├── ResultsView.jsx       # Results report: Type, Risk Badge, Forensics, Fields, Limitations
│   │   │   └── ErrorAlert.jsx        # Friendly error notifications
│   │   ├── services/
│   │   │   └── api.js               # REST client for backend endpoints
│   │   ├── App.jsx                  # State machine managing the upload-to-analysis workflow
│   │   ├── main.jsx                 # React root
│   │   └── index.css                # Tailwind CSS styling
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── postcss.config.js
├── uploads/                         # Secure storage for uploaded document files
├── database/                        # Local SQLite database (app.db)
└── README.md
```

---

## Supported Document Categories (Phase 2A)

The classification engine scores evidence dynamically across 10 official categories:
1. **Bank Statement** (Account numbers, IFSC, balances, transaction columns, period boundaries)
2. **Driving Licence** (Licence numbers, validity dates, transport authority stamps)
3. **Passport** (Republic of India, Passport No, Nationality, MRZ checksum zones)
4. **PAN Card** (Income Tax Department, Permanent Account Number 10-char syntax)
5. **Aadhaar** (UIDAI, masked 12-digit format, enrollment IDs, government notices)
6. **Salary Slip** (Earnings, deductions, net pay, basic salary, employee codes)
7. **Invoice** (Invoice numbers, tax breakdowns, itemized tables, GSTIN, totals)
8. **Certificate** (Degree, completion awards, accreditation, signatures)
9. **Utility Bill** (Electricity/water/gas consumer IDs, billing cycles, units consumed)
10. **Tax Return / Form 16** (Assessment year, ITR acknowledgments, gross total income)
11. **Other Document / Unknown** (Safe fallbacks when evidence is generic or conflicting)

---

## Forensic & Tamper Analysis Capabilities (Phase 2B)

### 1. Error Level Analysis (ELA)
- Resaves images to a calibrated 90% JPEG baseline and measures pixel-level reconstruction divergence.
- Detects localized compression discrepancy peaks characteristic of spliced, pasted, or re-saved image regions.

### 2. Local Noise Variance Analysis
- Evaluates 32x32 pixel Laplacian variance across the document matrix.
- Accurately discriminates between uniform digital vector backgrounds and paper scans with digitally erased/smoothed patches.

### 3. Copy-Move Forgery Detection
- Utilizes OpenCV ORB feature extraction and K-Nearest Neighbor descriptor matching.
- Employs spatial displacement vector clustering with strict 2D bounding extent filtering to isolate cloned stamps, duplicated signatures, and cloned photos while preventing false positives from repeating typographical characters along horizontal text lines.

### 4. PDF Metadata & Software Signature Analysis
- Inspects PDF metadata headers (`Creator`, `Producer`, `Title`, `Author`).
- Identifies signatures of design, raster, and editing software (Photoshop, Canva, Illustrator, InDesign, GIMP, iLovePDF, Sejda, PDF24).

### 5. Timestamp Discrepancy & Inversion Forensics
- Parses PDF `CreationDate` and `ModDate` timestamps.
- Flags impossible chronological sequences (Modification date preceding Creation date) and excessive modification delays (>30 days).

### 6. PDF Structural Layer Composition
- Analyzes embedded fonts, text stream layers, and raster image objects to distinguish native vector PDFs from image-only scans.

### 7. Content Consistency & Chronological Validation
- **Date Chronology**: Verifies logical ordering (Date of Birth < Issue Date < Expiry Date) and detects future issue dates.
- **Statement Period Logic**: Validates that statement starting dates precede closing dates.
- **Identifier Syntax**: Validates strict regex format compliance (e.g. PAN `[A-Z]{5}[0-9]{4}[A-Z]{1}`).
- **Invoice Arithmetic**: Checks subtotal/total balance plausibility and flags negative values.

---

## Verification Verdict Engine

| Verdict | Trigger Condition |
| :--- | :--- |
| **Unable to Verify** | Inconclusive classification, text length < 30 chars, OR clean document with 0 anomalies (adhering to the rule that absence of anomalies is not proof of authentic origin). |
| **Suspicious** | At least 1 medium or high severity anomaly detected (e.g. Canva metadata signature, minor timestamp anomaly, inverted statement period). |
| **Likely Fake** | Multiple concurring high-severity indicators (e.g. contradictory dates + severe metadata/copy-move forgery, or Risk Score ≥ 0.70 with 2+ independent warnings). |
| **Likely Genuine** | Reserved exclusively for comprehensive multi-point verified checks. Never assigned solely for absence of anomalies. |

---

---

## Machine Learning Models & Architecture (Phase 2C)

The system incorporates two trained machine learning models alongside deterministic rule-based engines:

### 1. Document Category Classifier (`models/document_classifier_v1.joblib`)
- **Algorithm**: TF-IDF Feature Extraction + Multinomial Logistic Regression (`C=1.0`, `max_iter=500`).
- **N-Gram Range**: Unigrams and bigrams (`ngram_range=(1, 2)`, sublinear term frequency scaling).
- **Supported Classes (9)**: Aadhaar, Bank Statement, Certificate, Driving Licence, Invoice, Other Document, PAN Card, Passport, Salary Slip.
- **Hybrid Ensemble**: Combines statistical ML probability with rule-based regex and keyword signatures. Provides transparent fallback to rule-based classification if the model file is absent or text evidence is sparse.

### 2. Document Tampering Risk Classifier (`models/tamper_risk_classifier_v1.joblib`)
- **Algorithm**: `CalibratedClassifierCV(GradientBoostingClassifier(n_estimators=100, max_depth=4), method='sigmoid', cv=5)`.
- **Feature Vector**: 24 deterministic numerical features extracted by `ForensicFeatureExtractor` covering:
  - Error Level Analysis (ELA mean, std, max, anomaly pixel ratio)
  - 32x32 block local noise variance
  - Image sharpness & defocus blur
  - Intersecting 2D rectangular box splicing corners
  - ORB copy-move cluster counts and candidate matches
  - Image and PDF desktop publishing tool signatures
  - PDF timestamp inversion and creation-modification delays
  - Date chronology and statement period consistency
  - Invoice and bank statement running balance arithmetic discrepancies
  - Bank identity vs. IFSC prefix consistency
- **Held-Out Test Accuracy**: 97.86% (ROC-AUC: 0.9774, Brier Loss: 0.0222).
- **Hybrid Blending**: Weighted risk blending ($0.60 \times \text{ML Risk} + 0.40 \times \text{Rule Risk}$) with critical anomaly overrides and seamless rule-based fallback.

---

## Getting Started

### Prerequisites
- **Python 3.10+**
- **Node.js 18+** & **npm**
- **Tesseract OCR** (Auto-detected on Windows at `C:\Program Files\Tesseract-OCR\tesseract.exe` or set via `TESSERACT_PATH` in `.env`)

### Backend Setup
```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
pytest backend/tests
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend Setup
```powershell
cd frontend
npm install
npm run build     # Verify production build
npm run dev       # Start development server
```
Open your browser at `http://127.0.0.1:5173`.

---

## Test Suite Execution

Run all 102 automated unit, regression, OCR, and forensic tests:
```powershell
.\.venv\Scripts\pytest backend/tests
```
All 102 tests pass with 100% coverage across:
- `backend/tests/test_api.py` (6 tests: API health, upload validation, error flows)
- `backend/tests/test_classifier.py` (20 tests: ML & rule-based classification, field masking)
- `backend/tests/test_field_extraction.py` (11 tests: structured field extraction & normalizer)
- `backend/tests/test_forensics.py` (45 tests: ELA, noise, copy-move, PDF, bank math, ML tamper risk & fallback)
- `backend/tests/test_ocr.py` (11 tests: multi-PSM, image preprocessing & quality scoring)
- `backend/tests/test_preview.py` (9 tests: thumbnail rendering, PDF rasterization, error guards)

---

## Production Deployment Guide

This system is configured for cloud deployment with the backend hosted on **Render** (via Docker or native Python) and the frontend hosted on **Vercel** (React + Vite SPA).

### 1. Pre-Deployment Git Setup

Ensure the repository is initialized and pushed to GitHub or GitLab:

```bash
git init
git add .
git commit -m "chore: prepare AI Document Verification system for Render and Vercel deployment"
git branch -M main
git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPOSITORY>.git
git push -u origin main
```

> **Note on Model Files**: The trained ML models (`models/document_classifier_v1.joblib` ~1.10 MB and `models/tamper_risk_classifier_v1.joblib` ~1.36 MB) are under 2 MB each and are tracked in Git via `.gitignore` exception rules (`!models/*.joblib`).

---

### 2. Backend Deployment on Render

Render hosts the FastAPI backend. You can deploy using **Docker (Recommended)** or **Native Python**:

#### Option A: Docker Service (Recommended for full Tesseract OCR & OpenCV support)

1. Sign in to your [Render Dashboard](https://dashboard.render.com/).
2. Click **New +** > **Web Service**.
3. Connect your Git repository.
4. Render will detect the root [`Dockerfile`](file:///c:/Users/DELL/OneDrive/Desktop/vasim2/Dockerfile).
   - **Name**: `ai-document-verifier-backend`
   - **Runtime**: `Docker`
   - **Instance Type**: `Free`
   - **Region**: Any (e.g. `Oregon (US West)` or `Frankfurt (EU Central)`)
5. Under **Environment Variables**, add:
   - `ENVIRONMENT`: `production`
   - `PORT`: `8000`
   - `CORS_ORIGINS`: `https://<YOUR_VERCEL_APP>.vercel.app,http://localhost:5173` *(Update with your actual Vercel URL once created)*
   - `MAX_FILE_SIZE_MB`: `10`
6. Click **Create Web Service**.
7. Once deployed, note your Render public backend URL:
   `https://<YOUR_RENDER_SERVICE_NAME>.onrender.com`
8. Verify health endpoint in your browser:
   `https://<YOUR_RENDER_SERVICE_NAME>.onrender.com/api/health`

#### Option B: Native Python Service

If using native Python without Docker:
- **Build Command**: `./render-build.sh` (or `pip install -r backend/requirements.txt`)
- **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- *Note*: If Tesseract OCR is not installed on the native host, the system automatically runs in fallback mode (`ocr_available: false`) with full support for image forensics, PDF forensics, ML fraud risk detection, and rule-based checks.

---

### 3. Frontend Deployment on Vercel

1. Sign in to your [Vercel Dashboard](https://vercel.com/).
2. Click **Add New...** > **Project** and import your Git repository.
3. Configure the project:
   - **Framework Preset**: `Vite`
   - **Root Directory**: Click *Edit* and select `frontend` (or leave as root, root `vercel.json` will route to `frontend`)
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. Under **Environment Variables**, add:
   - `VITE_API_URL`: `https://<YOUR_RENDER_SERVICE_NAME>.onrender.com` *(Your Render backend URL from Step 2)*
5. Click **Deploy**.
6. Once deployed, note your Vercel URL (e.g. `https://<YOUR_PROJECT>.vercel.app`).
7. Update `CORS_ORIGINS` on your Render service environment variables to include your Vercel URL if you haven't already.

---

### 4. Verification Checklist

- [ ] Backend health check responds `200 OK` at `https://<RENDER_URL>/api/health`.
- [ ] Frontend opens at `https://<VERCEL_URL>`.
- [ ] Green "Backend Connected" pill appears in the top navigation bar.
- [ ] Uploading a sample PDF or image produces instant preview, type classification, fraud risk assessment, and transparent verification verdict.

