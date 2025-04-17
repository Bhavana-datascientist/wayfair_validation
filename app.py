import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from PIL import Image

# ----------------- Initialize -----------------
st.set_page_config(layout="wide")
st.title("🛠️ Wayfair Multi-Attribute Validation Tool")

# ----------------- Load Data -----------------
DATA_FILE = "Data/sofa_streamlit.xlsx"  # update path as needed

@st.cache_data
def load_data(path):
    return pd.read_excel(path)

@st.cache_data
def load_image(url):
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200 and "image" in resp.headers.get("content-type", "").lower():
            return Image.open(BytesIO(resp.content))
    except Exception:
        pass
    return None

# Load and sample
_df = load_data(DATA_FILE)
sample_df = _df.sample(frac=0.1, random_state=42).reset_index(drop=True)

# Identify attribute columns
attr_cols = [c for c in sample_df.columns if c not in ['SLNO', 'Image URL']]

# ----------------- Taxonomy -----------------
taxonomy = {
    'Product Type': ['Sofa'],
    'Sub Type': ['Loveseat', 'Sectional', 'Sleeper', 'Standard', 'Modular', 'Chaise'],
    'Silhouette': ['Straight', 'Curved', 'L-shaped', 'U-shaped', 'Tuxedo', 'Camelback', 'Lawson',
                   'English roll arm', 'Chesterfield', 'Mid-century', 'Cabriole'],
    'Back Style': ['Tight', 'Pillow', 'Tufted', 'Channel', 'Split', 'Camelback', 'Low profile',
                   'High profile', 'Multi-cushion', 'Single-cushion'],
    'Upholstery Color': ["Off-White", "Ivory", "Cream", "Beige", "Taupe", "Light Gray", "Dark Gray", "Charcoal", "Black", "White"],
    'Upholstery Color_Hex': ['#FF0000', '#0000FF', '#00FF00', '#FFFF00'],
    'Pattern': ['Solid', 'Striped', 'Floral', 'Geometric', 'Checkered/Plaid', 'Abstract', 'Animal print', 'Dot', 'Herringbone', 'Ikat', 'Damask', 'Trellis'],
    'Sheen': ['Matte', 'Satin', 'Semi-gloss', 'High-gloss', 'Low-sheen', 'Reflective', 'Dull'],
    'Finish': ['Natural', 'Painted', 'Distressed', 'Polished', 'Lacquered', 'Antique', 'Chrome', 'Brass'],
    'Leg Visibility': ['Exposed', 'Hidden', 'No legs'],
    'Visual Weight': ['Light', 'Medium', 'Heavy'],
    # ... add others as needed ...
}

# ----------------- Initialize Default Status -----------------
if "init_defaults" not in st.session_state:
    for idx in range(len(sample_df)):
        for attr in attr_cols:
            st.session_state[f"status_{idx}_{attr}"] = "Correct"
    st.session_state["init_defaults"] = True
    st.session_state["evaluation_complete"] = False

# ----------------- Pagination Setup -----------------
per_page = 20
page = st.session_state.get('page', 0)
start = page * per_page
end = min(start + per_page, len(sample_df))
page_df = sample_df.iloc[start:end]

total_pages = (len(sample_df) - 1) // per_page + 1

st.write(f"Displaying items {start+1}–{end} of {len(sample_df)} for validation (Page {page+1}/{total_pages}).")

# ----------------- Display Grid -----------------
cols_per_row = 4
for i in range(0, len(page_df), cols_per_row):
    cols = st.columns(cols_per_row)
    for j in range(cols_per_row):
        idx = start + i + j
        if idx < len(sample_df):
            row = sample_df.iloc[idx]
            with cols[j]:
                img = load_image(row['Image URL'])
                if img:
                    st.image(img, use_column_width=True)
                else:
                    st.write("No image available")
                st.markdown(f"**SLNO:** {row['SLNO']}")
                for attr in attr_cols:
                    val = row[attr]
                    st.write(f"- **{attr}:** {val}")
                    status_key = f"status_{idx}_{attr}"
                    choice = st.radio(
                        "",
                        ["Correct", "It's wrong, let's update"],
                        key=status_key,
                        horizontal=True
                    )
                    if choice == "It's wrong, let's update":
                        options = taxonomy.get(attr, [])
                        new_key = f"new_{idx}_{attr}"
                        st.selectbox(
                            "Select new value:",
                            options,
                            key=new_key
                        )

# ----------------- Navigation -----------------
pcol, scol, ncol = st.columns(3)
with pcol:
    if st.button("◀ Previous") and page > 0:
        st.session_state['page'] = page - 1
        st.experimental_rerun()
with scol:
    if page == total_pages - 1 and not st.session_state.get("evaluation_complete"):
        if st.button("🏁 Finish Evaluation and Show Metrics"):
            st.session_state['evaluation_complete'] = True
            st.experimental_rerun()
    elif st.session_state.get("evaluation_complete"):
        st.write("✅ Evaluation complete. Metrics are now available below.")
with ncol:
    if st.button("Next ▶") and page < total_pages - 1:
        st.session_state['page'] = page + 1
        st.experimental_rerun()

# ----------------- Performance Metrics -----------------
if st.session_state.get("evaluation_complete"):
    metrics_attr = st.selectbox(
        "Select Attribute for Performance Metrics",
        ['-- none --'] + attr_cols,
        key="metrics_attr"
    )
    if metrics_attr and metrics_attr != '-- none --':
        total = len(sample_df)
        correct = sum(
            1 for idx in range(total)
            if st.session_state.get(f"status_{idx}_{metrics_attr}", "Correct") == "Correct"
        )
        accuracy = correct / total
       
        precision = accuracy
        recall = accuracy
        c1, c2, c3 = st.columns(3)
        c1.metric("Accuracy", f"{accuracy:.2%}")
        c2.metric("Precision", f"{precision:.2%}")
        c3.metric("Recall", f"{recall:.2%}")

    # ----------------- Save Corrected Excel -----------------
    if st.button("💾 Save Corrected Excel"):
        updated = _df.copy()
        for idx in range(len(sample_df)):
            slno = sample_df.at[idx, 'SLNO']
            for attr in attr_cols:
                if st.session_state.get(f"status_{idx}_{attr}") == "It's wrong, let's update":
                    new_val = st.session_state.get(f"new_{idx}_{attr}")
                    updated.loc[updated['SLNO'] == slno, attr] = new_val
        updated.to_excel("updated_attributes.xlsx", index=False)
        st.success("Updated file saved as 'updated_attributes.xlsx'.")
