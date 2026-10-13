
import streamlit as st
import pandas as pd
import time
import os
from datetime import datetime

st.set_page_config(
    page_title="Football IQ Trainer",
    page_icon="⚽",
    layout="wide"
)

RESULTS_FILE = "training_results.csv"

st.title("⚽ Football IQ Trainer")
st.caption("Train your match analysis, record predictions, and track your results.")

for key, default in {
    "fixtures": [],
    "index": 0,
    "phase": "setup",
    "answers": {},
    "phase_started": time.time(),
    "prepared": False
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


def load_results():
    columns = [
        "saved_at", "fixture", "team_a", "team_b",
        "prediction", "actual", "correct",
        "team_a_seconds", "team_b_seconds",
        "prediction_seconds", "group_number", "worksheet"
    ]
    if os.path.exists(RESULTS_FILE):
        try:
            return pd.read_csv(RESULTS_FILE)
        except Exception:
            pass
    return pd.DataFrame(columns=columns)


def save_result(row):
    exists = os.path.exists(RESULTS_FILE)
    pd.DataFrame([row]).to_csv(
        RESULTS_FILE,
        mode="a",
        header=not exists,
        index=False
    )


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


def clean(value):
    if pd.isna(value):
        return ""
    value = str(value).strip()
    return "" if value.lower() in ("nan", "none") else value


def get_history(sheet, start, team_col):
    rows = []
    for i in range(start, min(start + 25, len(sheet))):
        team = clean(sheet.iloc[i, team_col])
        opponent = clean(sheet.iloc[i, team_col + 1])

        if not team or not opponent:
            continue

        rows.append({
            "Team": team,
            "Opponent": opponent,
            "Date": sheet.iloc[i, team_col + 2],
            "Result": sheet.iloc[i, team_col + 3],
            "GF": sheet.iloc[i, team_col + 4],
            "GA": sheet.iloc[i, team_col + 5],
            "Win Margin": sheet.iloc[i, team_col + 6],
            "Goal Diff": sheet.iloc[i, team_col + 7]
        })
    return rows


def read_workbook(uploaded):
    fixtures = []
    skipped = []

    book = pd.ExcelFile(uploaded)

    for sheet_name in book.sheet_names:
        raw = pd.read_excel(
            book,
            sheet_name=sheet_name,
            header=None
        )

        if raw.shape[1] < 18:
            skipped.append(
                f"{sheet_name}: fewer than 18 columns"
            )
            continue

        sheet_fixtures = 0

        # First row is assumed to contain column headings.
        # Each following fixture occupies 25 rows.
        for start in range(1, len(raw), 25):
            hist_a = get_history(raw, start, 0)
            hist_b = get_history(raw, start, 8)

            if not hist_a or not hist_b:
                continue

            # Ignore blocks that do not contain the expected
            # Team A and Team B histories.
            team_a = hist_a[0]["Team"]
            team_b = hist_b[0]["Team"]

            score = raw.iloc[start, 16]
            date = raw.iloc[start, 17]

            fixtures.append({
                "team_a": team_a,
                "team_b": team_b,
                "history_a": hist_a,
                "history_b": hist_b,
                "actual_score": score,
                "actual_date": date,
                "worksheet": sheet_name
            })
            sheet_fixtures += 1

        if sheet_fixtures == 0:
            skipped.append(
                f"{sheet_name}: no fixture blocks found"
            )

    return fixtures, book.sheet_names, skipped


st.header("1. Load match history")

st.write(
    "Upload one Excel workbook. The app will read all its "
    "worksheets automatically. Your original workbook is not edited."
)

uploaded = st.file_uploader(
    "Upload match history workbook",
    type=["xlsx", "xls"]
)

if uploaded is not None:
    if st.button("Prepare fixtures", type="primary"):
        try:
            with st.spinner("Reading all worksheets..."):
                fixtures, sheet_names, skipped = read_workbook(uploaded)

            if not fixtures:
                st.error(
                    "No fixtures were found. The workbook layout "
                    "may differ from the expected 25-row blocks."
                )
            else:
                st.session_state.fixtures = fixtures
                st.session_state.index = 0
                st.session_state.answers = {}
                st.session_state.phase = "team_a"
                st.session_state.phase_started = time.time()
                st.session_state.prepared = True

                st.success(
                    f"Prepared {len(fixtures)} fixtures from "
                    f"{len(sheet_names)} worksheets."
                )
                st.write("Worksheets found:", ", ".join(sheet_names))

                if skipped:
                    st.warning(
                        "Some worksheets had no usable fixtures:\n\n"
                        + "\n".join(skipped)
                    )

        except Exception as e:
            st.error(f"Could not read the workbook: {e}")


if st.session_state.fixtures:
    fixtures = st.session_state.fixtures
    idx = st.session_state.index

    st.divider()
    st.header("2. Training")

    if idx < len(fixtures):
        fixture = fixtures[idx]

        st.caption(
            f"Worksheet: {fixture['worksheet']} · "
            f"Fixture {idx + 1} of {len(fixtures)}"
        )
        st.subheader(
            f"{fixture['team_a']} vs {fixture['team_b']}"
        )

        def show_history(team_name, history):
            st.markdown(f"### {team_name} — last matches")
            st.dataframe(
                pd.DataFrame(history),
                use_container_width=True,
                hide_index=True
            )

        if st.session_state.phase == "team_a":
            elapsed = int(time.time() - st.session_state.phase_started)
            st.info(
                f"Team A analysis time: {elapsed // 60}:"
                f"{elapsed % 60:02d}"
            )
            show_history(fixture["team_a"], fixture["history_a"])

            if st.button("Next — Team B"):
                st.session_state.answers.setdefault(idx, {})[
                    "team_a_seconds"
                ] = elapsed
                st.session_state.phase = "team_b"
                st.session_state.phase_started = time.time()
                st.rerun()

        elif st.session_state.phase == "team_b":
            elapsed = int(time.time() - st.session_state.phase_started)
            st.info(
                f"Team B analysis time: {elapsed // 60}:"
                f"{elapsed % 60:02d}"
            )
            show_history(fixture["team_b"], fixture["history_b"])

            if st.button("Next — Make prediction"):
                st.session_state.answers.setdefault(idx, {})[
                    "team_b_seconds"
                ] = elapsed
                st.session_state.phase = "predict"
                st.session_state.phase_started = time.time()
                st.rerun()

        elif st.session_state.phase == "predict":
            elapsed = int(time.time() - st.session_state.phase_started)
            st.info(
                f"Prediction time: {elapsed // 60}:"
                f"{elapsed % 60:02d}"
            )

            pick = st.radio(
                "Choose your prediction",
                ["1", "X", "2"],
                format_func=lambda x: {
                    "1": f"1 — {fixture['team_a']} wins",
                    "X": "X — Draw",
                    "2": f"2 — {fixture['team_b']} wins"
                }[x],
                horizontal=True,
                key=f"pick_{idx}"
            )

            if st.button("Reveal actual result"):
                actual = result_to_pick(fixture["actual_score"])
                answer = st.session_state.answers.setdefault(idx, {})
                answer["prediction_seconds"] = elapsed

                row = {
                    "saved_at": datetime.now().isoformat(timespec="seconds"),
                    "fixture": idx + 1,
                    "team_a": fixture["team_a"],
                    "team_b": fixture["team_b"],
                    "prediction": pick,
                    "actual": actual,
                    "correct": pick == actual if actual else "",
                    "team_a_seconds": answer.get("team_a_seconds", 0),
                    "team_b_seconds": answer.get("team_b_seconds", 0),
                    "prediction_seconds": elapsed,
                    "group_number": idx // 2 + 1,
                    "worksheet": fixture["worksheet"]
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
            st.write(f"Actual score: **{fixture['actual_score']}**")

            if row.get("actual"):
                if row.get("correct"):
                    st.success("Correct prediction!")
                else:
                    st.error("Incorrect prediction.")
            else:
                st.warning(
                    "The actual score could not be read. "
                    "Check column Q in the source workbook."
                )

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
st.header("3. Training dashboard")

results = load_results()

if results.empty:
    st.write("Your statistics will appear here after your first prediction.")
else:
    results["correct_bool"] = (
        results["correct"].astype(str).str.lower()
        .map({"true": True, "false": False})
    )

    scored = results[
        results["actual"].fillna("").astype(str) != ""
    ]

    total = len(scored)
    correct_count = int(scored["correct_bool"].fillna(False).sum())
    accuracy = 100 * correct_count / total if total else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Scored predictions", total)
    c2.metric("Correct predictions", correct_count)
    c3.metric("Single-match accuracy", f"{accuracy:.1f}%")

    if total:
        st.subheader("Recent training results")
        st.dataframe(
            results.tail(30),
            use_container_width=True,
            hide_index=True
        )

    if len(results) >= 2:
        ordered = results.sort_values("saved_at")
        groups = []

        for _, group in ordered.groupby("group_number"):
            if len(group) == 2 and (
                group["actual"].fillna("").astype(str) != ""
            ).all():
                groups.append(
                    bool(group["correct_bool"].fillna(False).all())
                )

        if groups:
            group_accuracy = 100 * sum(groups) / len(groups)
            failed_streak = 0
            longest_failed_streak = 0

            for passed in groups:
                if passed:
                    failed_streak = 0
                else:
                    failed_streak += 1
                    longest_failed_streak = max(
                        longest_failed_streak, failed_streak
                    )

            c1, c2 = st.columns(2)
            c1.metric("Completed two-match groups", len(groups))
            c2.metric("Both picks correct", f"{group_accuracy:.1f}%")
            st.metric(
                "Longest consecutive failed groups",
                longest_failed_streak
            )
            st.metric(
                "Failed groups in a row (current)",
                failed_streak
            )

st.caption(
    "Training tool only. Results are for learning and tracking, "
    "not a guarantee of betting profits."
)
