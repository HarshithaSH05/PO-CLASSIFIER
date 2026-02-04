import csv
import io
import json
import logging
import time

import streamlit as st

from classifier import classify_po
from taxonomy import get_taxonomy_rows, get_taxonomy_set

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
if "feedback" not in st.session_state:
    st.session_state.feedback = []
if "cache" not in st.session_state:
    st.session_state.cache = {}

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
        taxonomy_rows = get_taxonomy_rows()
        search = st.text_input("Search taxonomy", placeholder="Type L1/L2/L3 keywords")
        if search:
            search_lower = search.strip().lower()
            taxonomy_rows = [
                row
                for row in taxonomy_rows
                if search_lower in row["L1"].lower()
                or search_lower in row["L2"].lower()
                or search_lower in row["L3"].lower()
            ]
        st.dataframe(taxonomy_rows, use_container_width=True)


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


def _cache_key(description: str, supplier: str) -> str:
    return f"{description.strip().lower()}|{supplier.strip().lower()}"


def _cached_classify(description: str, supplier: str) -> dict:
    key = _cache_key(description, supplier)
    if key in st.session_state.cache:
        return st.session_state.cache[key]
    raw = classify_po(description, supplier)
    parsed = _parse_result(raw)
    if parsed is not None:
        st.session_state.cache[key] = parsed
    return parsed


def _validate_schema(parsed: dict) -> tuple[bool, str]:
    required = ["L1", "L2", "L3"]
    missing = [key for key in required if key not in parsed]
    if missing:
        return False, f"Missing fields: {', '.join(missing)}"
    return True, "OK"


def _taxonomy_status(parsed: dict) -> tuple[bool | None, str]:
    l1, l2, l3 = _extract_levels(parsed)
    if l1 is None or l2 is None:
        return None, "Classification missing L1/L2 fields - needs review."
    key = f"{str(l1).strip()}|{str(l2).strip()}|{str(l3 or '').strip()}"
    if key not in get_taxonomy_set():
        return False, "Classification not in taxonomy - needs review."
    return True, "Classification matches taxonomy."


def _match_quality_note(parsed: dict) -> str | None:
    quality = parsed.get("match_quality") if isinstance(parsed, dict) else None
    if not quality:
        return None
    quality = str(quality).strip().lower()
    if quality == "closest":
        return "Closest taxonomy match selected (not exact)."
    if quality == "not_sure":
        return "Model could not find a reasonable match."
    if quality == "exact":
        return "Exact taxonomy match."
    return None


def _confidence_value(parsed: dict) -> float | None:
    raw = parsed.get("confidence") if isinstance(parsed, dict) else None
    if raw is None:
        return None
    try:
        value = float(raw)
    except Exception:
        return None
    if value < 0 or value > 1:
        return None
    return value


def _confidence_label(value: float | None) -> str:
    if value is None:
        return "-"
    if value >= 0.8:
        return f"High ({value:.2f})"
    if value >= 0.5:
        return f"Medium ({value:.2f})"
    return f"Low ({value:.2f})"


tab_single, tab_bulk, tab_history, tab_eval = st.tabs(
    ["Single", "Bulk CSV", "History", "Evaluate"]
)

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
            try:
                st.rerun()
            except AttributeError:
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
        if len(po_description.split()) < 3:
            st.info("Tip: add more detail (item, scope, duration) for better accuracy.")
        if supplier and len(supplier) > 80:
            st.warning("Supplier name is quite long. Please shorten it (80 chars max).")
            st.stop()

        result = None
        error = None
        elapsed_ms = None
        with st.spinner("Classifying..."):
            start = time.perf_counter()
            try:
                result = _cached_classify(po_description, supplier)
            except Exception as exc:
                error = exc
                logging.exception("Classification failed")
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000

        if error:
            st.error("Classification failed. Please try again.")
        else:
            parsed = result
            schema_ok = False
            if parsed is not None:
                schema_ok, _ = _validate_schema(parsed)
            if parsed is None or not schema_ok:
                try:
                    retry = classify_po(po_description, supplier)
                    parsed = _parse_result(retry)
                except Exception:
                    parsed = None
            if parsed is not None:
                schema_ok, schema_msg = _validate_schema(parsed)
                if not schema_ok:
                    st.error(f"Invalid model response: {schema_msg}")
                    st.code(result or "", language="text")
                    if debug_mode:
                        with st.expander("Debug details"):
                            st.write("Raw response:")
                            st.code(result or "", language="text")
                    st.stop()
                l1, l2, l3 = _extract_levels(parsed)
                status, status_msg = _taxonomy_status(parsed)
                confidence = _confidence_value(parsed)

                metric_cols = st.columns(4)
                metric_cols[0].metric("L1", str(l1 or "-"))
                metric_cols[1].metric("L2", str(l2 or "-"))
                metric_cols[2].metric("L3", str(l3 or "-"))
                metric_cols[3].metric("Confidence", _confidence_label(confidence))

                if status is True:
                    st.success(status_msg)
                else:
                    st.warning(status_msg)
                    if st.button("Retry classification (closest match)"):
                        try:
                            retry = classify_po(po_description, supplier)
                            parsed = _parse_result(retry)
                            if parsed:
                                st.success("Reclassified. Scroll up to see updated values.")
                        except Exception:
                            st.error("Retry failed. Please try again later.")

                note = _match_quality_note(parsed)
                if note:
                    st.info(note)

                st.subheader("Full Output")
                st.json(parsed)

                st.download_button(
                    "Download JSON",
                    data=json.dumps(parsed, indent=2),
                    file_name="po_classification.json",
                    mime="application/json",
                )

                st.subheader("Feedback (Optional)")
                taxonomy_rows = get_taxonomy_rows()
                l1_options = sorted({row["L1"] for row in taxonomy_rows})
                l1_choice = st.selectbox("Correct L1", l1_options, index=0)
                l2_options = sorted(
                    {row["L2"] for row in taxonomy_rows if row["L1"] == l1_choice}
                )
                l2_choice = st.selectbox("Correct L2", l2_options, index=0)
                l3_options = sorted(
                    {
                        row["L3"]
                        for row in taxonomy_rows
                        if row["L1"] == l1_choice and row["L2"] == l2_choice
                    }
                )
                l3_choice = st.selectbox("Correct L3", l3_options, index=0)
                if st.button("Submit Feedback"):
                    st.session_state.feedback.append(
                        {
                            "description": po_description,
                            "supplier": supplier,
                            "pred_l1": l1,
                            "pred_l2": l2,
                            "pred_l3": l3,
                            "correct_l1": l1_choice,
                            "correct_l2": l2_choice,
                            "correct_l3": l3_choice,
                            "match_quality": parsed.get("match_quality"),
                            "confidence": confidence,
                        }
                    )
                    st.success("Feedback saved for export.")

                st.session_state.history.insert(
                    0,
                    {
                        "description": po_description,
                        "supplier": supplier,
                        "l1": l1,
                        "l2": l2,
                        "l3": l3,
                        "match_quality": parsed.get("match_quality"),
                        "confidence": confidence,
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
                            "match_quality": "",
                            "confidence": "",
                            "l1": "",
                            "l2": "",
                            "l3": "",
                        }
                    )
                    continue
                try:
                    parsed = _cached_classify(desc, supp)
                    schema_ok = False
                    if parsed is not None:
                        schema_ok, _ = _validate_schema(parsed)
                    if parsed is None or not schema_ok:
                        retry = classify_po(desc, supp)
                        parsed = _parse_result(retry)
                    if parsed is None:
                        results.append(
                            {
                                "description": desc,
                                "supplier": supp,
                                "status": "invalid response",
                                "match_quality": "",
                                "confidence": "",
                                "l1": "",
                                "l2": "",
                                "l3": "",
                            }
                        )
                    else:
                        l1, l2, l3 = _extract_levels(parsed)
                        status, _ = _taxonomy_status(parsed)
                        match_quality = parsed.get("match_quality")
                        confidence = _confidence_value(parsed)
                        results.append(
                            {
                                "description": desc,
                                "supplier": supp,
                                "status": "ok" if status else "needs review",
                                "match_quality": match_quality or "",
                                "confidence": f"{confidence:.2f}" if confidence is not None else "",
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
                            "match_quality": "",
                            "confidence": "",
                            "l1": "",
                            "l2": "",
                            "l3": "",
                        }
                    )
                progress.progress(idx / max(len(rows), 1))

            output = io.StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "description",
                    "supplier",
                    "status",
                    "match_quality",
                    "confidence",
                    "l1",
                    "l2",
                    "l3",
                ],
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
        export_rows = []
        for item in st.session_state.history:
            summary = f"{item['l1'] or '-'} / {item['l2'] or '-'} / {item['l3'] or '-'}"
            with st.expander(summary):
                st.write("Description:")
                st.code(item["description"] or "", language="text")
                if item["supplier"]:
                    st.write("Supplier:")
                    st.code(item["supplier"], language="text")
                if item.get("match_quality"):
                    st.write(f"Match quality: {item['match_quality']}")
                if item.get("confidence") is not None:
                    st.write(f"Confidence: {item['confidence']}")
                st.write("Result:")
                st.json(item["raw"])
            export_rows.append(
                {
                    "description": item["description"],
                    "supplier": item["supplier"],
                    "l1": item["l1"] or "",
                    "l2": item["l2"] or "",
                    "l3": item["l3"] or "",
                    "match_quality": item.get("match_quality") or "",
                    "confidence": item.get("confidence") or "",
                }
            )
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "description",
                "supplier",
                "l1",
                "l2",
                "l3",
                "match_quality",
                "confidence",
            ],
        )
        writer.writeheader()
        writer.writerows(export_rows)
        st.download_button(
            "Download history CSV",
            data=output.getvalue(),
            file_name="po_classification_history.csv",
            mime="text/csv",
        )
        if st.session_state.feedback:
            feedback_output = io.StringIO()
            feedback_writer = csv.DictWriter(
                feedback_output,
                fieldnames=[
                    "description",
                    "supplier",
                    "pred_l1",
                    "pred_l2",
                    "pred_l3",
                    "correct_l1",
                    "correct_l2",
                    "correct_l3",
                    "match_quality",
                    "confidence",
                ],
            )
            feedback_writer.writeheader()
            feedback_writer.writerows(st.session_state.feedback)
            st.download_button(
                "Download feedback CSV",
                data=feedback_output.getvalue(),
                file_name="po_classification_feedback.csv",
                mime="text/csv",
            )
    else:
        st.write("No classifications yet.")

with tab_eval:
    st.write("Upload a labeled CSV with columns: `description`, `supplier`, `L1`, `L2`, `L3`.")
    eval_file = st.file_uploader("Labeled CSV", type=["csv"], key="eval_csv")
    if eval_file is not None:
        data = eval_file.read().decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(data))
        rows = list(reader)
        st.write(f"Loaded {len(rows)} rows.")

        if st.button("Evaluate CSV"):
            results = []
            correct = 0
            total = 0
            progress = st.progress(0)
            for idx, row in enumerate(rows, start=1):
                desc = (row.get("description") or "").strip()
                supp = (row.get("supplier") or "").strip()
                gold_l1 = (row.get("L1") or "").strip()
                gold_l2 = (row.get("L2") or "").strip()
                gold_l3 = (row.get("L3") or "").strip()
                if not desc:
                    continue
                total += 1
                try:
                    raw = classify_po(desc, supp)
                    parsed = _parse_result(raw)
                    if parsed is None:
                        retry = classify_po(desc, supp)
                        parsed = _parse_result(retry)
                    if parsed is None:
                        results.append(
                            {
                                "description": desc,
                                "supplier": supp,
                                "gold_l1": gold_l1,
                                "gold_l2": gold_l2,
                                "gold_l3": gold_l3,
                                "pred_l1": "",
                                "pred_l2": "",
                                "pred_l3": "",
                                "match": "error",
                            }
                        )
                    else:
                        pred_l1, pred_l2, pred_l3 = _extract_levels(parsed)
                        match = (
                            pred_l1 == gold_l1
                            and pred_l2 == gold_l2
                            and (pred_l3 or "") == gold_l3
                        )
                        if match:
                            correct += 1
                        results.append(
                            {
                                "description": desc,
                                "supplier": supp,
                                "gold_l1": gold_l1,
                                "gold_l2": gold_l2,
                                "gold_l3": gold_l3,
                                "pred_l1": pred_l1 or "",
                                "pred_l2": pred_l2 or "",
                                "pred_l3": pred_l3 or "",
                                "match": "yes" if match else "no",
                            }
                        )
                except Exception:
                    results.append(
                        {
                            "description": desc,
                            "supplier": supp,
                            "gold_l1": gold_l1,
                            "gold_l2": gold_l2,
                            "gold_l3": gold_l3,
                            "pred_l1": "",
                            "pred_l2": "",
                            "pred_l3": "",
                            "match": "error",
                        }
                    )
                progress.progress(idx / max(len(rows), 1))

            accuracy = (correct / total) * 100 if total else 0
            st.metric("Accuracy", f"{accuracy:.1f}%")

            output = io.StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "description",
                    "supplier",
                    "gold_l1",
                    "gold_l2",
                    "gold_l3",
                    "pred_l1",
                    "pred_l2",
                    "pred_l3",
                    "match",
                ],
            )
            writer.writeheader()
            writer.writerows(results)
            st.download_button(
                "Download evaluation CSV",
                data=output.getvalue(),
                file_name="po_classification_evaluation.csv",
                mime="text/csv",
            )
