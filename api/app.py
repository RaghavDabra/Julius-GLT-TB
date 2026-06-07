from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import pandas as pd, numpy as np
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.decomposition import PCA
from sklearn.metrics import r2_score
import traceback, os, io, json, base64, math, pickle, hashlib, uuid, datetime, re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import openai
import shap

app = Flask(__name__)
CORS(app)

# File paths for saving models and scalers.
MODEL_PATH = "best_model.pkl"
FEATURE_SCALER_PATH = "feature_scaler.pkl"
TARGET_SCALER_PATH = "target_scaler.pkl"

def _require_openai_api_key():
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("Missing OPENAI_API_KEY environment variable.")
    openai.api_key = key

RUNS = {}

def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def _ensure_run(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        run = {"run_id": run_id, "created_at": _now_iso(), "audit_log": [], "audit_events": []}
        RUNS[run_id] = run
    if "audit_events" not in run:
        run["audit_events"] = []
    if "audit_log" not in run:
        run["audit_log"] = []
    return run

def _append_audit_event(run_id: str, event_type: str, step: str, details: dict):
    run = _ensure_run(run_id)
    event = {
        "id": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "eventType": event_type,
        "step": step,
        "details": details or {},
        "runId": run_id,
    }
    run["audit_events"].append(event)
    run["audit_log"].append({"ts": event["timestamp"], "event": event_type, "step": step})
    return event

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _read_csv_from_filestorage(file_storage):
    data = file_storage.read()
    if not data:
        raise ValueError("Empty file.")
    checksum = _sha256_bytes(data)
    try:
        df = pd.read_csv(io.BytesIO(data))
    except Exception:
        df = pd.read_csv(io.BytesIO(data), encoding_errors="replace")
    return df, checksum

def _read_pdf_bytes_from_filestorage(file_storage):
    data = file_storage.read()
    if not data:
        raise ValueError("Empty PDF file.")
    checksum = _sha256_bytes(data)
    return data, checksum

# -----------------------------------------------------------------------------
# Utility: Convert numpy/pandas types to native Python types.
# -----------------------------------------------------------------------------
def convert_types(obj):
    if isinstance(obj, dict):
        return {k: convert_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_types(item) for item in obj]
    elif isinstance(obj, (np.float32, np.float64)):
        return float(obj) if not np.isnan(obj) else None
    elif isinstance(obj, float):
        return obj if not math.isnan(obj) else None
    elif isinstance(obj, (np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    else:
        return obj

# -----------------------------------------------------------------------------
# Preprocess Endpoint
# -----------------------------------------------------------------------------
@app.route('/api/preprocess', methods=['POST'])
def preprocess_endpoint():
    """
    Reads the CSV file, automatically detects numeric, categorical, and date columns,
    and determines which columns to exclude (based on keywords). It then stores the 
    original raw data in app.config['RAW_DATA'] (for training) and returns the detected
    column types for display/analysis.
    """
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if file.filename == '' or not file.filename.endswith('.csv'):
            return jsonify({'error': 'Invalid file'}), 400

        # Read the CSV into a raw DataFrame.
        df_raw = pd.read_csv(file)
        app.config['RAW_DATA'] = df_raw.to_dict(orient='records')

        # Parse options (e.g. target_column if provided)
        options = json.loads(request.form.get('options', '{}'))
        columnTypes = json.loads(request.form.get('columnTypes', '{}'))
        target_column = options.get("target_column", None)
        do_format_date   = options.get("formatDates", True)
        do_drop_empty    = options.get("dropEmpty", True)
        do_drop_missing  = options.get("dropMissing", True)
        do_fill_missing  = options.get("fillMissing", False)
        do_scale         = options.get("scaleNumeric", True)
        do_encode        = options.get("encodeCategorical", True)
        do_pca           = options.get("performPCA", False)
        do_corr          = options.get("showCorrelation", False)
        detect_only      = options.get("detectOnly", False)

        # Auto-detect column types.
        excluded_keywords = ['id', 'number', 'code', 'identifier']
        numeric_cols = df_raw.select_dtypes(include=['number']).columns.tolist()
        date_cols = []
        categorical_cols = []
        date_format = '%d/%m/%Y'
        for col in df_raw.select_dtypes(include=['object']).columns:
            try:
                # Try parsing using the specified format
                pd.to_datetime(df_raw[col].dropna().iloc[:5], format=date_format)
                date_cols.append(col)
            except Exception:
                categorical_cols.append(col)
        excluded_cols = [col for col in df_raw.columns if any(kw in col.lower() for kw in excluded_keywords)]
        if target_column:
            numeric_cols = [col for col in numeric_cols if col != target_column]

        columns_to_process = {
            "numeric": numeric_cols,
            "categorical": categorical_cols,
            "date": date_cols,
            "excluded": excluded_cols
        }

        # If only auto-detection is requested, return the detected types immediately.
        if detect_only:
            detected_column_types = {}
            for col in df_raw.columns:
                if col in numeric_cols:
                    detected_column_types[col] = "numeric"
                elif col in categorical_cols:
                    detected_column_types[col] = "categorical"
                elif col in date_cols:
                    detected_column_types[col] = "date"
                else:
                    detected_column_types[col] = "exclude"
            response = {
                "message": "Auto detection completed successfully!",
                "columns": columns_to_process,
                "summary": {"shape": df_raw.shape, "columns": df_raw.columns.tolist()},
                "detected_column_types": detected_column_types
            }
            return jsonify(convert_types(response))

        # For display/analysis, perform additional transformations on a copy.
        df = df_raw.copy()
        if do_format_date and date_cols:
            for col in date_cols:
                try:
                    df[col] = pd.to_datetime(df[col], errors='coerce', format=date_format).dt.strftime(date_format)
                except Exception:
                    pass
        if do_drop_empty:
            df = df.dropna(axis=1, how='all')
        if do_drop_missing:
            df = df.dropna()
        if do_fill_missing:
            for col in df.columns:
                if col in numeric_cols:
                    df[col].fillna(df[col].mean(), inplace=True)
                elif col in categorical_cols:
                    df[col].fillna(df[col].mode()[0], inplace=True)
        if do_scale and numeric_cols:
            scaler = StandardScaler()
            numeric_cols_existing = [col for col in numeric_cols if col in df.columns]
            if numeric_cols_existing:
                df[numeric_cols_existing] = scaler.fit_transform(df[numeric_cols_existing])
        encoders = {}
        if do_encode and categorical_cols:
            for col in categorical_cols:
                le = LabelEncoder()
                df[col] = le.fit_transform(df[col].astype(str))
                encoders[col] = list(le.classes_)

        # Optional PCA and correlation (for display only)
        pca_result = {}
        if do_pca and numeric_cols:
            try:
                numeric_data = df[numeric_cols]
                scaled_data = StandardScaler().fit_transform(numeric_data)
                pca = PCA(n_components=scaled_data.shape[1])
                pca.fit(scaled_data)
                cum_var = np.cumsum(pca.explained_variance_ratio_)
                plt.figure()
                plt.plot(range(1, len(cum_var)+1), cum_var, marker='o', linestyle='--')
                plt.title('Cumulative Variance Explained by PCA Components')
                plt.xlabel('Number of Components')
                plt.ylabel('Cumulative Variance')
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                plt.close()
                buf.seek(0)
                cum_var_img = base64.b64encode(buf.read()).decode('utf-8')

                loadings = pd.DataFrame(pca.components_, columns=numeric_cols,
                                        index=[f'PC{i+1}' for i in range(len(pca.components_))])
                plt.figure(figsize=(10,8))
                sns.heatmap(loadings, annot=True, cmap='coolwarm')
                plt.title('PCA Loadings')
                buf2 = io.BytesIO()
                plt.savefig(buf2, format='png')
                plt.close()
                buf2.seek(0)
                pca_load_img = base64.b64encode(buf2.read()).decode('utf-8')

                pca_result = {
                    'cumulative_variance_plot': cum_var_img,
                    'pca_loadings_heatmap': pca_load_img,
                    'explained_variance': pca.explained_variance_ratio_.tolist()
                }
            except Exception as e:
                pca_result = {'error': str(e)}
        corr_matrix = {}
        if do_corr and numeric_cols:
            numeric_df = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
            corr = numeric_df.corr()
            corr = corr.where(pd.notnull(corr), None)
            corr_matrix = corr.to_dict()

        detected_column_types = {}
        for col in df_raw.columns:
            if col in numeric_cols:
                detected_column_types[col] = "numeric"
            elif col in categorical_cols:
                detected_column_types[col] = "categorical"
            elif col in date_cols:
                detected_column_types[col] = "date"
            else:
                detected_column_types[col] = "exclude"

        response = {
            "message": "Preprocessing completed successfully!",
            "columns": columns_to_process,
            "summary": {"shape": df.shape, "columns": df.columns.tolist()},
            "pca_result": pca_result,
            "correlation_matrix": corr_matrix,
            "encoders": encoders,
            "detected_column_types": detected_column_types
        }
        return jsonify(convert_types(response))
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def _canonicalize_columns(df: pd.DataFrame) -> list[str]:
    return [str(c) for c in df.columns.tolist()]

def _col_score(col: str, keywords: list[str]) -> float:
    c = col.strip().lower()
    score = 0.0
    for kw in keywords:
        if kw in c:
            score += 1.0
    if score > 0 and (" " in c or "_" in c):
        score += 0.2
    return score

def _suggest_mapping(df: pd.DataFrame, dataset_type: str):
    cols = _canonicalize_columns(df)
    if dataset_type == "gl":
        targets = {
            "account_code": ["account", "acct", "gl account", "account code", "account_number", "account no"],
            "amount": ["amount", "amt", "value", "net", "signed"],
            "debit": ["debit", "dr"],
            "credit": ["credit", "cr"],
            "posting_date": ["date", "posting", "transaction date", "txn date"],
            "journal_id": ["journal", "entry", "je", "voucher", "document", "doc", "reference", "ref", "id"],
            "description": ["description", "narration", "memo", "details"],
        }
    elif dataset_type == "tb":
        targets = {
            "account_code": ["account", "acct", "gl account", "account code", "account_number", "account no"],
            "balance": ["balance", "ending", "closing", "net", "amount", "value"],
            "account_name": ["name", "account name", "description"],
        }
    else:
        raise ValueError("dataset_type must be 'gl' or 'tb'.")

    suggestions = {}
    proposed = {}
    for canonical, keywords in targets.items():
        scored = []
        for col in cols:
            s = _col_score(col, keywords)
            if s > 0:
                scored.append({"column": col, "score": s})
        scored.sort(key=lambda x: x["score"], reverse=True)
        suggestions[canonical] = scored[:5]
        if scored and scored[0]["score"] >= 1.0:
            proposed[canonical] = scored[0]["column"]
        else:
            proposed[canonical] = ""

    return {"dataset_type": dataset_type, "columns": cols, "suggestions": suggestions, "proposed_mapping": proposed}

def _normalize_account_code(value: str, options: dict) -> str:
    v = (value or "").strip()
    if not v:
        return ""

    if options.get("upper", True):
        v = v.upper()

    if options.get("strip_non_alnum", True):
        v = re.sub(r"[^A-Z0-9]", "", v)

    if options.get("drop_leading_zeros", True):
        v = re.sub(r"^0+", "", v)

    return v

def _standardize_gl(df: pd.DataFrame, mapping: dict, normalize_options: dict | None = None):
    account_col = mapping.get("account_code") or ""
    amount_col = mapping.get("amount") or ""
    debit_col = mapping.get("debit") or ""
    credit_col = mapping.get("credit") or ""

    if not account_col or account_col not in df.columns:
        raise ValueError("GL mapping requires a valid 'account_code' column.")

    out = pd.DataFrame()
    out["AccountCode"] = df[account_col].astype(str).str.strip()
    if normalize_options:
        out["AccountCode"] = out["AccountCode"].map(lambda x: _normalize_account_code(x, normalize_options))

    if amount_col and amount_col in df.columns:
        out["Amount"] = pd.to_numeric(df[amount_col], errors="coerce")
    elif debit_col in df.columns and credit_col in df.columns:
        debit = pd.to_numeric(df[debit_col], errors="coerce").fillna(0.0)
        credit = pd.to_numeric(df[credit_col], errors="coerce").fillna(0.0)
        out["Amount"] = debit - credit
    else:
        raise ValueError("GL mapping requires either 'amount' OR both 'debit' and 'credit' columns.")

    out = out.dropna(subset=["AccountCode", "Amount"])
    out["AccountCode"] = out["AccountCode"].replace({"nan": ""})
    out = out[out["AccountCode"] != ""]
    return out

def _standardize_tb(df: pd.DataFrame, mapping: dict, normalize_options: dict | None = None):
    account_col = mapping.get("account_code") or ""
    balance_col = mapping.get("balance") or ""

    if not account_col or account_col not in df.columns:
        raise ValueError("TB mapping requires a valid 'account_code' column.")
    if not balance_col or balance_col not in df.columns:
        raise ValueError("TB mapping requires a valid 'balance' column.")

    out = pd.DataFrame()
    out["AccountCode"] = df[account_col].astype(str).str.strip()
    if normalize_options:
        out["AccountCode"] = out["AccountCode"].map(lambda x: _normalize_account_code(x, normalize_options))
    out["Balance"] = pd.to_numeric(df[balance_col], errors="coerce")
    out = out.dropna(subset=["AccountCode", "Balance"])
    out["AccountCode"] = out["AccountCode"].replace({"nan": ""})
    out = out[out["AccountCode"] != ""]
    return out

def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")

def _parse_dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)

def _hash_duplicate_key(account_code: str, date_iso: str, amount: float | None, description: str) -> str:
    amt = "" if amount is None or (isinstance(amount, float) and math.isnan(amount)) else f"{float(amount):.6f}"
    raw = f"{account_code}|{date_iso}|{amt}|{description.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

@app.route('/api/ingest', methods=['POST'])
def ingest_endpoint():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        dataset_type = (request.form.get("dataset_type") or "").strip().lower()
        if dataset_type not in {"gl", "tb"}:
            return jsonify({'error': "dataset_type must be 'gl' or 'tb'."}), 400

        file = request.files['file']
        if file.filename == '' or not file.filename.lower().endswith('.csv'):
            return jsonify({'error': 'Invalid file (CSV only for this prototype).'}), 400

        run_id = (request.form.get("run_id") or "").strip() or str(uuid.uuid4())
        df, checksum = _read_csv_from_filestorage(file)

        run = _ensure_run(run_id)
        run[dataset_type] = {
            "filename": file.filename,
            "checksum_sha256": checksum,
            "ingested_at": _now_iso(),
            "rows": int(df.shape[0]),
            "columns": _canonicalize_columns(df),
            "dataframe": df,
        }
        _append_audit_event(
            run_id,
            "UPLOAD_RECEIVED",
            "Data Ingestion",
            {"dataset_type": dataset_type, "filename": file.filename, "checksum_sha256": checksum, "rows": int(df.shape[0])},
        )
        RUNS[run_id] = run

        response = {
            "run_id": run_id,
            "dataset_type": dataset_type,
            "filename": file.filename,
            "checksum_sha256": checksum,
            "summary": {"shape": df.shape, "columns": df.columns.tolist()},
            "sample_rows": df.head(3).to_dict(orient="records"),
            "audit_events": run["audit_events"][-50:],
        }
        return jsonify(convert_types(response))
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/suggest-mapping', methods=['POST'])
def suggest_mapping_endpoint():
    try:
        data = request.get_json() or {}
        run_id = (data.get("run_id") or "").strip()
        dataset_type = (data.get("dataset_type") or "").strip().lower()
        if not run_id or run_id not in RUNS:
            return jsonify({"error": "Invalid run_id."}), 400
        if dataset_type not in {"gl", "tb"}:
            return jsonify({"error": "dataset_type must be 'gl' or 'tb'."}), 400
        run = RUNS[run_id]
        if dataset_type not in run or "dataframe" not in run[dataset_type]:
            return jsonify({"error": f"No {dataset_type} dataset ingested for this run."}), 400

        df = run[dataset_type]["dataframe"]
        result = _suggest_mapping(df, dataset_type)
        _append_audit_event(
            run_id,
            "SCHEMA_MAPPING_COMPLETED",
            "AI Schema Mapping",
            {"dataset_type": dataset_type, "proposed_mapping": result.get("proposed_mapping", {}), "suggestions": result.get("suggestions", {})},
        )
        return jsonify(convert_types({"run_id": run_id, **result, "audit_events": run["audit_events"][-50:]}))
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/validate', methods=['POST'])
def validate_endpoint():
    try:
        data = request.get_json() or {}
        run_id = (data.get("run_id") or "").strip()
        if not run_id or run_id not in RUNS:
            return jsonify({"error": "Invalid run_id."}), 400

        dataset_type = (data.get("dataset_type") or "gl").strip().lower()
        if dataset_type != "gl":
            return jsonify({"error": "Only GL validation is supported in this prototype (dataset_type='gl')."}), 400

        mapping = data.get("mapping_gl") or data.get("mapping") or {}
        normalize_account_codes = bool(data.get("normalize_account_codes", True))
        normalize_options = data.get("normalize_options") or {}
        if normalize_account_codes:
            normalize_options = {
                "upper": True if normalize_options.get("upper") is None else bool(normalize_options.get("upper")),
                "strip_non_alnum": True if normalize_options.get("strip_non_alnum") is None else bool(normalize_options.get("strip_non_alnum")),
                "drop_leading_zeros": True if normalize_options.get("drop_leading_zeros") is None else bool(normalize_options.get("drop_leading_zeros")),
            }
        else:
            normalize_options = None

        run = RUNS[run_id]
        if "gl" not in run or "dataframe" not in run["gl"]:
            return jsonify({"error": "No GL dataset ingested for this run."}), 400

        gl_df = run["gl"]["dataframe"]
        row_count = int(gl_df.shape[0])

        account_col = mapping.get("account_code") or ""
        amount_col = mapping.get("amount") or ""
        debit_col = mapping.get("debit") or ""
        credit_col = mapping.get("credit") or ""
        date_col = mapping.get("transaction_date") or mapping.get("posting_date") or ""
        desc_col = mapping.get("description") or ""

        if not account_col or account_col not in gl_df.columns:
            return jsonify({"error": "Validation requires a valid 'account_code' mapping."}), 400

        account_raw = gl_df[account_col].astype(str)
        if normalize_options:
            account_norm = account_raw.map(lambda x: _normalize_account_code(x, normalize_options))
        else:
            account_norm = account_raw.str.strip()
        invalid_account_mask = account_norm.isna() | (account_norm.astype(str).str.strip() == "") | (account_norm.astype(str).str.lower() == "nan")

        amount_series = None
        if amount_col and amount_col in gl_df.columns:
            amount_series = _coerce_numeric(gl_df[amount_col])
        elif debit_col in gl_df.columns and credit_col in gl_df.columns:
            debit_series = _coerce_numeric(gl_df[debit_col]).fillna(0.0)
            credit_series = _coerce_numeric(gl_df[credit_col]).fillna(0.0)
            amount_series = debit_series - credit_series

        invalid_amount_mask = pd.Series([True] * row_count)
        if amount_series is not None:
            invalid_amount_mask = amount_series.isna()

        date_series = None
        invalid_date_mask = pd.Series([False] * row_count)
        missing_date_mask = pd.Series([True] * row_count)
        if date_col and date_col in gl_df.columns:
            date_series = _parse_dates(gl_df[date_col])
            missing_date_mask = date_series.isna()
            original_not_null = ~gl_df[date_col].isna()
            invalid_date_mask = original_not_null & date_series.isna()

        description_series = None
        if desc_col and desc_col in gl_df.columns:
            description_series = gl_df[desc_col].astype(str).fillna("")

        double_entry = {"status": "not_available", "debits_sum": None, "credits_sum": None, "difference": None}
        if debit_col in gl_df.columns and credit_col in gl_df.columns:
            debits = _coerce_numeric(gl_df[debit_col]).fillna(0.0)
            credits = _coerce_numeric(gl_df[credit_col]).fillna(0.0)
            deb_sum = float(debits.sum())
            cred_sum = float(credits.sum())
            diff = deb_sum - cred_sum
            status = "pass" if abs(diff) <= 0.01 else "fail"
            double_entry = {"status": status, "debits_sum": deb_sum, "credits_sum": cred_sum, "difference": float(diff)}

        duplicate_count = 0
        duplicate_records = []
        if amount_series is not None and date_series is not None and description_series is not None:
            date_iso = date_series.dt.strftime("%Y-%m-%d").fillna("")
            dup_keys = []
            for i in range(row_count):
                dup_keys.append(
                    _hash_duplicate_key(
                        str(account_norm.iloc[i] if i < len(account_norm) else ""),
                        str(date_iso.iloc[i] if i < len(date_iso) else ""),
                        None if amount_series is None else amount_series.iloc[i],
                        str(description_series.iloc[i] if i < len(description_series) else ""),
                    )
                )
            key_series = pd.Series(dup_keys)
            dup_mask = key_series.duplicated(keep=False)
            duplicate_count = int(dup_mask.sum())
            if duplicate_count:
                sample_df = gl_df.loc[dup_mask].copy()
                sample_df["duplicate_hash"] = key_series.loc[dup_mask].values
                duplicate_records = sample_df.head(50).to_dict(orient="records")
        else:
            dup_mask = pd.Series([False] * row_count)

        missing_account_count = int(invalid_account_mask.sum())
        missing_amount_count = int(invalid_amount_mask.sum()) if amount_series is not None else row_count
        missing_date_count = int(missing_date_mask.sum()) if date_series is not None else row_count

        invalid_account_count = int(invalid_account_mask.sum())
        invalid_amount_count = int(invalid_amount_mask.sum()) if amount_series is not None else row_count
        invalid_date_count = int(invalid_date_mask.sum()) if date_series is not None else row_count

        issue_mask = invalid_account_mask | invalid_amount_mask | dup_mask
        if date_series is not None:
            issue_mask = issue_mask | invalid_date_mask
        issue_rows = int(issue_mask.sum())
        score = 100.0
        if row_count > 0:
            score = max(0.0, 100.0 * (1.0 - (issue_rows / row_count)))
        if double_entry["status"] == "fail":
            score = max(0.0, score - 10.0)

        report = {
            "validation_score_pct": score,
            "row_count": row_count,
            "double_entry": double_entry,
            "duplicate_count": duplicate_count,
            "missing_values": {
                "missing_account_codes": missing_account_count,
                "missing_dates": missing_date_count,
                "missing_amounts": missing_amount_count,
            },
            "invalid_records": {
                "invalid_account_codes": invalid_account_count,
                "invalid_dates": invalid_date_count,
                "invalid_amounts": invalid_amount_count,
            },
        }

        run["validation"] = {"completed_at": _now_iso(), "report": report, "duplicate_records": duplicate_records}
        _append_audit_event(run_id, "STANDARDISATION_COMPLETED", "Data Standardisation", {"normalize_account_codes": bool(normalize_options is not None)})
        _append_audit_event(run_id, "VALIDATION_COMPLETED", "Data Quality Validation", report)

        return jsonify(convert_types({"run_id": run_id, "report": report, "duplicate_records": duplicate_records, "audit_events": run["audit_events"][-50:]}))
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/quality', methods=['POST'])
def quality_endpoint():
    try:
        data = request.get_json() or {}
        run_id = (data.get("run_id") or "").strip()
        dataset_type = (data.get("dataset_type") or "").strip().lower()
        mapping = data.get("mapping") or {}

        if not run_id or run_id not in RUNS:
            return jsonify({"error": "Invalid run_id."}), 400
        if dataset_type not in {"gl", "tb"}:
            return jsonify({"error": "dataset_type must be 'gl' or 'tb'."}), 400
        run = RUNS[run_id]
        if dataset_type not in run or "dataframe" not in run[dataset_type]:
            return jsonify({"error": f"No {dataset_type} dataset ingested for this run."}), 400

        df = run[dataset_type]["dataframe"]
        cols = set(df.columns.tolist())

        if dataset_type == "gl":
            required = ["account_code"]
            amount_ok = False
            if mapping.get("amount") and mapping.get("amount") in cols:
                amount_ok = True
            if mapping.get("debit") in cols and mapping.get("credit") in cols:
                amount_ok = True
            missing_required = [k for k in required if not mapping.get(k) or mapping.get(k) not in cols]
            errors = []
            if not amount_ok:
                errors.append("Provide GL 'amount' OR both 'debit' and 'credit'.")
        else:
            required = ["account_code", "balance"]
            missing_required = [k for k in required if not mapping.get(k) or mapping.get(k) not in cols]
            errors = []

        missingness = df.isna().mean().to_dict()
        dup_count = int(df.duplicated().sum())

        _append_audit_event(run_id, "STANDARDISATION_COMPLETED", "Data Standardisation", {"dataset_type": dataset_type})
        return jsonify(convert_types({
            "run_id": run_id,
            "dataset_type": dataset_type,
            "missing_required_mapped_columns": missing_required,
            "errors": errors,
            "row_count": int(df.shape[0]),
            "duplicate_row_count": dup_count,
            "missingness_by_column": missingness,
            "audit_events": run["audit_events"][-50:],
        }))
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/reconcile', methods=['POST'])
def reconcile_endpoint():
    try:
        data = request.get_json() or {}
        run_id = (data.get("run_id") or "").strip()
        if not run_id or run_id not in RUNS:
            return jsonify({"error": "Invalid run_id."}), 400
        mapping_gl = data.get("mapping_gl") or {}
        mapping_tb = data.get("mapping_tb") or {}
        tolerance = float(data.get("tolerance") if data.get("tolerance") is not None else 0.01)
        normalize_account_codes = bool(data.get("normalize_account_codes", True))
        normalize_options = data.get("normalize_options") or {}
        if normalize_account_codes:
            normalize_options = {
                "upper": True if normalize_options.get("upper") is None else bool(normalize_options.get("upper")),
                "strip_non_alnum": True if normalize_options.get("strip_non_alnum") is None else bool(normalize_options.get("strip_non_alnum")),
                "drop_leading_zeros": True if normalize_options.get("drop_leading_zeros") is None else bool(normalize_options.get("drop_leading_zeros")),
            }
        else:
            normalize_options = None

        run = RUNS[run_id]
        if "gl" not in run or "tb" not in run:
            return jsonify({"error": "Both GL and TB must be ingested before reconciliation."}), 400

        gl_df = run["gl"]["dataframe"]
        tb_df = run["tb"]["dataframe"]

        gl_std = _standardize_gl(gl_df, mapping_gl, normalize_options=normalize_options)
        tb_std = _standardize_tb(tb_df, mapping_tb, normalize_options=normalize_options)

        gl_totals = gl_std.groupby("AccountCode", as_index=False)["Amount"].sum().rename(columns={"Amount": "GLTotal"})
        tb_totals = tb_std.groupby("AccountCode", as_index=False)["Balance"].sum().rename(columns={"Balance": "TBTotal"})

        merged = gl_totals.merge(tb_totals, on="AccountCode", how="outer")
        merged["GLTotal"] = merged["GLTotal"].fillna(0.0)
        merged["TBTotal"] = merged["TBTotal"].fillna(0.0)
        merged["Difference"] = merged["GLTotal"] - merged["TBTotal"]
        merged["InGL"] = merged["AccountCode"].isin(gl_totals["AccountCode"])
        merged["InTB"] = merged["AccountCode"].isin(tb_totals["AccountCode"])
        merged["VariancePct"] = merged.apply(
            lambda r: (r["Difference"] / r["TBTotal"]) if r["TBTotal"] not in (0, 0.0) else None,
            axis=1
        )
        merged["OutOfTolerance"] = merged["Difference"].abs() > tolerance
        merged["Severity"] = merged.apply(
            lambda r: (
                "high"
                if (not r["InGL"] or not r["InTB"])
                else (
                    "high"
                    if (r["VariancePct"] is not None and abs(r["VariancePct"]) >= 0.05)
                    else (
                        "medium"
                        if (r["VariancePct"] is not None and abs(r["VariancePct"]) >= 0.01)
                        else "low"
                    )
                )
            ),
            axis=1
        )

        exceptions = merged[merged["OutOfTolerance"]].copy()
        exceptions = exceptions.sort_values(by="Difference", key=lambda s: s.abs(), ascending=False)

        in_both = merged[merged["InGL"] & merged["InTB"]]
        matched_in_both = in_both[~in_both["OutOfTolerance"]]
        reconciliation_pct = (len(matched_in_both) / len(in_both)) if len(in_both) else None

        summary = {
            "tolerance": tolerance,
            "normalize_account_codes": bool(normalize_options is not None),
            "normalize_options": normalize_options or {},
            "gl_account_count": int(gl_totals.shape[0]),
            "tb_account_count": int(tb_totals.shape[0]),
            "accounts_in_both": int(len(in_both)),
            "matched_accounts_in_both": int(len(matched_in_both)),
            "reconciliation_percentage_in_both": reconciliation_pct,
            "exceptions_count": int(exceptions.shape[0]),
            "gl_total_sum": float(gl_totals["GLTotal"].sum()),
            "tb_total_sum": float(tb_totals["TBTotal"].sum()),
            "abs_difference_sum": float(merged["Difference"].abs().sum()),
        }

        result = {
            "run_id": run_id,
            "summary": summary,
            "exceptions": exceptions.head(500).to_dict(orient="records"),
            "reconciliation_table_sample": merged.head(50).to_dict(orient="records"),
        }

        run["reconciliation"] = {"completed_at": _now_iso(), "summary": summary}
        run["reconciliation_tables"] = {
            "merged": merged,
            "exceptions": exceptions,
        }
        _append_audit_event(run_id, "STANDARDISATION_COMPLETED", "Data Standardisation", {"normalize_account_codes": bool(normalize_options is not None), "normalize_options": normalize_options or {}})
        _append_audit_event(run_id, "RECONCILIATION_COMPLETED", "Deterministic Reconciliation Engine", summary)
        if int(exceptions.shape[0]) > 0:
            _append_audit_event(
                run_id,
                "VARIANCE_DETECTED",
                "Deterministic Reconciliation Engine",
                {"exceptions_count": int(exceptions.shape[0]), "tolerance": tolerance},
            )

        return jsonify(convert_types({**result, "audit_events": run["audit_events"][-50:]}))
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/reconcile/export', methods=['GET'])
def reconcile_export_endpoint():
    try:
        run_id = (request.args.get("run_id") or "").strip()
        if not run_id or run_id not in RUNS:
            return jsonify({"error": "Invalid run_id."}), 400
        run = RUNS[run_id]
        tables = run.get("reconciliation_tables") or {}
        if "exceptions" not in tables or "merged" not in tables:
            return jsonify({"error": "No reconciliation results found for this run. Run /api/reconcile first."}), 400

        dataset = (request.args.get("dataset") or "exceptions").strip().lower()
        if dataset not in {"exceptions", "merged"}:
            return jsonify({"error": "dataset must be 'exceptions' or 'merged'."}), 400

        df = tables[dataset]
        csv_text = df.to_csv(index=False)
        filename = f"{run_id}_{dataset}.csv"
        headers = {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        return Response(csv_text, headers=headers)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/audit', methods=['GET'])
def audit_events_endpoint():
    try:
        run_id = (request.args.get("run_id") or "").strip()
        if not run_id or run_id not in RUNS:
            return jsonify({"error": "Invalid run_id."}), 400
        run = RUNS[run_id]
        events = run.get("audit_events") or []
        return jsonify(convert_types({"run_id": run_id, "events": events}))
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/audit/export', methods=['GET'])
def audit_events_export_endpoint():
    try:
        run_id = (request.args.get("run_id") or "").strip()
        if not run_id or run_id not in RUNS:
            return jsonify({"error": "Invalid run_id."}), 400
        run = RUNS[run_id]
        payload = {"run_id": run_id, "events": run.get("audit_events") or []}
        json_text = json.dumps(convert_types(payload), indent=2)
        filename = f"{run_id}_audit_events.json"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        return Response(json_text, headers=headers)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/pdf/upload', methods=['POST'])
def pdf_upload_endpoint():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        run_id = (request.form.get("run_id") or "").strip()
        if not run_id:
            return jsonify({'error': 'Missing run_id'}), 400
        run = _ensure_run(run_id)

        file = request.files['file']
        if file.filename == '' or not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Invalid file (PDF only)'}), 400

        pdf_bytes, checksum = _read_pdf_bytes_from_filestorage(file)
        pdf_id = str(uuid.uuid4())
        record = {
            "pdf_id": pdf_id,
            "filename": file.filename,
            "checksum_sha256": checksum,
            "uploaded_at": _now_iso(),
            "size_bytes": int(len(pdf_bytes)),
            "raw_base64": base64.b64encode(pdf_bytes).decode("utf-8"),
            "extracted_text": None,
            "analysis": None,
        }
        pdfs = run.get("pdfs") or []
        pdfs.append(record)
        run["pdfs"] = pdfs

        _append_audit_event(
            run_id,
            "UPLOAD_RECEIVED",
            "PDF Ingestion",
            {"pdf_id": pdf_id, "filename": file.filename, "checksum_sha256": checksum, "size_bytes": int(len(pdf_bytes))},
        )

        return jsonify(convert_types({"run_id": run_id, "pdf_id": pdf_id}))
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    from PyPDF2 import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if t:
            parts.append(t)
    return "\n\n".join(parts).strip()

@app.route('/api/pdf/analyze', methods=['POST'])
def pdf_analyze_endpoint():
    try:
        data = request.get_json() or {}
        run_id = (data.get("run_id") or "").strip()
        pdf_id = (data.get("pdf_id") or "").strip()
        if not run_id or run_id not in RUNS:
            return jsonify({"error": "Invalid run_id."}), 400
        if not pdf_id:
            return jsonify({"error": "Missing pdf_id."}), 400

        run = _ensure_run(run_id)
        pdfs = run.get("pdfs") or []
        rec = next((p for p in pdfs if p.get("pdf_id") == pdf_id), None)
        if not rec:
            return jsonify({"error": "Unknown pdf_id for this run."}), 400

        pdf_bytes = base64.b64decode(rec.get("raw_base64") or "")
        extracted = rec.get("extracted_text")
        if extracted is None:
            extracted = _extract_text_from_pdf_bytes(pdf_bytes)
            rec["extracted_text"] = extracted
            _append_audit_event(
                run_id,
                "STANDARDISATION_COMPLETED",
                "PDF Text Extraction",
                {"pdf_id": pdf_id, "extracted_text_length": int(len(extracted or ""))},
            )

        exceptions = []
        tables = run.get("reconciliation_tables") or {}
        if "exceptions" in tables:
            try:
                exceptions = tables["exceptions"].head(50).to_dict(orient="records")
            except Exception:
                exceptions = []

        prompt = (
            "You are assisting an audit team. Extract structured information from the PDF text. "
            "Do not compute or alter any financial figures. Only extract and summarize.\n\n"
            "Return STRICT JSON with keys:\n"
            "{\n"
            '  "journalReference": string|null,\n'
            '  "preparedBy": string|null,\n'
            '  "approvedBy": string|null,\n'
            '  "possibleIssues": string[] ,\n'
            '  "summary": string\n'
            "}\n\n"
            f"PDF_TEXT:\n{extracted[:20000]}\n\n"
            f"KNOWN_VARIANCES (account-level exceptions):\n{json.dumps(exceptions)[:20000]}\n"
        )

        _require_openai_api_key()
        messages = [
            {"role": "system", "content": "You extract audit evidence from documents and respond in strict JSON."},
            {"role": "user", "content": prompt},
        ]
        response_obj = openai.ChatCompletion.create(model="gpt-4o", messages=messages)
        content = response_obj.choices[0].message["content"]

        result = None
        try:
            result = json.loads(content)
        except Exception:
            result = {
                "journalReference": None,
                "preparedBy": None,
                "approvedBy": None,
                "possibleIssues": [],
                "summary": content,
            }

        links = []
        if "exceptions" in tables:
            try:
                exc_df = tables["exceptions"]
                text_upper = (extracted or "").upper()
                for _, row in exc_df.iterrows():
                    acct = str(row.get("AccountCode", "")).upper()
                    if acct and acct in text_upper:
                        links.append({"AccountCode": acct})
            except Exception:
                links = []

        analysis_record = {
            "pdf_id": pdf_id,
            "filename": rec.get("filename"),
            "checksum_sha256": rec.get("checksum_sha256"),
            "extracted_text_length": int(len(extracted or "")),
            "result": result,
            "linked_variances": links,
        }
        rec["analysis"] = analysis_record
        run["pdfs"] = pdfs

        _append_audit_event(
            run_id,
            "AI_ANALYSIS_COMPLETED",
            "PDF Analysis",
            {"pdf_id": pdf_id, "linked_variances_count": int(len(links))},
        )

        return jsonify(convert_types({"run_id": run_id, "pdf_id": pdf_id, "result": analysis_record}))
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# -----------------------------------------------------------------------------
# Train Endpoint
# -----------------------------------------------------------------------------
@app.route('/api/train', methods=['POST'])
def train_endpoint():
    """
    Uses the ORIGINAL raw data (unmodified) stored in app.config['RAW_DATA'].
    Trains a regression model on the target column without binarization.
    Missing values in the features are imputed using a mean strategy,
    while rows with missing target values are dropped.
    Columns that are completely missing are dropped from training.
    """
    try:
        if 'RAW_DATA' not in app.config:
            return jsonify({"error": "No raw data found. Please run /api/preprocess first."}), 400

        df_raw = pd.DataFrame(app.config['RAW_DATA'])
        target_column = request.json.get('target_column', '')
        if target_column == '' or target_column not in df_raw.columns:
            raise ValueError(f"Invalid target column. Available columns: {df_raw.columns.tolist()}")

        # Separate features and target.
        X = df_raw.drop(columns=[target_column]).copy()
        y = df_raw[target_column].copy()

        # Convert all feature columns to numeric.
        for col in X.columns:
            X[col] = pd.to_numeric(X[col], errors='coerce')
        # Select only numeric columns.
        X_numeric = X.select_dtypes(include=[np.number])
        print("Original X shape:", X.shape)
        print("Numeric X shape before dropping all-NaN columns:", X_numeric.shape)
        
        # Drop columns with all missing values.
        X_numeric = X_numeric.dropna(axis=1, how='all')
        features = list(X_numeric.columns)
        print("Numeric X shape after dropping all-NaN columns:", X_numeric.shape)

        # Convert target to numeric.
        y = pd.to_numeric(y, errors='coerce')

        # Impute missing values in numeric features using mean imputation.
        from sklearn.impute import SimpleImputer
        imputer = SimpleImputer(strategy='mean')
        X_imputed = imputer.fit_transform(X_numeric)
        # Construct DataFrame using the columns from X_numeric.
        X = pd.DataFrame(X_imputed, columns=features)
        print("Imputed X shape:", X.shape)

        # For the target, drop rows with missing values.
        valid_idx = ~y.isna()
        X = X.loc[valid_idx].reset_index(drop=True)
        y = y.loc[valid_idx].reset_index(drop=True)

        print("Final training X shape:", X.shape)
        print("Target shape:", y.shape)
        print("Feature columns for training:", features)
        print("Target column:", target_column)

        # Assume target is continuous.
        use_regression = True

        # Scale the target for training and save the target scaler.
        from sklearn.preprocessing import StandardScaler
        target_scaler = StandardScaler()
        y_scaled = target_scaler.fit_transform(y.values.reshape(-1, 1)).flatten()
        with open(TARGET_SCALER_PATH, 'wb') as f_tscaler:
            pickle.dump(target_scaler, f_tscaler)

        # Scale features.
        feature_scaler = StandardScaler()
        X_scaled = feature_scaler.fit_transform(X)
        with open(FEATURE_SCALER_PATH, 'wb') as f_scaler:
            pickle.dump(feature_scaler, f_scaler)

        if X.shape[1] == 0:
            raise ValueError("No numeric features remain for training.")
        if len(X) < 2:
            raise ValueError("Not enough data for train/test split.")

        from sklearn.model_selection import train_test_split
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y_scaled, test_size=0.3, random_state=42
        )

        # Train regression models.
        from sklearn.linear_model import LinearRegression
        from sklearn.tree import DecisionTreeRegressor
        from sklearn.ensemble import RandomForestRegressor
        from xgboost import XGBRegressor
        models = {
            "LinearRegression": LinearRegression(),
            "DecisionTreeRegressor": DecisionTreeRegressor(),
            "RandomForestRegressor": RandomForestRegressor(n_estimators=100),
            "XGBRegressor": XGBRegressor(objective='reg:squarederror', n_estimators=100)
        }

        best_model = None
        best_score = -np.inf
        best_model_name = None
        model_scores = {}
        for name, model in models.items():
            model.fit(X_train, y_train)
            preds = model.predict(X_test)
            score = r2_score(y_test, preds)
            model_scores[name] = score
            if score > best_score:
                best_score = score
                best_model = model
                best_model_name = name

        if best_model is None:
            raise ValueError("No model could be trained successfully.")

        # Save best model with metadata.
        best_model_data = {
            'model': best_model,
            'features': features,
            'target': target_column,
            'use_regression': use_regression,
            'model_name': best_model_name,
            'best_score': best_score
        }

        with open(TARGET_SCALER_PATH, 'rb') as f_tscaler:
            target_scaler = pickle.load(f_tscaler)
        best_model_data['target_scaler'] = {
            'mean': target_scaler.mean_.tolist(),
            'scale': target_scaler.scale_.tolist()
        }

        with open(MODEL_PATH, 'wb') as f_model:
            pickle.dump(best_model_data, f_model)

        app.config['BEST_MODEL'] = best_model
        app.config['FEATURES'] = features
        app.config['TRAINED_DATA'] = df_raw.to_dict(orient='records')

        response = {
            'model_scores': model_scores,
            'best_model': best_model_name,
            'best_score': best_score,
            'use_regression': use_regression
        }
        print("Training completed. Best model:", best_model_name, "with score:", best_score)
        return jsonify(convert_types(response))
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# -----------------------------------------------------------------------------
# Predict Endpoint - Recommender Engine Style
# -----------------------------------------------------------------------------
@app.route('/api/predict', methods=['POST'])
def predict_endpoint():
    try:
        if not os.path.exists(MODEL_PATH):
            return jsonify({"error": "No trained model found. Train a model first."}), 400

        # Load best model and metadata.
        with open(MODEL_PATH, 'rb') as f_model:
            best_model_data = pickle.load(f_model)
        best_model = best_model_data['model']
        features = best_model_data['features']
        target_column = best_model_data.get('target', None)
        use_regression = best_model_data.get('use_regression', False)
        target_scaler_params = best_model_data.get('target_scaler', None)
        
        # Get the input data.
        req_data = request.get_json() or {}
        new_data = req_data.get('data', [])
        if not isinstance(new_data, list):
            return jsonify({"error": "Please provide a 'data' key with an array of records."}), 400

        df_input = pd.DataFrame(new_data)
        # Keep only the features used for training.
        df_input = df_input[features]
        for col in df_input.columns:
            df_input[col] = pd.to_numeric(df_input[col], errors='coerce')
        df_input = df_input.select_dtypes(include=[np.number])

        # Scale the input data.
        with open(FEATURE_SCALER_PATH, 'rb') as f_scaler:
            feature_scaler = pickle.load(f_scaler)
        df_input_scaled = feature_scaler.transform(df_input)

        # Get predictions.
        predictions_scaled = best_model.predict(df_input_scaled)
        recommendations = []
        for i, pred in enumerate(predictions_scaled):
            if use_regression and target_scaler_params:
                s = target_scaler_params['scale'][0]
                m = target_scaler_params['mean'][0]
                pred_original = (float(pred) * s) + m
                pred_value = float(pred_original)
            else:
                pred_value = float(pred) if use_regression else int(pred) if pd.notnull(pred) else None
            message = f"Sample {i}: The predicted {target_column} is {pred_value:.2f}"
            recommendations.append({
                "Sample": i,
                "PredictedTarget": pred_value,
                "Recommendation": message
            })

        # Retrieve the correlation matrix.
        if 'TRAINED_DATA' in app.config:
            df_train = pd.DataFrame(app.config['TRAINED_DATA'])
            numeric_features = [col for col in features if pd.api.types.is_numeric_dtype(df_train[col])]
            corr = df_train[numeric_features].corr().to_dict()
        else:
            corr = {}

        # SHAP Analysis: Compute SHAP values for the first sample.
        try:
            if best_model_data.get('model_name', '').lower().find('tree') != -1 or \
               best_model_data.get('model_name', '').lower().find('xgb') != -1:
                explainer = shap.TreeExplainer(best_model)
            else:
                background = df_input_scaled[:min(10, len(df_input_scaled))]
                explainer = shap.KernelExplainer(best_model.predict, background)
            shap_values = explainer(df_input_scaled)
            shap_summary = dict(zip(features, shap_values.values[0].tolist()))
        except Exception as e:
            shap_summary = {"error": f"SHAP analysis failed: {str(e)}"}

        # Load model metadata.
        model_metadata = {
            "model_name": best_model_data.get('model_name'),
            "best_score": best_model_data.get('best_score'),
            "features": features,
            "target_column": target_column
        }

        # Compose the prompt for the LLM.
        prompt = (
            f"Customer Data: {json.dumps(req_data)}\n\n"
            f"Prediction: {recommendations[0]['Recommendation']}\n\n"
            f"Model Metadata: {json.dumps(model_metadata)}\n\n"
            f"Correlation Matrix: {json.dumps(corr)}\n\n"
            f"SHAP Analysis (feature contributions): {json.dumps(shap_summary)}\n\n"
            "Based on these details, provide a detailed, customer-specific business insight that focuses on what can be improved for this customer. "
            "Explain the strategic implications, actionable recommendations, potential opportunities, and risks in a way that directly relates to the provided data. "
            "Ensure that your insights are customized to this customer's profile and context, highlighting key areas for improvement, targeted business strategies, and unique challenges. "
            "Avoid any technical details or jargon."
        )

        # Call the LLM API to get business insights.
        messages = [
            {"role": "system", "content": "You are an expert data analyst and business strategist."},
            {"role": "user", "content": prompt}
        ]
        _require_openai_api_key()
        llm_response_obj = openai.ChatCompletion.create(model="gpt-4o", messages=messages)
        llm_insight = llm_response_obj.choices[0].message["content"]
        token_usage = llm_response_obj.get("usage", {})
        print("LLM token usage for /api/predict:", token_usage)  # Print token usage to terminal

        # Build the final response.
        response = {
            "target_column": target_column,
            "predictions": recommendations,
            "model_info": f"{model_metadata.get('model_name', 'Unknown')} => Score: {model_metadata.get('best_score', 'N/A'):.2f}",
            "llm_insight": llm_insight,
            "token_usage": token_usage
        }
        return jsonify(convert_types(response))
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# -----------------------------------------------------------------------------
# LLM Chat Endpoint
# -----------------------------------------------------------------------------
@app.route('/api/llm', methods=['POST'])
def llm_endpoint():
    try:
        data = request.json
        prompt = data.get("prompt", "")
        chat_history = data.get("chat_history", [])
        processed_summary = data.get("processed_summary", "")
        run_id = (data.get("run_id") or "").strip()
        
        messages = [{
            "role": "system",
            "content": (
                "You are an expert data analyst and business strategist with deep knowledge in data engineering, analysis, "
                "and business strategy. Provide detailed insights, predictive analysis, and actionable recommendations on the current dataset only and do not assume if the column data is not there. "
                "When asked about scenarios or 'what-if' questions, clearly explain potential outcomes, risks, and opportunities. "
                "Focus on how the data can drive business improvements and suggest next steps to enhance the business case. "
                "When you are pulling out insights, make sure you showcase a table of 2-3 records from the dataset which supports your insights, actions, and everything. Make sure you show all the fields in that record and only from that dataset"
            )
        }]
        
        if processed_summary:
            messages.append({"role": "assistant", "content": processed_summary})
        if chat_history:
            messages.extend(chat_history)
        messages.append({"role": "user", "content": prompt})
        
        _require_openai_api_key()
        response_obj = openai.ChatCompletion.create(model="gpt-4o", messages=messages)
        llm_response = response_obj.choices[0].message["content"]
        token_usage = response_obj.get("usage", {})
        print("LLM token usage for /api/llm:", token_usage)  # Print token usage to terminal
        if run_id and run_id in RUNS:
            run = _ensure_run(run_id)
            analysis_id = str(uuid.uuid4())
            analyses = run.get("ai_analyses") or []
            analyses.append({
                "id": analysis_id,
                "timestamp": _now_iso(),
                "prompt": prompt,
                "response": llm_response,
                "token_usage": token_usage,
            })
            run["ai_analyses"] = analyses
            _append_audit_event(
                run_id,
                "AI_ANALYSIS_COMPLETED",
                "AI Exception Analysis",
                {"analysis_id": analysis_id, "token_usage": token_usage},
            )
        return jsonify({"response": llm_response, "token_usage": token_usage})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=8080)
