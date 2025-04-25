import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from PIL import Image
from pymongo import MongoClient
from bson import ObjectId
from sklearn.metrics import accuracy_score, precision_score, recall_score

st.set_page_config(layout="wide")
st.title("🛠️ Wayfair Multi-Attribute Validation Tool")

# ----------------- MongoDB Connection -----------------
client = MongoClient("mongodb+srv://bhavana:Trends_bhavana@wayfair.xve1u.mongodb.net/console?retryWrites=true&w=majority")
db = client['console']
evaluation_collection = db['Evaluation_metric']
batch_collection = db['Batch_table']  # NEW: For storing batch metrics

# ----------------- Category Selection -----------------
st.sidebar.header("📂 Select Category")
categories = ['sofa', 'coffee_table', 'accent_chair']
selected_category = st.sidebar.selectbox("Category", categories)

if "selected_category" not in st.session_state:
    st.session_state.selected_category = selected_category

if st.session_state.selected_category != selected_category:
    st.session_state.selected_category = selected_category
    st.experimental_rerun()

# Load MongoDB collections
data_collection = db[f'Attributes_Validation_{selected_category}']
taxonomy_collection = db[f'{selected_category}_taxonomy']

# ----------------- Load Data -----------------
@st.cache_data
def load_data(_collection):
    data = list(_collection.find())
    return pd.DataFrame(data)

_df = load_data(data_collection)
sample_df = _df.sample(frac=0.1, random_state=42).reset_index(drop=True)
attr_cols = [c for c in sample_df.columns if c not in ['_id', 'SLNO', 'Image URL']]

# ----------------- Load Taxonomy -----------------
@st.cache_data
def load_taxonomy(_taxonomy_collection):
    doc = _taxonomy_collection.find_one()
    if doc:
        doc.pop('_id', None)
        return doc
    else:
        st.warning("⚠️ No taxonomy found for this category.")
        return {}

taxonomy = load_taxonomy(taxonomy_collection)

# ----------------- Image Loader -----------------
@st.cache_data
def load_image(url):
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200 and "image" in resp.headers.get("content-type", "").lower():
            return Image.open(BytesIO(resp.content))
    except Exception:
        pass
    return None

# ----------------- Session State Initialization -----------------
if "page" not in st.session_state:
    st.session_state.page = 0

if "feedback" not in st.session_state:
    st.session_state.feedback = {}

# ----------------- Pagination -----------------
per_page = 20
page = st.session_state.page
start = page * per_page
end = min(start + per_page, len(sample_df))
page_df = sample_df.iloc[start:end]
total_pages = (len(sample_df) - 1) // per_page + 1

st.write(f"Displaying items {start+1}–{end} of {len(sample_df)} (Page {page+1}/{total_pages})")

# ----------------- Display Grid -----------------
cols_per_row = 4
for i in range(0, len(page_df), cols_per_row):
    cols = st.columns(cols_per_row)
    for j in range(cols_per_row):
        idx = start + i + j
        if idx < len(sample_df):
            row = sample_df.iloc[idx]
            row_id = str(row['_id'])
            with cols[j]:
                img = load_image(row['Image URL'])
                if img:
                    st.image(img, use_column_width=True)
                else:
                    st.write("No image available")
                st.markdown(f"**SLNO:** {row['SLNO']}")

                for attr in attr_cols:
                    key_status = f"{idx}_{attr}_status"
                    key_newval = f"{idx}_{attr}_newval"

                    default_status = st.session_state.feedback.get(key_status, "Correct")
                    status = st.radio(
                        f"{attr}: {row[attr]}",
                        ["Correct", "Wrong"],
                        key=key_status,
                        index=0 if default_status == "Correct" else 1,
                        horizontal=True
                    )
                    st.session_state.feedback[key_status] = status

                    if status == "Wrong":
                        options = taxonomy.get(attr, [])
                        default_new_val = st.session_state.feedback.get(key_newval, "")
                        new_val = st.selectbox(
                            f"Select correct {attr}",
                            [""] + options,
                            index=([""] + options).index(default_new_val) if default_new_val in ([""] + options) else 0,
                            key=key_newval
                        )
                        st.session_state.feedback[key_newval] = new_val

# ----------------- Save Updates -----------------
if st.button("📂 Save Updates"):
    updated_count = 0
    for idx in range(start, end):
        row = sample_df.iloc[idx]
        obj_id = ObjectId(row['_id']) if not isinstance(row['_id'], ObjectId) else row['_id']
        doc = data_collection.find_one({'_id': obj_id})
        if not doc:
            continue
        updates = {}
        for attr in attr_cols:
            key_status = f"{idx}_{attr}_status"
            key_newval = f"{idx}_{attr}_newval"
            if st.session_state.feedback.get(key_status) == "Wrong":
                new_val = st.session_state.feedback.get(key_newval)
                if new_val and new_val != doc.get(attr):
                    updates[attr] = new_val
        if updates:
            result = data_collection.update_one({'_id': obj_id}, {'$set': updates})
            if result.modified_count > 0:
                st.success(f"✅ Updated: {row['SLNO']} | Fields: {list(updates.keys())}")
                updated_count += 1
    st.write(f"🔄 Total updated documents: {updated_count}")

# ----------------- Navigation -----------------
col1, col2, col3 = st.columns([1, 1, 6])
with col1:
    if st.button("⬅️ Previous") and st.session_state.page > 0:
        st.session_state.page -= 1
with col2:
    if st.button("Next ➡️") and st.session_state.page < total_pages - 1:
        st.session_state.page += 1

# ----------------- Metrics -----------------
if page == total_pages - 1:
    st.markdown("---")
    st.header("📊 Attribute Performance Metrics")

    batch_id = str(sample_df['_id'].iloc[0])[:8]  # Example batch_id derived from first ID
    evaluation_data = []
    attribute_scores = {}

    for idx in range(len(sample_df)):
        row = sample_df.iloc[idx]
        row_eval = {'batch_id': batch_id, 'SLNO': row['SLNO']}
        for attr in attr_cols:
            key_status = f"{idx}_{attr}_status"
            key_newval = f"{idx}_{attr}_newval"
            status = st.session_state.feedback.get(key_status)
            if status == "Correct":
                row_eval[attr] = "correct"
            elif status == "Wrong":
                selected_val = st.session_state.feedback.get(key_newval, "")
                row_eval[attr] = "wrong" if selected_val else ""
        evaluation_data.append(row_eval)

    for attr in attr_cols:
        y_true, y_pred = [], []
        for idx in range(len(sample_df)):
            row = sample_df.iloc[idx]
            key_status = f"{idx}_{attr}_status"
            key_newval = f"{idx}_{attr}_newval"
            if key_status in st.session_state.feedback:
                original_val = row[attr]
                status = st.session_state.feedback.get(key_status)
                if status == "Correct":
                    y_true.append(original_val)
                    y_pred.append(original_val)
                elif status == "Wrong":
                    new_val = st.session_state.feedback.get(key_newval)
                    if new_val:
                        y_true.append(original_val)
                        y_pred.append(new_val)
        if y_true:
            attribute_scores[attr] = {
                "accuracy": accuracy_score(y_true, y_pred),
                "precision": precision_score(y_true, y_pred, average='macro', zero_division=0),
                "recall": recall_score(y_true, y_pred, average='macro', zero_division=0)
            }

    # Insert all evaluation rows
    evaluation_collection.insert_many(evaluation_data)

    # Store evaluation scores into batch table
    batch_collection.insert_one({
        "batch_id": batch_id,
        "category": selected_category,
        "attribute_scores": attribute_scores
    })

    # Display metrics for selected attribute
    selected_attr = st.selectbox("Select an attribute", attr_cols)
    if selected_attr in attribute_scores:
        st.metric("✅ Accuracy", f"{attribute_scores[selected_attr]['accuracy']:.2%}")
        st.metric("📌 Precision", f"{attribute_scores[selected_attr]['precision']:.2%}")
        st.metric("🎯 Recall", f"{attribute_scores[selected_attr]['recall']:.2%}")
    else:
        st.info("No validated records yet.")
