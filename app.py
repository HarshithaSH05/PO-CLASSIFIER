import csv
import io
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

if "history" not in st.session_state:
    st.session_state.history = []
if "po_desc" not in st.session_state:
    st.session_state.po_desc = ""
if "supplier" not in st.session_state:
    st.session_state.supplier = ""

with st.sidebar:
    st.subheader("Quick Start")
    sample = st.selectbox(
        "Example descriptions",
        [
            "Annual maintenance for HVAC systems across all facilities.",
            "Microsoft 365 enterprise subscription renewal.",
            "Recruitment fees for senior engineering roles.",
            "Catering services for quarterly all-hands meeting.",
        ],
    )
    use_sample = st.checkbox("Use selected example")

    st.subheader("Quality Tips")
    st.write("Include item type, scope, and duration.")
    st.write("Mention supplier if known.")
    debug_mode = st.toggle("Debug mode", value=False)

    st.subheader("Taxonomy")
    if st.checkbox("Show taxonomy list"):
        st.text(get_taxonomy_set())

def _extract_levels(parsed: dict) -> tuple[str | None, str | None, str | None]:
    key_map = {str(key).strip().lower(): key for key in parsed.keys()}
    l1 = parsed.get(key_map.get("l1")) if "l1" in key_map else None
    l2 = parsed.get(key_map.get("l2")) if "l2" in key_map else None
    l3 = parsed.get(key_map.get("l3")) if "l3" in key_map else None
    return l1, l2, l3


def _parse_result(result) -> dict | None:
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            return json.loads(result)
        except Exception:
            return None
    return None


def _taxonomy_status(parsed: dict) -> tuple[bool | None, str]:
    l1, l2, l3 = _extract_levels(parsed)
    if l1 is None or l2 is None:
        return None, "Classification missing L1/L2 fields — needs review."
    key = f"{str(l1).strip()}|{str(l2).strip()}|{str(l3 or '').strip()}"
    if key not in get_taxonomy_set():
        return False, "Classification not in taxonomy — needs review."
    return True, "Classification matches taxonomy."


tab_single, tab_bulk, tab_history = st.tabs(["Single", "Bulk CSV", "History"])

with tab_single:
    col_left, col_right = st.columns([3, 1])
    with col_left:
        if use_sample:
            st.session_state.po_desc = sample
        po_description = st.text_area(
            "PO Description",
            height=140,
            key="po_desc",
            placeholder="Example: Annual maintenance for HVAC systems across all facilities.",
            help="Be as specific as possible for best results.",
        )
    with col_right:
        supplier = st.text_input(
            "Supplier (optional)",
            key="supplier",
            placeholder="Example: Acme Mechanical Inc.",
            help="Optional, but can improve classification accuracy.",
        )
        st.write("")
        clear = st.button("Clear", use_container_width=True)
        if clear:
            st.session_state.po_desc = ""
            st.session_state.supplier = ""
            st.session_state.history = []
            st.experimental_rerun()


    if st.button("Classify", use_container_width=True):
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
            parsed = _parse_result(result)
            if parsed is not None:
                l1, l2, l3 = _extract_levels(parsed)
                status, status_msg = _taxonomy_status(parsed)

                metric_cols = st.columns(3)
                metric_cols[0].metric("L1", str(l1 or "—"))
                metric_cols[1].metric("L2", str(l2 or "—"))
                metric_cols[2].metric("L3", str(l3 or "—"))

                if status is True:
                    st.success(status_msg)
                else:
                    st.warning(status_msg)

                st.subheader("Full Output")
                st.json(parsed)

                st.download_button(
                    "Download JSON",
                    data=json.dumps(parsed, indent=2),
                    file_name="po_classification.json",
                    mime="application/json",
                )

                st.session_state.history.insert(
                    0,
                    {
                        "description": po_description,
                        "supplier": supplier,
                        "l1": l1,
                        "l2": l2,
                        "l3": l3,
                        "raw": parsed,
                    },
                )
                st.session_state.history = st.session_state.history[:10]
            else:
                st.error("Invalid model response")
                st.code(result or "", language="text")

        if debug_mode:
            with st.expander("Debug details"):
                st.write(f"Latency: {elapsed_ms:.1f} ms")
                if error:
                    st.exception(error)
                else:
                    st.write("Raw response:")
                    st.code(result or "", language="text")

with tab_bulk:
    st.write("Upload a CSV with columns: `description` and optional `supplier`.")
    file = st.file_uploader("CSV file", type=["csv"])
    if file is not None:
        data = file.read().decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(data))
        rows = list(reader)
        st.write(f"Loaded {len(rows)} rows.")

        if st.button("Classify CSV"):
            results = []
            progress = st.progress(0)
            for idx, row in enumerate(rows, start=1):
                desc = (row.get("description") or "").strip()
                supp = (row.get("supplier") or "").strip()
                if not desc:
                    results.append(
                        {
                            "description": desc,
                            "supplier": supp,
                            "status": "missing description",
                            "l1": "",
                            "l2": "",
                            "l3": "",
                        }
                    )
                    continue
                try:
                    raw = classify_po(desc, supp)
                    parsed = _parse_result(raw)
                    if parsed is None:
                        results.append(
                            {
                                "description": desc,
                                "supplier": supp,
                                "status": "invalid response",
                                "l1": "",
                                "l2": "",
                                "l3": "",
                            }
                        )
                    else:
                        l1, l2, l3 = _extract_levels(parsed)
                        status, _ = _taxonomy_status(parsed)
                        results.append(
                            {
                                "description": desc,
                                "supplier": supp,
                                "status": "ok" if status else "needs review",
                                "l1": l1 or "",
                                "l2": l2 or "",
                                "l3": l3 or "",
                            }
                        )
                except Exception as exc:
                    logging.exception("Bulk classification failed")
                    results.append(
                        {
                            "description": desc,
                            "supplier": supp,
                            "status": f"error: {exc}",
                            "l1": "",
                            "l2": "",
                            "l3": "",
                        }
                    )
                progress.progress(idx / max(len(rows), 1))

            output = io.StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=["description", "supplier", "status", "l1", "l2", "l3"],
            )
            writer.writeheader()
            writer.writerows(results)

            st.success("Bulk classification complete.")
            st.download_button(
                "Download results CSV",
                data=output.getvalue(),
                file_name="po_classification_results.csv",
                mime="text/csv",
            )

with tab_history:
    st.subheader("Recent Classifications")
    if st.session_state.history:
        for item in st.session_state.history:
            summary = f"{item['l1'] or '—'} / {item['l2'] or '—'} / {item['l3'] or '—'}"
            with st.expander(summary):
                st.write("Description:")
                st.code(item["description"] or "", language="text")
                if item["supplier"]:
                    st.write("Supplier:")
                    st.code(item["supplier"], language="text")
                st.write("Result:")
                st.json(item["raw"])
    else:
        st.write("No classifications yet.")
