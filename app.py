import json
import logging
import time

import streamlit as st

from classifier import classify_po
from taxonomy import get_taxonomy_set

logging.basicConfig(level=logging.INFO)

st.set_page_config(page_title="PO Category Classifier", layout="centered")

st.title("PO L1-L2-L3 Classifier")
st.caption("Paste a purchase order description to classify L1/L2/L3 categories.")

po_description = st.text_area(
    "PO Description",
    height=120,
    placeholder="Example: Annual maintenance for HVAC systems across all facilities.",
    help="Be as specific as possible for best results.",
)
supplier = st.text_input(
    "Supplier (optional)",
    placeholder="Example: Acme Mechanical Inc.",
    help="Optional, but can improve classification accuracy.",
)


def _extract_levels(parsed: dict) -> tuple[str | None, str | None, str | None]:
    key_map = {str(key).strip().lower(): key for key in parsed.keys()}
    l1 = parsed.get(key_map.get("l1")) if "l1" in key_map else None
    l2 = parsed.get(key_map.get("l2")) if "l2" in key_map else None
    l3 = parsed.get(key_map.get("l3")) if "l3" in key_map else None
    return l1, l2, l3


if st.button("Classify"):
    po_description = po_description.strip()
    supplier = supplier.strip()

    if not po_description:
        st.warning("Please enter a PO description.")
        st.stop()
    if len(po_description) < 10:
        st.warning("Please provide a slightly longer description (10+ characters).")
        st.stop()
    if supplier and len(supplier) > 80:
        st.warning("Supplier name is quite long. Please shorten it (80 chars max).")
        st.stop()

    result = None
    error = None
    elapsed_ms = None
    with st.spinner("Classifying..."):
        start = time.perf_counter()
        try:
            result = classify_po(po_description, supplier)
        except Exception as exc:
            error = exc
            logging.exception("Classification failed")
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000

    if error:
        st.error("Classification failed. Please try again.")
    else:
        parsed = None
        if isinstance(result, dict):
            parsed = result
        elif isinstance(result, str):
            try:
                parsed = json.loads(result)
            except Exception:
                parsed = None

        if parsed is not None:
            st.json(parsed)

            l1, l2, l3 = _extract_levels(parsed)
            if l1 is not None and l2 is not None:
                key = f"{str(l1).strip()}|{str(l2).strip()}|{str(l3 or '').strip()}"
                if key not in get_taxonomy_set():
                    st.warning("Classification not in taxonomy — needs review.")
            else:
                st.warning("Classification missing L1/L2 fields — needs review.")

            st.download_button(
                "Download JSON",
                data=json.dumps(parsed, indent=2),
                file_name="po_classification.json",
                mime="application/json",
            )
        else:
            st.error("Invalid model response")
            st.code(result or "", language="text")

    with st.expander("Debug details"):
        st.write(f"Latency: {elapsed_ms:.1f} ms")
        if error:
            st.exception(error)
        else:
            st.write("Raw response:")
            st.code(result or "", language="text")
