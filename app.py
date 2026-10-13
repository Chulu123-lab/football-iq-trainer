
import streamlit as st
import pandas as pd
import time
import csv
import os
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Football IQ Trainer", page_icon="⚽", layout="wide")

RESULTS_FILE = "training_results.csv"

st.title("⚽ Football IQ Trainer")
st.caption("Practice match analysis, record predictions, and measure your results.")

if "fixtures" not in st.session_state:
    st.session_state.fixtures = []
if "index" not in st.session_state:
    st.session_state.index = 0
if "phase" not in st.session_state:
    st.session_state.phase = "setup"
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "phase_started" not in st.session_state:
    st.session_state.phase_started = time.time()

def load_results():
    if os.path.exists(RESULTS_FILE):
        try:
            return pd.read_csv(RESULTS_FILE)
        except Exception:
            pass
    return pd.DataFrame(columns=[
        "saved_at", "fixture", "team_a", "team_b", "prediction",
        "actual", "correct", "team_a_seconds", "team_b_seconds",
        "prediction_seconds", "group_number"
    ])

def save_result(row):
    df = pd.DataFrame([row])
    df.to_csv(RESULTS_FILE, mode="a", header=not os.path.exists(RESULTS_FILE), index=False)

def result_to_pick(score):
    if pd.isna(score):
        return ""
    score = str(score).strip()
    try:
        a, b = score.replace(":", "-").split("-", 1)
        a, b = int(a.strip()), int(b.strip())
        return "1" if a > b else ("2" if a < b else "X")
    except Exception:
        return ""

def get_history(sheet, start_row, team_col, opponent_col, date_col, result_col, gf_col, ga_col):
    rows = []
    end_row = min(start_row + 25, len(sheet))
    for i in range(start_row, end_row):
        team = str(sheet.iloc[i, team_col]).strip()
        opponent = str(sheet.iloc[i, opponent_col]).strip()
        if team in ("", "nan", "None") or opponent in ("", "nan", "None"):
            continue
        rows.append({
            "Team": team,
            "Opponent": opponent,
            "Date": sheet.iloc[i, date_col],
            "Result": sheet.iloc[i, result_col],
            "GF": sheet.iloc[i, gf_col],
            "GA": sheet.iloc[i, ga_col]
        })
    return rows

st.header("1. Load match history")
st.write("Upload an exported Excel or CSV copy of your match-history sheet. This app does not edit your original spreadsheet.")

uploaded = st.file_uploader("Upload match history", type=["xlsx", "xls", "csv"])

if uploaded is not None:
    try:
        if uploaded.name.lower().endswith(".csv"):
            raw = pd.read_csv(uploaded, header=None)
        else:
            book = pd.ExcelFile(uploaded)
            sheet_name = st.selectbox("Choose worksheet", book.sheet_names)
            raw = pd.read_excel(uploaded, sheet_name=sheet_name, header=None)

        st.caption("Expected layout: Team A history in columns A–H, Team B history in I–P, actual score in Q, and actual date in R. Each fixture block has 25 history rows.")
        if st.button("Prepare fixtures"):
            fixtures = []
            for start in range(1, len(raw), 25):
                if raw.shape[1] < 18:
                    break
                hist_a = get_history(raw, start, 0, 1, 2, 3, 4, 5)
                hist_b = get_history(raw, start, 8, 9, 10, 11, 12, 13)
                if not hist_a or not hist_b:
                    continue
                actual_score = raw.iloc[start, 16] if start < len(raw) else ""
                actual_date = raw.iloc[start, 17] if start < len(raw) else ""
                team_a = hist_a[0]["Team"]
                team_b = hist_b[0]["Team"]
                fixtures.append({
                    "team_a": team_a, "team_b": team_b,
                    "history_a": hist_a, "history_b": hist_b,
                    "actual_score": actual_score, "actual_date": actual_date
                })
            st.session_state.fixtures = fixtures
            st.session_state.index = 0
            st.session_state.answers = {}
            st.session_state.phase = "team_a"
            st.session_state.phase_started = time.time()
            st.success(f"Prepared {len(fixtures)} fixtures.")
    except Exception as e:
        st.error(f"Could not read this file: {e}")

if st.session_state.fixtures:
    fixtures = st.session_state.fixtures
    idx = st.session_state.index

    if idx < len(fixtures):
        fixture = fixtures[idx]
        st.divider()
        st.subheader(f"Fixture {idx + 1} of {len(fixtures)}")
        st.write(f"**{fixture['team_a']} vs {fixture['team_b']}**")

        def show_history(team_name, history):
            st.markdown(f"### {team_name} — last matches")
            st.dataframe(pd.DataFrame(history), use_container_width=True, hide_index=True)

        if st.session_state.phase == "team_a":
            st_autorefresh(interval=1000, key="timer_a")
            elapsed = int(time.time() - st.session_state.phase_started)
            st.info(f"Team A analysis time: {elapsed // 60}:{elapsed % 60:02d}")
            show_history(fixture["team_a"], fixture["history_a"])
            if st.button("Next — Team B"):
                st.session_state.answers.setdefault(idx, {})["team_a_seconds"] = elapsed
                st.session_state.phase = "team_b"
                st.session_state.phase_started = time.time()
                st.rerun()

        elif st.session_state.phase == "team_b":
            st_autorefresh(interval=1000, key="timer_b")
            elapsed = int(time.time() - st.session_state.phase_started)
            st.info(f"Team B analysis time: {elapsed // 60}:{elapsed % 60:02d}")
            show_history(fixture["team_b"], fixture["history_b"])
            if st.button("Next — Make prediction"):
                st.session_state.answers.setdefault(idx, {})["team_b_seconds"] = elapsed
                st.session_state.phase = "predict"
                st.session_state.phase_started = time.time()
                st.rerun()

        elif st.session_state.phase == "predict":
            st_autorefresh(interval=1000, key="timer_predict")
            elapsed = int(time.time() - st.session_state.phase_started)
            st.info(f"Prediction time: {elapsed // 60}:{elapsed % 60:02d}")
            pick = st.radio(
                "Choose your prediction",
                ["1", "X", "2"],
                format_func=lambda x: {"1": f"1 — {fixture['team_a']} wins",
                                       "X": "X — Draw",
                                       "2": f"2 — {fixture['team_b']} wins"}[x],
                horizontal=True,
                key=f"pick_{idx}"
            )
            if st.button("Reveal actual result"):
                actual = result_to_pick(fixture["actual_score"])
                correct = (pick == actual) if actual else None
                answer = st.session_state.answers.setdefault(idx, {})
                answer["prediction_seconds"] = elapsed
                row = {
                    "saved_at": datetime.now().isoformat(timespec="seconds"),
                    "fixture": idx + 1,
                    "team_a": fixture["team_a"],
                    "team_b": fixture["team_b"],
                    "prediction": pick,
                    "actual": actual,
                    "correct": correct,
                    "team_a_seconds": answer.get("team_a_seconds", 0),
                    "team_b_seconds": answer.get("team_b_seconds", 0),
                    "prediction_seconds": elapsed,
                    "group_number": idx // 2 + 1
                }
                save_result(row)
                answer["saved_row"] = row
                st.session_state.phase = "reveal"
                st.rerun()

        elif st.session_state.phase == "reveal":
            answer = st.session_state.answers.get(idx, {})
            row = answer.get("saved_row", {})
            st.subheader("Prediction result")
            st.write(f"Your prediction: **{row.get('prediction', '')}**")
            st.write(f"Actual result: **{fixture['actual_score']}**")
            if row.get("actual"):
                st.success("Correct prediction!" if row.get("correct") else "Incorrect prediction.")
            else:
                st.warning("The actual score could not be read. Check the score in column Q.")
            if st.button("Next fixture"):
                st.session_state.index += 1
                st.session_state.phase = "team_a"
                st.session_state.phase_started = time.time()
                st.rerun()
    else:
        st.success("You've reached the end of the loaded fixtures!")
        if st.button("Start again"):
            st.session_state.index = 0
            st.session_state.phase = "team_a"
            st.session_state.phase_started = time.time()
            st.rerun()

st.divider()
st.header("2. Training dashboard")
results = load_results()

if results.empty:
    st.write("Your training statistics will appear here after your first prediction.")
else:
    results["correct_bool"] = results["correct"].astype(str).str.lower().map({"true": True, "false": False})
    scored = results[results["actual"].fillna("").astype(str) != ""]
    total = len(scored)
    correct_count = int(scored["correct_bool"].fillna(False).sum())
    accuracy = (100 * correct_count / total) if total else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Scored predictions", total)
    c2.metric("Correct predictions", correct_count)
    c3.metric("Single-match accuracy", f"{accuracy:.1f}%")

    if total:
        st.subheader("Recent training results")
        st.dataframe(results.tail(30), use_container_width=True, hide_index=True)

    if len(results) >= 2:
        ordered = results.sort_values("saved_at").reset_index(drop=True)
        groups = []
        for group_number, group in ordered.groupby("group_number"):
            if len(group) == 2:
                known = group["actual"].fillna("").astype(str) != ""
                if known.all():
                    groups.append(bool(group["correct_bool"].fillna(False).all()))
        if groups:
            group_accuracy = 100 * sum(groups) / len(groups)
            c1, c2 = st.columns(2)
            c1.metric("Completed two-match groups", len(groups))
            c2.metric("Both picks correct", f"{group_accuracy:.1f}%")
            longest = current = 0
            for passed in groups:
                if passed:
                    current = 0
                else:
                    current += 1
                    longest = max(longest, current)
            st.metric("Longest consecutive failed groups", longest)
            st.metric("Failed groups in a row (current)", current)

st.caption("Training tool only. Results are for learning and tracking, not a guarantee of betting profits.")
