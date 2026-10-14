import streamlit as st
import pandas as pd
import time
import os
import re
import uuid
from datetime import datetime

# ============================================================
# FOOTBALL IQ TRAINER
# ============================================================

st.set_page_config(
    page_title="Football IQ Trainer",
    page_icon="⚽",
    layout="wide"
)

RESULTS_FILE = "training_results.csv"
WORKBOOK_FILE = "match_history_workbook.xlsx"

RESULT_COLUMNS = [
    "saved_at",
    "session_id",
    "fixture",
    "team_a",
    "team_b",
    "prediction",
    "actual",
    "correct",
    "team_a_seconds",
    "team_b_seconds",
    "prediction_seconds",
    "group_number",
    "worksheet"
]

# ============================================================
# SESSION STATE
# ============================================================

defaults = {
    "fixtures": [],
    "index": 0,
    "phase": "setup",
    "answers": {},
    "phase_started": time.time(),
    "prepared": False,
    "session_id": str(uuid.uuid4()),
    "last_saved_fixture": None,
    "training_complete": False
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# RESULTS STORAGE
# ============================================================

def load_results():
    if os.path.exists(RESULTS_FILE):
        try:
            df = pd.read_csv(RESULTS_FILE)

            for column in RESULT_COLUMNS:
                if column not in df.columns:
                    df[column] = None

            return df[RESULT_COLUMNS]

        except Exception:
            pass

    return pd.DataFrame(columns=RESULT_COLUMNS)


def save_result(row):
    existing = load_results()

    new_row = pd.DataFrame([row])

    updated = pd.concat(
        [existing, new_row],
        ignore_index=True
    )

    updated.to_csv(
        RESULTS_FILE,
        index=False
    )


# ============================================================
# RESULT HELPERS
# ============================================================

def clean(value):
    if pd.isna(value):
        return ""

    return str(value).strip()


def result_to_pick(score):
    """
    Convert a score into:
    1 = Team A wins
    X = Draw
    2 = Team B wins
    """

    score = clean(score)

    match = re.match(
        r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$",
        score
    )

    if not match:
        return ""

    goals_a = int(match.group(1))
    goals_b = int(match.group(2))

    if goals_a > goals_b:
        return "1"

    if goals_a == goals_b:
        return "X"

    return "2"


def format_pick(pick):
    names = {
        "1": "Team A Win",
        "X": "Draw",
        "2": "Team B Win"
    }

    return names.get(pick, "Unknown")


def safe_number(value):
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return value


# ============================================================
# MATCH HISTORY READER
# ============================================================

def get_history(sheet, start, team_col):
    """
    Each team's history occupies eight columns.

    Team A: columns A:H
    Team B: columns I:P

    Each fixture contains 25 historical match rows.
    """

    history = []

    column_names = [
        "Team",
        "Opponent",
        "Date",
        "Result",
        "GF",
        "GA",
        "Win Margin",
        "Goal Diff"
    ]

    end = min(
        start + 25,
        len(sheet)
    )

    for row_index in range(start, end):

        row = sheet.iloc[
            row_index,
            team_col:team_col + 8
        ]

        values = [
            clean(value)
            for value in row.tolist()
        ]

        if not values:
            continue

        if not values[0] and not values[1]:
            continue

        if not values[0] and not values[1]:
            continue

        history.append({
            column_names[i]: values[i]
            for i in range(8)
        })

    return history


# ============================================================
# WORKBOOK READER
# ============================================================

def read_workbook(workbook_source):

    excel = pd.ExcelFile(workbook_source)

    fixtures = []
    sheet_names = []
    skipped = []

    for sheet_name in excel.sheet_names:

        try:
            raw = pd.read_excel(
                excel,
                sheet_name=sheet_name,
                header=None
            )

            if raw.shape[1] < 18:
                skipped.append(
                    f"{sheet_name}: fewer than 18 columns"
                )
                continue

            sheet_fixture_count = 0

            # Row 1 is the header.
            # Each fixture block contains 25 history rows.
            #
            # Zero-based starting rows:
            # 1, 26, 51, 76, ...
            #
            # Excel starting rows:
            # 2, 27, 52, 77, ...

            for start in range(1, len(raw), 25):

                team_a_history = get_history(
                    raw,
                    start,
                    0
                )

                team_b_history = get_history(
                    raw,
                    start,
                    8
                )

                if not team_a_history or not team_b_history:
                    continue

                team_a = clean(
                    team_a_history[0].get("Team", "")
                )

                team_b = clean(
                    team_b_history[0].get("Team", "")
                )

                if not team_a or not team_b:
                    continue

                actual_score = ""

                actual_date = ""

                if start < len(raw):

                    actual_score = clean(
                        raw.iloc[start, 16]
                    )

                    actual_date = clean(
                        raw.iloc[start, 17]
                    )

                fixture = {
                    "fixture": len(fixtures) + 1,
                    "worksheet": sheet_name,
                    "team_a": team_a,
                    "team_b": team_b,
                    "team_a_history": team_a_history,
                    "team_b_history": team_b_history,
                    "actual_score": actual_score,
                    "actual_date": actual_date
                }

                fixtures.append(fixture)

                sheet_fixture_count += 1

            if sheet_fixture_count > 0:
                sheet_names.append(sheet_name)
            else:
                skipped.append(
                    f"{sheet_name}: no valid fixtures found"
                )

        except Exception as error:

            skipped.append(
                f"{sheet_name}: {str(error)}"
            )

    return fixtures, sheet_names, skipped


# ============================================================
# RESET TRAINING
# ============================================================

def reset_training():

    st.session_state.fixtures = []
    st.session_state.index = 0
    st.session_state.phase = "setup"
    st.session_state.answers = {}
    st.session_state.phase_started = time.time()
    st.session_state.prepared = False
    st.session_state.last_saved_fixture = None
    st.session_state.training_complete = False
    st.session_state.session_id = str(uuid.uuid4())


# ============================================================
# APPLICATION HEADER
# ============================================================

st.title("⚽ Football IQ Trainer")

st.write(
    "Train your football prediction skills using historical "
    "match data. Review both teams, make a prediction, reveal "
    "the result, and track your accuracy."
)

st.divider()


# ============================================================
# SETUP SCREEN
# ============================================================

if st.session_state.phase == "setup":

    st.header("Load Your Match History")

    st.write(
        "Choose one of the available methods to load your workbook."
    )

    load_method = st.radio(
        "Workbook source",
        [
            "Google Drive link",
            "Upload Excel file"
        ],
        horizontal=True
    )

    if load_method == "Google Drive link":

        st.info(
            "Your Google Drive file must be accessible to the "
            "app through its sharing link."
        )

        drive_link = st.text_input(
            "Google Drive Excel file link",
            placeholder=(
                "https://drive.google.com/file/d/FILE_ID/view"
            ),
            key="drive_link"
        )

        if st.button(
            "Prepare fixtures",
            type="primary",
            key="prepare_drive"
        ):

            if not drive_link.strip():

                st.warning(
                    "Paste your Google Drive file link first."
                )

            else:

                try:

                    import gdown

                    with st.spinner(
                        "Downloading your Excel workbook..."
                    ):

                        downloaded_file = gdown.download(
                            url=drive_link.strip(),
                            output=WORKBOOK_FILE,
                            quiet=False,
                            fuzzy=True
                        )

                    if (
                        not downloaded_file
                        or not os.path.exists(downloaded_file)
                    ):

                        st.error(
                            "The download failed. Check the "
                            "Google Drive link and its sharing settings."
                        )

                    else:

                        with st.spinner(
                            "Reading all worksheets and fixtures..."
                        ):

                            fixtures, sheet_names, skipped = (
                                read_workbook(downloaded_file)
                            )

                        if not fixtures:

                            st.error(
                                "No fixtures were found. Check that "
                                "your workbook follows the expected "
                                "18-column layout and 25-match blocks."
                            )

                        else:

                            st.session_state.fixtures = fixtures
                            st.session_state.index = 0
                            st.session_state.answers = {}
                            st.session_state.phase = "team_a"
                            st.session_state.phase_started = (
                                time.time()
                            )
                            st.session_state.prepared = True
                            st.session_state.training_complete = False
                            st.session_state.last_saved_fixture = None
                            st.session_state.session_id = str(
                                uuid.uuid4()
                            )

                            st.success(
                                f"Loaded {len(fixtures)} fixtures "
                                f"from {len(sheet_names)} worksheets."
                            )

                            if skipped:

                                with st.expander(
                                    "Worksheets skipped or with warnings"
                                ):

                                    for message in skipped:
                                        st.write(message)

                            st.rerun()

                except Exception as error:

                    st.error(
                        f"Could not load the workbook: {error}"
                    )

    else:

        uploaded = st.file_uploader(
            "Upload match history workbook",
            type=["xlsx", "xls"],
            key="excel_upload"
        )

        if st.button(
            "Prepare fixtures",
            type="primary",
            key="prepare_upload"
        ):

            if uploaded is None:

                st.warning(
                    "Choose an Excel workbook first."
                )

            else:

                try:

                    with st.spinner(
                        "Reading all worksheets and fixtures..."
                    ):

                        fixtures, sheet_names, skipped = (
                            read_workbook(uploaded)
                        )

                    if not fixtures:

                        st.error(
                            "No fixtures were found. Check the "
                            "workbook layout."
                        )

                    else:

                        st.session_state.fixtures = fixtures
                        st.session_state.index = 0
                        st.session_state.answers = {}
                        st.session_state.phase = "team_a"
                        st.session_state.phase_started = time.time()
                        st.session_state.prepared = True
                        st.session_state.training_complete = False
                        st.session_state.last_saved_fixture = None
                        st.session_state.session_id = str(uuid.uuid4())

                        st.success(
                            f"Loaded {len(fixtures)} fixtures "
                            f"from {len(sheet_names)} worksheets."
                        )

                        if skipped:

                            with st.expander(
                                "Worksheets skipped or with warnings"
                            ):

                                for message in skipped:
                                    st.write(message)

                        st.rerun()

                except Exception as error:

                    st.error(
                        f"Could not read the workbook: {error}"
                    )


# ============================================================
# TRAINING SCREEN
# ============================================================

elif st.session_state.phase in [
    "team_a",
    "team_b",
    "predict",
    "reveal"
]:

    fixtures = st.session_state.fixtures
    idx = st.session_state.index

    if not fixtures:

        st.warning("No fixtures are loaded.")

        if st.button("Return to setup"):
            reset_training()
            st.rerun()

    elif idx >= len(fixtures):

        st.session_state.phase = "complete"
        st.rerun()

    else:

        fixture = fixtures[idx]

        team_a = fixture["team_a"]
        team_b = fixture["team_b"]

        st.progress(
            (idx + 1) / len(fixtures)
        )

        st.caption(
            f"Fixture {idx + 1} of {len(fixtures)}"
            f"  |  Worksheet: {fixture['worksheet']}"
        )

        st.header(
            f"{team_a} vs {team_b}"
        )

        st.write(
            f"**Match date:** "
            f"{fixture['actual_date'] or 'Not available'}"
        )

        phase = st.session_state.phase

        # ----------------------------------------------------
        # TEAM A HISTORY
        # ----------------------------------------------------

        if phase == "team_a":

            st.subheader(
                f"Team A: {team_a}"
            )

            st.write(
                "Review Team A's historical matches carefully."
            )

            st.dataframe(
                pd.DataFrame(
                    fixture["team_a_history"]
                ),
                use_container_width=True,
                hide_index=True
            )

            if st.button(
                "Continue to Team B",
                type="primary"
            ):

                st.session_state.answers[
                    "team_a_seconds"
                ] = round(
                    time.time()
                    - st.session_state.phase_started,
                    2
                )

                st.session_state.phase = "team_b"
                st.session_state.phase_started = time.time()

                st.rerun()

        # ----------------------------------------------------
        # TEAM B HISTORY
        # ----------------------------------------------------

        elif phase == "team_b":

            st.subheader(
                f"Team B: {team_b}"
            )

            st.write(
                "Review Team B's historical matches carefully."
            )

            st.dataframe(
                pd.DataFrame(
                    fixture["team_b_history"]
                ),
                use_container_width=True,
                hide_index=True
            )

            col1, col2 = st.columns(2)

            with col1:

                if st.button("Back to Team A"):

                    st.session_state.phase = "team_a"
                    st.session_state.phase_started = time.time()

                    st.rerun()

            with col2:

                if st.button(
                    "Make Prediction",
                    type="primary"
                ):

                    st.session_state.answers[
                        "team_b_seconds"
                    ] = round(
                        time.time()
                        - st.session_state.phase_started,
                        2
                    )

                    st.session_state.phase = "predict"
                    st.session_state.phase_started = time.time()

                    st.rerun()

        # ----------------------------------------------------
        # PREDICTION
        # ----------------------------------------------------

        elif phase == "predict":

            st.subheader("Make Your Prediction")

            st.write(
                f"**{team_a}** vs **{team_b}**"
            )

            st.write(
                "Choose the outcome you believe will happen."
            )

            choice = st.radio(
                "Your prediction",
                ["1", "X", "2"],
                format_func=lambda value: {
                    "1": f"1 — {team_a} wins",
                    "X": "X — Draw",
                    "2": f"2 — {team_b} wins"
                }[value],
                key=f"prediction_{idx}"
            )

            st.caption(
                "1 = Home/Team A win | X = Draw | "
                "2 = Away/Team B win"
            )

            if st.button(
                "Lock Prediction",
                type="primary"
            ):

                st.session_state.answers["prediction"] = choice

                st.session_state.answers[
                    "prediction_seconds"
                ] = round(
                    time.time()
                    - st.session_state.phase_started,
                    2
                )

                st.session_state.phase = "reveal"
                st.session_state.phase_started = time.time()

                st.rerun()

        # ----------------------------------------------------
        # REVEAL ACTUAL RESULT
        # ----------------------------------------------------

        elif phase == "reveal":

            st.subheader("Prediction Locked")

            prediction = st.session_state.answers.get(
                "prediction",
                ""
            )

            st.write(
                f"**Your prediction:** {format_pick(prediction)}"
            )

            actual_score = fixture["actual_score"]

            actual_pick = result_to_pick(
                actual_score
            )

                        if actual_score:
                st.write(
                    f"**Actual score:** {actual_score}"
                )

                st.write(
                    f"**Actual result:** {format_pick(actual_pick)}"
                )

                correct = prediction == actual_pick

                if correct:
                    st.success("Correct prediction!")
                else:
                    st.error("Incorrect prediction.")

            else:
                st.warning("No actual score found for this fixture.")
