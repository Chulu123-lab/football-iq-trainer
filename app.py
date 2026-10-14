# Football History Training App
# Streamlit app for Android-friendly browser use.
# Google Sheets connection uses a Google service account for read-only access.
# Training records are stored separately in training_results.csv.

import os, re, time, json
from datetime import datetime
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Football IQ Trainer", page_icon="⚽", layout="centered")

st.markdown("""
<style>
.block-container {max-width: 760px; padding-top: 1rem; padding-bottom: 4rem;}
.match-card {border:1px solid #d9dee7;border-radius:14px;padding:12px 14px;margin:8px 0;background:rgba(120,130,150,.04);}
.teamline {display:flex;justify-content:space-between;gap:12px;font-size:1.02rem;padding:5px 0;}
.smallmuted {color:#737b89;font-size:.85rem;}
.bigtime {font-size:2rem;font-weight:750;letter-spacing:1px;}
</style>
""", unsafe_allow_html=True)

st.title("⚽ Football IQ Trainer")
st.caption("Historical practice • Team A → Team B → Prediction → Reveal")
st.info("This app reads your source sheets and writes training results to a separate CSV. It does not edit your original Google Sheets.")

# ---------- Helpers ----------
def norm(s):
    return re.sub(r"[^a-z0-9]+", "", str(s).strip().lower())

def pick_col(df, options):
    by_norm = {norm(c): c for c in df.columns}
    for opt in options:
        if norm(opt) in by_norm:
            return by_norm[norm(opt)]
    for c in df.columns:
        nc = norm(c)
        if any(norm(o) in nc for o in options):
            return c
    return None

def get_google_client():
    try:
        import gspread
        import google.auth
        creds, _ = google.auth.default(scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ])
        return gspread.authorize(creds)
    except Exception as e:
        st.error("Google Sheets authorization is not ready in this hosting environment. See the setup steps below. " + str(e))
        return None

def sheets_from_client(gc):
    try:
        return gc.openall()
    except Exception as e:
        st.error(f"Could not list Google Sheets: {e}")
        return []

def read_tab(ws):
    rows = ws.get_all_values()
    if not rows:
        return pd.DataFrame()
    # Use first non-empty row as header
    header_idx = next((i for i, r in enumerate(rows[:10]) if any(str(x).strip() for x in r)), 0)
    headers = rows[header_idx]
    data = rows[header_idx+1:]
    width = len(headers)
    headers = [(h.strip() or f"Column_{i+1}") for i,h in enumerate(headers)]
    fixed = []
    for r in data:
        r = (r + [""]*width)[:width]
        if any(str(x).strip() for x in r):
            fixed.append(r)
    return pd.DataFrame(fixed, columns=headers)

def parse_score(v):
    if v is None: return None
    s = str(v).strip()
    if re.fullmatch(r"\d+(?:\.0)?", s):
        return int(float(s))
    return None

def infer_fixtures(df):
    """
    Supports the user's workbook layout:
    A:H = Team A history, I:P = Team B history,
    Q = actual match score/result, R = actual match date.
    Each fixture occupies a 25-row block (e.g. rows 2–26, then 27–51).
    """
    # Preferred exact layout by column position, independent of header wording.
    if len(df.columns) >= 16:
        cols = list(df.columns)
        # The sheet may include Q/R or further columns for target result/date.
        def col_at(idx):
            return cols[idx] if len(cols) > idx else None
        A,B,C,D,E,F,G,H = [col_at(i) for i in range(8)]
        I,J,K,L,M,N,O,P = [col_at(i) for i in range(8,16)]
        Q,R = col_at(16), col_at(17)

        # Identify contiguous 25-row blocks by row position. Each block is a fixture.
        fixtures=[]
        for block_start in range(0, len(df), 25):
            block=df.iloc[block_start:block_start+25]
            if len(block) < 1:
                continue
            first=block.iloc[0]
            team_a=str(first[A]).strip() if A else ""
            team_b=str(first[I]).strip() if I else ""
            if not team_a or not team_b or team_a.lower()=="nan" or team_b.lower()=="nan":
                continue

            def side_history(team_col, opp_col, date_col, result_col, gf_col, ga_col, side_block):
                hist=[]
                for _, row in side_block.iterrows():
                    team=str(row[team_col]).strip()
                    opp=str(row[opp_col]).strip()
                    if not team or not opp or team.lower()=="nan" or opp.lower()=="nan":
                        continue
                    gf=parse_score(row[gf_col]) if gf_col else None
                    ga=parse_score(row[ga_col]) if ga_col else None
                    result=str(row[result_col]).strip().upper() if result_col else ""
                    hist.append({
                        "date":str(row[date_col]).strip() if date_col else "",
                        "home":team,
                        "away":opp,
                        "hg":gf,
                        "ag":ga,
                        "result":result if result in ["W","D","L"] else (
                            "W" if gf is not None and ga is not None and gf>ga else
                            "X" if gf is not None and ga is not None and gf==ga else
                            "L" if gf is not None and ga is not None and gf<ga else ""
                        ),
                        "team_name":team,
                        "opponent":opp,
                        "team_gf":gf,
                        "team_ga":ga,
                        "team_result":result
                    })
                return hist

            hist_a=side_history(A,B,C,D,E,F,block)
            hist_b=side_history(I,J,K,L,M,N,block)

            # The target result/date columns are generally repeated or populated near the first row.
            actual_raw=""
            actual_date=""
            if Q:
                for value in block[Q].tolist():
                    if str(value).strip() and str(value).strip().lower()!="nan":
                        actual_raw=str(value).strip()
                        break
            if R:
                for value in block[R].tolist():
                    if str(value).strip() and str(value).strip().lower()!="nan":
                        actual_date=str(value).strip()
                        break

            actual=""
            score_match=re.search(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$",actual_raw)
            if score_match:
                x,y=int(score_match.group(1)),int(score_match.group(2))
                actual="1" if x>y else ("X" if x==y else "2")
            else:
                v=actual_raw.upper()
                if v in ["1","H","HOME","HOME WIN","W"]: actual="1"
                elif v in ["X","D","DRAW"]: actual="X"
                elif v in ["2","A","AWAY","AWAY WIN","L"]: actual="2"

            fixtures.append({
                "date":actual_date,
                "home":team_a,
                "away":team_b,
                "hg":int(score_match.group(1)) if score_match else None,
                "ag":int(score_match.group(2)) if score_match else None,
                "result":actual,
                "history_a":hist_a,
                "history_b":hist_b,
                "actual_raw":actual_raw,
                "block_start":block_start+2
            })
        return fixtures

    # Fallback for standard one-row-per-fixture tables with named columns.
    home = pick_col(df, ["home team", "team a", "hometeam", "team1", "home"])
    away = pick_col(df, ["away team", "team b", "awayteam", "team2", "away"])
    datec = pick_col(df, ["date", "match date", "fixture date"])
    hg = pick_col(df, ["home goals", "home score", "team a goals", "team1 goals", "hg"])
    ag = pick_col(df, ["away goals", "away score", "team b goals", "team2 goals", "ag"])
    resultc = pick_col(df, ["result", "ft result", "full time result", "outcome"])
    if home and away:
        out=[]
        for _,r in df.iterrows():
            h=str(r[home]).strip(); a=str(r[away]).strip()
            if not h or not a: continue
            hs=parse_score(r[hg]) if hg else None
            as_=parse_score(r[ag]) if ag else None
            res=""
            if hs is not None and as_ is not None:
                res="1" if hs>as_ else ("X" if hs==as_ else "2")
            elif resultc:
                x=str(r[resultc]).strip().upper()
                res="1" if x in ["1","H","HOME","HOME WIN","W"] else ("X" if x in ["X","D","DRAW"] else ("2" if x in ["2","A","AWAY","AWAY WIN","L"] else ""))
            out.append({"date":str(r[datec]).strip() if datec else "", "home":h,"away":a,"hg":hs,"ag":as_,"result":res,"history_a":[],"history_b":[]})
        return out
    return []

def render_history(team, matches):
    st.subheader(team)
    st.caption(f"{len(matches)} historical matches")
    if not matches:
        st.warning("No history found in this 25-row block.")
        return
    for m in matches:
        date=m.get("date","")
        team_name=m.get("team_name",team)
        opponent=m.get("opponent",m.get("away",""))
        gf=m.get("team_gf",m.get("hg"))
        ga=m.get("team_ga",m.get("ag"))
        gf="—" if gf is None else str(gf)
        ga="—" if ga is None else str(ga)
        st.markdown(f"""
        <div class="match-card">
          <div class="teamline"><span>{team_name}</span><b>{gf}</b></div>
          <div class="teamline"><span>{opponent}</span><b>{ga}</b></div>
          <div class="smallmuted">{date}</div>
        </div>""", unsafe_allow_html=True)

def save_result(record):
    path = "training_results.csv"
    row = pd.DataFrame([record])
    if os.path.exists(path):
        row.to_csv(path, mode="a", header=False, index=False)
    else:
        row.to_csv(path, index=False)

# ---------- Data connection ----------
with st.expander("1. Choose your Google Sheets source", expanded=True):
    st.write("For private sheets, run this app in an environment authenticated to your Google account. On a deployed host, configure Google service-account credentials and share the source sheets with that service-account email as Viewer.")
    mode = st.radio("Data source", ["Connect Google Sheets", "Upload CSV/XLSX export"], horizontal=False)
    raw_frames=[]
    if mode == "Connect Google Sheets":
        if st.button("Connect / refresh spreadsheet list", use_container_width=True):
            st.session_state["try_google"] = True
        if st.session_state.get("try_google"):
            gc = get_google_client()
            if gc:
                books = sheets_from_client(gc)
                labels = [f"{b.title}  ·  {b.id}" for b in books]
                if labels:
                    selected = st.selectbox("Select a spreadsheet", labels)
                    book = books[labels.index(selected)]
                    tabs = book.worksheets()
                    tab_labels = [w.title for w in tabs]
                    chosen_tabs = st.multiselect("Select tabs containing match data", tab_labels, default=tab_labels[:1])
                    for tabname in chosen_tabs:
                        ws = next(w for w in tabs if w.title == tabname)
                        frame = read_tab(ws)
                        if not frame.empty:
                            frame["__source_sheet"] = book.title
                            frame["__source_tab"] = tabname
                            raw_frames.append(frame)
                    if st.button("Load selected tab(s)", use_container_width=True):
                        st.session_state["loaded_frames"] = raw_frames
                        st.session_state["source_label"] = selected
                        st.rerun()
                else:
                    st.warning("No spreadsheets were returned for this Google account.")
    else:
        uploaded = st.file_uploader("Upload a CSV or Excel export", type=["csv","xlsx","xls"])
        if uploaded:
            if uploaded.name.lower().endswith(".csv"):
                raw_frames=[pd.read_csv(uploaded, dtype=str).fillna("")]
            else:
                xls=pd.ExcelFile(uploaded)
                chosen=st.multiselect("Choose worksheet tabs", xls.sheet_names, default=xls.sheet_names[:1])
                for tab in chosen:
                    raw_frames.append(pd.read_excel(uploaded, sheet_name=tab, dtype=str).fillna(""))
            if st.button("Load uploaded data", use_container_width=True):
                st.session_state["loaded_frames"] = raw_frames
                st.session_state["source_label"] = uploaded.name
                st.rerun()

# Process loaded frames
frames=st.session_state.get("loaded_frames", [])
if frames:
    all_matches=[]
    for frame in frames:
        all_matches.extend(infer_fixtures(frame))
    # Each 25-row block is one training fixture, with both histories retained.
    seen=set(); unique=[]
    for m in all_matches:
        key=(m.get("block_start"),m.get("home"),m.get("away"),m.get("date"),m.get("actual_raw"))
        if key not in seen:
            seen.add(key); unique.append(m)
    st.success(f"Loaded {len(unique):,} identifiable 25-row fixture blocks from {st.session_state.get('source_label','source')}.")
    if not unique:
        st.warning("The selected tabs do not yet match the automatic column mapper. The current file format uses a row-pair or multi-block layout; we need to map its exact columns before training can start.")
    else:
        valid=[m for m in unique if m.get("result") in ["1","X","2"]]
        candidates=[m for m in unique if m.get("home") and m.get("away")]
        if "queue" not in st.session_state:
            # Reverse chronological fixtures so training proceeds oldest-to-newest, minimizing future-data leakage.
            st.session_state["queue"]=sorted(candidates,key=lambda x:x.get("date",""))
        queue=st.session_state["queue"]
        if not queue:
            st.warning("No fixtures are available.")
        else:
            idx=st.session_state.get("fixture_idx",0)
            idx=min(idx,len(queue)-1)
            fixture=queue[idx]
            st.markdown("---")
            st.caption(f"FIXTURE {idx+1:,} / {len(queue):,}")
            st.header(f"{fixture['home']} vs {fixture['away']}")
            if "phase" not in st.session_state: st.session_state["phase"]="team_a"
            if "team_a_start" not in st.session_state: st.session_state["team_a_start"]=time.time()
            if "team_b_start" not in st.session_state: st.session_state["team_b_start"]=None
            if "pred_start" not in st.session_state: st.session_state["pred_start"]=None
            histories={fixture["home"]:fixture.get("history_a",[]), fixture["away"]:fixture.get("history_b",[])}
            phase=st.session_state["phase"]

            if phase in ["team_a","team_b","prediction"]:
                st_autorefresh(interval=1000, key=f"timer_refresh_{idx}_{phase}")
                default_secs=420 if phase in ["team_a","team_b"] else 60
                key_start={"team_a":"team_a_start","team_b":"team_b_start","prediction":"pred_start"}[phase]
                if st.session_state.get(key_start) is None: st.session_state[key_start]=time.time()
                elapsed=int(time.time()-st.session_state[key_start])
                remaining=max(0,default_secs-elapsed)
                st.markdown(f'<div class="bigtime">{remaining//60:02d}:{remaining%60:02d} remaining</div>',unsafe_allow_html=True)
                if phase=="team_a":
                    render_history(fixture["home"],histories.get(fixture["home"],[]))
                    st.caption("Review the 25 matches. You can move on early when ready.")
                    if remaining==0 or st.button("Next: Team B →",use_container_width=True):
                        st.session_state["phase"]="team_b"; st.session_state["team_b_start"]=time.time(); st.rerun()
                elif phase=="team_b":
                    render_history(fixture["away"],histories.get(fixture["away"],[]))
                    st.caption("Review the 25 matches. You can move on early when ready.")
                    if remaining==0 or st.button("Next: Prediction →",use_container_width=True):
                        st.session_state["phase"]="prediction"; st.session_state["pred_start"]=time.time(); st.rerun()
                else:
                    st.subheader("Make your prediction")
                    st.write(f"**{fixture['home']}** vs **{fixture['away']}**")
                    choice=st.radio("Choose one",["1 — Home win","X — Draw","2 — Away win"],horizontal=False,key=f"pick_{idx}")
                    if st.button("Lock prediction and reveal result",use_container_width=True):
                        pred=choice[0]
                        st.session_state["submitted_prediction"]=pred
                        st.session_state["prediction_elapsed"]=min(60,int(time.time()-st.session_state["pred_start"]))
                        st.session_state["phase"]="reveal"
                        st.rerun()
            elif phase=="reveal":
                pred=st.session_state.get("submitted_prediction","")
                actual=fixture.get("result","")
                st.subheader("Your result")
                st.write(f"Your prediction: **{pred}**")
                st.write(f"Actual result: **{actual or 'Unavailable'}**")
                correct=bool(actual) and pred==actual
                st.metric("Prediction", "CORRECT" if correct else ("INCORRECT" if actual else "UNSCORABLE"))
                rec={
                    "timestamp":datetime.now().isoformat(timespec="seconds"),
                    "fixture_index":idx+1,"date":fixture.get("date",""),
                    "home":fixture["home"],"away":fixture["away"],
                    "prediction":pred,"actual":actual,"correct":int(correct),
                    "team_a_seconds":int(min(420,time.time()-st.session_state.get("team_a_start",time.time()))),
                    "team_b_seconds":int(min(420,time.time()-(st.session_state.get("team_b_start") or time.time()))),
                    "prediction_seconds":st.session_state.get("prediction_elapsed",0),
                    "source":st.session_state.get("source_label",""),
                    "actual_score":fixture.get("actual_raw",""),
                    "source_block_row":fixture.get("block_start",""),
                }
                if not st.session_state.get("saved_current",False):
                    save_result(rec); st.session_state["saved_current"]=True
                if st.button("Next fixture →",use_container_width=True):
                    st.session_state["fixture_idx"]=idx+1
                    st.session_state["phase"]="team_a"
                    st.session_state["team_a_start"]=time.time()
                    st.session_state["team_b_start"]=None
                    st.session_state["pred_start"]=None
                    st.session_state["saved_current"]=False
                    st.session_state.pop("submitted_prediction",None)
                    st.session_state.pop("prediction_elapsed",None)
                    st.rerun()

# ---------- Dashboard ----------
st.markdown("---")
st.header("Training dashboard")
if os.path.exists("training_results.csv"):
    results=pd.read_csv("training_results.csv")
    if not results.empty:
        scorable=results[results["actual"].isin(["1","X","2"])]
        correct=int((scorable["prediction"]==scorable["actual"]).sum())
        total=len(scorable)
        c1,c2=st.columns(2)
        c1.metric("Single-match accuracy",f"{correct/total*100:.1f}%" if total else "—",f"{correct}/{total}" if total else None)
        c2.metric("Fixtures recorded",len(results))
        ta=pd.to_numeric(results["team_a_seconds"],errors="coerce").dropna()
        tb=pd.to_numeric(results["team_b_seconds"],errors="coerce").dropna()
        times=pd.concat([ta,tb])
        st.metric("Average analysis time per team",f"{times.mean)
