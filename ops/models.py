import pandas as pd

from sklearn.model_selection import train_test_split

from sklearn.linear_model import LogisticRegression

from sklearn.metrics import roc_auc_score, classification_report

def train_tech_training_model(path_csv="data/train_tech_training.csv", use_raw_history=True):

    # Option 1: Train on raw historical tickets (more data points)
    if use_raw_history:
        hist_path = "data/history_tickets.csv"
        try:
            hist_df = pd.read_csv(hist_path)
            if not hist_df.empty:
                # Create features from individual tickets
                # Label: needs_training if ticket had rework OR overran significantly
                hist_df["needs_training"] = ((hist_df["reticketed"] == 1) | (hist_df["overran"] == 1)).astype(int)
                
                # Convert priority to numeric
                hist_df["priority_num"] = hist_df["priority"].map({"Low":1,"Medium":2,"High":3,"Critical":4}).fillna(2)
                
                # Extract first tag as feature (or create tag-based features)
                hist_df["first_tag"] = hist_df["tags"].str.split("|").str[0].fillna("unknown")
                
                # Features: priority, type, redundancy_risk, impact, tech_skill, eta_minutes, completed_minutes
                feats = ["priority_num", "redundancy_risk", "impact", "tech_skill", "eta_minutes", "completed_minutes"]
                
                # Add one-hot encoding for type and first_tag
                type_dummies = pd.get_dummies(hist_df["type"], prefix="type")
                tag_dummies = pd.get_dummies(hist_df["first_tag"], prefix="tag")
                
                X = pd.concat([hist_df[feats], type_dummies, tag_dummies], axis=1).fillna(0.0)
                y = hist_df["needs_training"].astype(int)
                
                # Use this dataset instead
                df = None  # Mark that we're using raw data
        except Exception as e:
            # Fall back to aggregated data if raw history not available
            use_raw_history = False
            df = pd.read_csv(path_csv)
    
    # Option 2: Train on aggregated tech×tag pairs (original approach)
    if not use_raw_history:
        df = pd.read_csv(path_csv)
        if df.empty or df["needs_training"].sum() == 0:
            return None, None
        feats = ["n","rework","overrun","avg_eta","avg_completed","risk","avg_priority","tech_skill"]
        X = df[feats].fillna(0.0)
        y = df["needs_training"].astype(int)

    # Check if stratification is possible (need at least 2 samples per class)
    use_stratify = True
    if len(y) < 4 or y.value_counts().min() < 2:
        use_stratify = False

    # For very small datasets, train on all data and skip evaluation
    if len(y) < 10:
        clf = LogisticRegression(max_iter=200).fit(X, y)
        return clf, {
            "auc": None, 
            "report": f"Model trained on all {len(y)} samples. Evaluation metrics unavailable with small dataset.",
            "note": "Dataset too small for train/test split. Model is ready for use but evaluation metrics are not available."
        }

    # Use 40% for training and 10% for test (50% unused/held out)
    # First split: 40% train, 60% temp (which will be split into 10% test + 50% unused)
    if use_stratify:
        Xtr, Xtemp, ytr, ytemp = train_test_split(X, y, test_size=0.6, random_state=42, stratify=y)
        # Second split: from the 60%, take 10% for test (10/60 = 16.67% of temp, which is 10% of total)
        # Check if stratification is possible for second split
        can_stratify_second = len(ytemp) >= 4 and ytemp.value_counts().min() >= 2
        if can_stratify_second:
            X_unused, Xte, y_unused, yte = train_test_split(Xtemp, ytemp, test_size=0.1667, random_state=42, stratify=ytemp)
        else:
            X_unused, Xte, y_unused, yte = train_test_split(Xtemp, ytemp, test_size=0.1667, random_state=42)
    else:
        Xtr, Xtemp, ytr, ytemp = train_test_split(X, y, test_size=0.6, random_state=42)
        X_unused, Xte, y_unused, yte = train_test_split(Xtemp, ytemp, test_size=0.1667, random_state=42)

    clf = LogisticRegression(max_iter=200).fit(Xtr, ytr)

    pred = clf.predict_proba(Xte)[:,1]

    # Check if we have both classes in test set for AUC
    if len(yte.unique()) < 2:
        auc = None
        report = f"Model trained on {len(Xtr)} samples ({len(Xtr)/len(X)*100:.1f}% of data). Test set ({len(Xte)} samples, {len(Xte)/len(X)*100:.1f}% of data) contains only one class, so evaluation metrics are unavailable. {len(X_unused)} samples ({len(X_unused)/len(X)*100:.1f}%) held out."
    else:
        auc = roc_auc_score(yte, pred)
        report = classification_report(yte, pred>0.5, zero_division=0)
        report = f"Train: {len(Xtr)} samples ({len(Xtr)/len(X)*100:.1f}%), Test: {len(Xte)} samples ({len(Xte)/len(X)*100:.1f}%), Held out: {len(X_unused)} samples ({len(X_unused)/len(X)*100:.1f}%)\n\n" + report

    return clf, {"auc":auc, "report":report}

def train_predictive_maintenance_model(path_csv="data/train_predictive_maint.csv", use_raw_failures=True):

    # Option 1: Train on raw failure events (more data points)
    if use_raw_failures:
        fail_path = "data/failure_events.csv"
        try:
            fail_df = pd.read_csv(fail_path)
            if not fail_df.empty:
                # Label: fail soon (<=3 days) vs not
                fail_df["label_fail_soon"] = (fail_df["days_to_fail"] <= 3).astype(int)
                
                # Convert priority to numeric
                fail_df["priority_num"] = fail_df["priority"].map({"Low":1,"Medium":2,"High":3,"Critical":4}).fillna(2)
                
                # Features: failure_tag (one-hot), priority (one-hot), redundancy_risk, days_to_fail, type (one-hot)
                failure_tag_dummies = pd.get_dummies(fail_df["failure_tag"], prefix="tag")
                priority_dummies = pd.get_dummies(fail_df["priority"], prefix="prio")
                type_dummies = pd.get_dummies(fail_df["type"], prefix="type")
                
                X = pd.concat([
                    fail_df[["redundancy_risk", "days_to_fail", "priority_num"]],
                    failure_tag_dummies,
                    priority_dummies,
                    type_dummies
                ], axis=1).fillna(0.0)
                y = fail_df["label_fail_soon"].astype(int)
                
                # Use this dataset
                df = None
        except Exception as e:
            # Fall back to pre-processed data if raw failures not available
            use_raw_failures = False
            df = pd.read_csv(path_csv)
    
    # Option 2: Use pre-processed training data (original approach)
    if not use_raw_failures:
        df = pd.read_csv(path_csv)
        if df.empty or "label_fail_soon" not in df.columns:
            return None, None
        y = df["label_fail_soon"].astype(int)
        X = df.drop(columns=["label_fail_soon"])

    # Check if stratification is possible (need at least 2 samples per class)
    use_stratify = True
    if len(y) < 4 or y.value_counts().min() < 2:
        use_stratify = False

    # Use 40% for training and 10% for test (50% unused/held out)
    # First split: 40% train, 60% temp (which will be split into 10% test + 50% unused)
    if use_stratify:
        Xtr, Xtemp, ytr, ytemp = train_test_split(X, y, test_size=0.6, random_state=42, stratify=y)
        # Second split: from the 60%, take 10% for test (10/60 = 16.67% of temp, which is 10% of total)
        # Check if stratification is possible for second split
        can_stratify_second = len(ytemp) >= 4 and ytemp.value_counts().min() >= 2
        if can_stratify_second:
            X_unused, Xte, y_unused, yte = train_test_split(Xtemp, ytemp, test_size=0.1667, random_state=42, stratify=ytemp)
        else:
            X_unused, Xte, y_unused, yte = train_test_split(Xtemp, ytemp, test_size=0.1667, random_state=42)
    else:
        Xtr, Xtemp, ytr, ytemp = train_test_split(X, y, test_size=0.6, random_state=42)
        X_unused, Xte, y_unused, yte = train_test_split(Xtemp, ytemp, test_size=0.1667, random_state=42)

    clf = LogisticRegression(max_iter=200).fit(Xtr, ytr)

    pred = clf.predict_proba(Xte)[:,1]

    # Check if we have both classes in test set for AUC
    if len(yte.unique()) < 2:
        auc = None
    else:
        auc = roc_auc_score(yte, pred)

    return clf, {
        "auc": auc,
        "train_size": len(Xtr),
        "test_size": len(Xte),
        "held_out_size": len(X_unused),
        "train_pct": len(Xtr)/len(X)*100,
        "test_pct": len(Xte)/len(X)*100,
        "held_out_pct": len(X_unused)/len(X)*100
    }

