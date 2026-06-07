from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd, numpy as np
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.decomposition import PCA
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import GaussianNB
from sklearn.tree import DecisionTreeClassifier
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score
import traceback, os, io, json, base64, math
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
import openai

app = Flask(__name__)
CORS(app)

def _require_openai_api_key():
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("Missing OPENAI_API_KEY environment variable.")
    openai.api_key = key

# Utility: Recursively convert numpy/pandas types to native Python types.
def convert_types(obj):
    if isinstance(obj, dict):
        return {k: convert_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_types(item) for item in obj]
    elif isinstance(obj, (np.float32, np.float64)):
        if np.isnan(obj):
            return None
        return float(obj)
    elif isinstance(obj, float):
        if math.isnan(obj):
            return None
        return obj
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
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if file.filename == '' or not file.filename.endswith('.csv'):
            return jsonify({'error': 'Invalid file'}), 400

        # Save file temporarily
        import tempfile
        from werkzeug.utils import secure_filename
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, secure_filename(file.filename))
        file.save(temp_path)
        df = pd.read_csv(temp_path)
        os.remove(temp_path)
        os.rmdir(temp_dir)

        # Parse options and manual column types
        options = json.loads(request.form.get('options', '{}'))
        columnTypes = json.loads(request.form.get('columnTypes', '{}'))
        do_format_date   = options.get("formatDates", True)
        do_drop_empty    = options.get("dropEmpty", True)
        do_drop_missing  = options.get("dropMissing", True)
        do_fill_missing  = options.get("fillMissing", False)
        do_scale         = options.get("scaleNumeric", True)
        do_encode        = options.get("encodeCategorical", True)
        do_pca           = options.get("performPCA", False)
        do_corr          = options.get("showCorrelation", False)

        # Build column categories – if manual types are set then use them,
        # otherwise auto-detect types.
        columns_to_process = {"numeric": [], "categorical": [], "date": [], "excluded": []}
        if columnTypes and any(val.strip() for val in columnTypes.values()):
            for col, col_type in columnTypes.items():
                if col_type == "numeric":
                    columns_to_process["numeric"].append(col)
                elif col_type == "categorical":
                    columns_to_process["categorical"].append(col)
                elif col_type == "date":
                    columns_to_process["date"].append(col)
                elif col_type == "exclude":
                    columns_to_process["excluded"].append(col)
        else:
            excluded_keywords = ['id', 'number', 'code', 'identifier']
            for col in df.columns:
                col_lower = col.lower()
                if df[col].dtype in ['int64', 'float64']:
                    if any(kw in col_lower for kw in excluded_keywords):
                        columns_to_process["excluded"].append(col)
                    else:
                        columns_to_process["numeric"].append(col)
                elif df[col].dtype == 'object':
                    try:
                        pd.to_datetime(df[col].dropna().head())
                        columns_to_process["date"].append(col)
                    except Exception:
                        if any(kw in col_lower for kw in excluded_keywords):
                            columns_to_process["excluded"].append(col)
                        else:
                            columns_to_process["categorical"].append(col)
                else:
                    columns_to_process["excluded"].append(col)

        if columns_to_process["excluded"]:
            df = df.drop(columns=columns_to_process["excluded"], errors='ignore')

        if do_format_date and columns_to_process["date"]:
            for col in columns_to_process["date"]:
                try:
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%d/%m/%Y')
                except:
                    pass

        if do_drop_empty:
            df = df.dropna(axis=1, how='all')
        if do_drop_missing:
            df = df.dropna()
        if do_fill_missing:
            for col in df.columns:
                if col in columns_to_process["numeric"]:
                    df[col].fillna(df[col].mean(), inplace=True)
                elif col in columns_to_process["categorical"]:
                    df[col].fillna(df[col].mode()[0], inplace=True)
        if do_scale and columns_to_process["numeric"]:
            scaler = StandardScaler()
            df[columns_to_process["numeric"]] = scaler.fit_transform(df[columns_to_process["numeric"]])
        encoders = {}
        if do_encode and columns_to_process["categorical"]:
            for col in columns_to_process["categorical"]:
                le = LabelEncoder()
                df[col] = le.fit_transform(df[col].astype(str))
                encoders[col] = list(le.classes_)
        pca_result = {}
        if do_pca and columns_to_process["numeric"]:
            try:
                numeric_data = df[columns_to_process["numeric"]]
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

                loadings = pd.DataFrame(pca.components_, 
                                        columns=columns_to_process["numeric"],
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
        if do_corr and columns_to_process["numeric"]:
            # Ensure that numeric data is truly numeric and replace NaN with None.
            numeric_df = df[columns_to_process["numeric"]].apply(pd.to_numeric, errors='coerce')
            corr = numeric_df.corr()
            corr = corr.where(pd.notnull(corr), None)
            corr_matrix = corr.to_dict()

        # Always compute the detected types based on auto-detection logic.
        detected_column_types = {}
        if columnTypes and any(val.strip() for val in columnTypes.values()):
            # If manual types are provided, use them as the "detected" ones.
            detected_column_types = columnTypes
        else:
            for col in df.columns:
                if col in columns_to_process["numeric"]:
                    detected_column_types[col] = "numeric"
                elif col in columns_to_process["categorical"]:
                    detected_column_types[col] = "categorical"
                elif col in columns_to_process["date"]:
                    detected_column_types[col] = "date"
                else:
                    detected_column_types[col] = "exclude"

        response = {
            'columns': columns_to_process,
            'detected_column_types': detected_column_types,
            'data': df.to_dict(orient='records'),
            'summary': {
                'shape': df.shape,
                'columns': df.columns.tolist()
            },
            'pca_result': pca_result,
            'correlation_matrix': corr_matrix,
            'encoders': encoders
        }
        return jsonify(convert_types(response))
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# -----------------------------------------------------------------------------  
# Train Endpoint  
# -----------------------------------------------------------------------------
@app.route('/api/train', methods=['POST'])
def train_endpoint():
    try:
        data = request.json
        print("Training endpoint received keys:", list(data.keys()))
        df = pd.DataFrame(data.get('data', []))
        target_column = data.get('target_column', '')
        print("DataFrame columns:", df.columns.tolist())
        print("Selected target column:", target_column)
        
        if df.empty:
            raise ValueError("No data provided.")
        if target_column == '' or target_column not in df.columns:
            raise ValueError(f"Invalid target column. Available columns: {df.columns.tolist()}")
        
        # Remove the target column from features.
        X = df.drop(columns=[target_column])
        # Force conversion: Convert all non-target columns to numeric if possible.
        for col in X.columns:
            X[col] = pd.to_numeric(X[col], errors='coerce')
        X = X.select_dtypes(include=[np.number])
        y = df[target_column]
        # Try converting target to numeric as well (in case it's coming as string)
        y = pd.to_numeric(y, errors='coerce')
        
        print("Initial features (numeric) after drop:", X.columns.tolist())
        
        # Check if target seems continuous. For instance, if there are more than a few unique values.
        if y.nunique() > 10:
            print("Target appears continuous. Binarizing using the median...")
            median_val = y.median()
            y = (y > median_val).astype(int)
            print("Converted target to binary. Unique values now:", y.unique())
        
        if X.shape[1] == 0:
            raise ValueError("After processing, no numeric features remain. Please ensure your dataset contains at least one numeric feature besides the target.")
        if len(df) < 2:
            raise ValueError("Not enough data for train/test split.")
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
        
        models = {
            "LogisticRegression": LogisticRegression(max_iter=1000),
            "GaussianNB": GaussianNB(),
            "DecisionTree": DecisionTreeClassifier(),
            "XGBoost": XGBClassifier(use_label_encoder=False, eval_metric='logloss')
        }
        best_model = None
        best_score = -1
        model_scores = {}
        best_model_name = None
        
        for name, model in models.items():
            try:
                model.fit(X_train, y_train)
                preds = model.predict(X_test)
                score = accuracy_score(y_test, preds)
                model_scores[name] = score
                if score > best_score:
                    best_score = score
                    best_model = model
                    best_model_name = name
            except Exception as e:
                print(f"Model {name} failed with error: {e}")
                model_scores[name] = str(e)
        
        if not best_model:
            raise ValueError("No model could be trained successfully. Check if the dataset has enough data and valid numeric features.")
        
        # Save the best model and training data for later use
        app.config['BEST_MODEL'] = best_model
        app.config['FEATURES'] = X.columns.tolist()
        app.config['TRAINED_DATA'] = df.to_dict(orient='records')
        response = {
            'model_scores': model_scores,
            'best_model': best_model_name,
            'best_score': best_score
        }
        print("Training completed. Best model:", best_model_name, "with score:", best_score)
        return jsonify(convert_types(response))
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# -----------------------------------------------------------------------------  
# Action Recommender Endpoint  
# -----------------------------------------------------------------------------
@app.route('/api/action-recommend', methods=['POST'])
def action_recommend_endpoint():
    try:
        best_model = app.config.get('BEST_MODEL', None)
        features = app.config.get('FEATURES', [])
        if best_model is None or not features:
            return jsonify({"error": "No trained model available. Please train a model first."}), 400
        data = pd.DataFrame(app.config.get('TRAINED_DATA', []))
        X = data[features]
        if hasattr(best_model, "predict_proba"):
            probabilities = best_model.predict_proba(X)
            threshold = 0.6
            recommendations = []
            for i, prob in enumerate(probabilities):
                high_prob = prob[1] if len(prob) > 1 else prob[0]
                rec = f"Sample {i}: High risk detected. Recommended action: Investigate further." if high_prob >= threshold else f"Sample {i}: Low risk. No immediate action required."
                recommendations.append({
                    "Sample": i,
                    "High Risk Probability": high_prob,
                    "Recommendation": rec
                })
        else:
            recommendations = [{"error": "Model does not support probability predictions."}]
        return jsonify(convert_types({"recommendations": recommendations}))
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
        chat_history = data.get("chat_history", [])  # Retrieve previous chat messages
        processed_summary = data.get("processed_summary", "")
        
        # Start with a system prompt that sets the context for the LLM.
        messages = [{
            "role": "system",
            "content": (
                "You are an expert data analyst and business strategist with deep knowledge in data engineering, analysis, "
                "and business strategy. Provide detailed insights, predictive analysis, and actionable recommendations on the current dataset only and do not assume if the column data is not there. "
                "When asked about scenarios or 'what-if' questions, clearly explain potential outcomes, risks, and opportunities. "
                "Focus on how the data can drive business improvements and suggest next steps to enhance the business case. "
                "When you are pulling out insights, make sure you showcase a table of 2-3 records from the dataset which supports your insights, actions, and everything. Make sure you show all the fields in that record."
            )
        }]
        
        # Optionally include a processed summary as additional context.
        if processed_summary:
            messages.append({"role": "assistant", "content": processed_summary})
        
        # Add chat history as additional context if it exists.
        if chat_history:
            messages.extend(chat_history)
        
        # Finally, add the latest user prompt.
        messages.append({"role": "user", "content": prompt})
        
        _require_openai_api_key()
        response = openai.ChatCompletion.create(model="gpt-4o", messages=messages)
        llm_response = response.choices[0].message["content"]
        return jsonify({"response": llm_response})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
