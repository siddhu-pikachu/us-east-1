import os, csv, math, random, time

from datetime import datetime, timedelta, timezone

from typing import List, Dict, Tuple

import pandas as pd

import numpy as np

DATA_DIR = "data"

TECH_CSV = os.path.join(DATA_DIR, "technicians.csv")

HIST_CSV = os.path.join(DATA_DIR, "history_tickets.csv")

FAIL_CSV = os.path.join(DATA_DIR, "failure_events.csv")

TRAIN_TECH_CSV = os.path.join(DATA_DIR, "train_tech_training.csv")

TRAIN_PDM_CSV  = os.path.join(DATA_DIR, "train_predictive_maint.csv")

RNG = random.Random(42)

np_rng = np.random.default_rng(42)

TYPES = ["recable_port","install_server","swap_psu","reseat_blade","audit_label"]

TAG_POOL = {

  "recable_port":  ["network","cabling","optic"],

  "install_server":["server","install","rails"],

  "swap_psu":      ["server","power","electrical"],

  "reseat_blade":  ["server","repair"],

  "audit_label":   ["inventory","labeling"],

}

PRIOS = ["Low","Medium","High","Critical"]

def load_techs() -> pd.DataFrame:

    df = pd.read_csv(TECH_CSV)

    df["tags"] = df["tags"].fillna("").apply(lambda s: [t.strip().lower() for t in str(s).split(",") if t.strip()])

    df["skill_level"] = pd.to_numeric(df["skill_level"], errors="coerce").fillna(3).astype(int)

    return df

def jaccard(a:List[str], b:List[str])->float:

    A=set(a or []); B=set(b or [])

    return 0.0 if not A and not B else len(A&B)/max(1,len(A|B))

def synth_history(n_days:int=240, avg_tickets_per_day:int=12, reopen_rate_base:float=0.08,

                  write_files:bool=True) -> Tuple[pd.DataFrame,pd.DataFrame]:

    tech_df = load_techs()

    start_date = datetime.now(timezone.utc) - timedelta(days=n_days)

    rows = []

    failure_rows = []

    ticket_id_counter = 1000

    for d in range(n_days):

        day = start_date + timedelta(days=d)

        todays_count = max(1, int(np_rng.poisson(avg_tickets_per_day)))

        for i in range(todays_count):

            ttype = RNG.choice(TYPES)

            prio = RNG.choices(PRIOS, weights=[0.2,0.45,0.25,0.10], k=1)[0]

            tags = TAG_POOL[ttype]

            impact = {"Low":1,"Medium":2,"High":3,"Critical":4}[prio]

            redundancy_risk = RNG.choices([0,1,2], weights=[0.55,0.30,0.15], k=1)[0]  # 2=single-homed

            # Pick a tech probabilistically by tag/skill fit (not too strong)

            weights = []

            for r in tech_df.itertuples():

                sim = jaccard(tags, r.tags)

                skill_need = {"Critical":5,"High":4,"Medium":3,"Low":2}[prio]

                skill_term = max(0.0, (r.skill_level - skill_need + 2) / 4)  # 0..1

                w = 0.4 + 0.9*sim + 0.7*skill_term + RNG.uniform(0,0.2)

                weights.append(max(0.05, w))

            tech_idx = RNG.choices(list(range(len(tech_df))), weights=weights, k=1)[0]

            tech = tech_df.iloc[tech_idx]

            # ETA (minutes) baseline by type + priority compression/expansion

            base = {"recable_port":18, "install_server":40, "swap_psu":22, "reseat_blade":16, "audit_label":10}[ttype]

            pr_adj = {"Critical":-4, "High":-2, "Medium":0, "Low":+2}[prio]

            eta = int(np.clip(np_rng.normal(base+pr_adj, base*0.15), 6, 90))

            # Completion time: log-normal centered around ETA * multipliers by skill/tag fit

            fit = 0.6*jaccard(tags, tech["tags"]) + 0.4*max(0.0, (tech["skill_level"]-3)/2)

            variance = 0.25 - 0.15*min(0.8, fit)  # better fit → less variance

            mu = math.log(max(1.0, eta* (1.08 - 0.10*min(0.9, fit))))  # closer to eta if good fit

            sigma = max(0.18, math.sqrt(max(0.05, variance)))

            completed = float(np_rng.lognormal(mean=mu, sigma=sigma))

            completed = float(np.clip(completed, 4, 240))

            # Did fix work? base + penalties for low fit, high risk

            p_reopen = reopen_rate_base + 0.10*(1.0-min(1.0, fit+0.1)) + 0.08*(redundancy_risk/2) + (0.05 if prio in ["High","Critical"] else 0.0)

            reopened = RNG.random() < min(0.45, max(0.02, p_reopen))

            time_to_reopen_days = 0

            had_followup = 0

            if reopened:

                # 30% immediate (same day), rest geometric over two weeks

                time_to_reopen_days = 0 if RNG.random() < 0.3 else RNG.randint(1, 14)

                had_followup = RNG.random() < 0.3  # escalated/extra work

            ticket_id_counter += 1

            tid = f"HIST-{ticket_id_counter}"

            rows.append({

                "ticket_id": tid,

                "tech": tech["name"],

                "priority": prio,

                "type": ttype,

                "tags": "|".join(tags),

                "created": (day + timedelta(hours=RNG.randint(1,20))).strftime("%Y-%m-%dT%H:%M:%SZ"),

                "completed_minutes": round(completed,1),

                "eta_minutes": eta,

                "overran": int(completed > eta*1.15),

                "had_followup": int(had_followup),

                "reticketed": int(reopened),

                "time_to_reopen_days": time_to_reopen_days,

                "redundancy_risk": redundancy_risk,

                "impact": impact,

                "tech_skill": int(tech["skill_level"]),

                "tech_tags": "|".join(tech["tags"]),

            })

            if reopened:

                failure_rows.append({

                    "ticket_id": tid,

                    "asset_tag": RNG.choice(["srv","sw","pdu","blade","sfp"]) + "-" + str(RNG.randint(1,500)),

                    "failure_tag": RNG.choice(tags),

                    "priority": prio,

                    "type": ttype,

                    "days_to_fail": time_to_reopen_days,

                    "redundancy_risk": redundancy_risk,

                })

    hist_df = pd.DataFrame(rows)

    fail_df = pd.DataFrame(failure_rows)

    if write_files:

        os.makedirs(DATA_DIR, exist_ok=True)

        hist_df.to_csv(HIST_CSV, index=False)

        fail_df.to_csv(FAIL_CSV, index=False)

    return hist_df, fail_df

def build_training_tables(hist_df: pd.DataFrame, fail_df: pd.DataFrame):

    # ---- Model A: tech training flagger ----

    # Aggregate by (tech, task_tag)

    def split_tags(s): return [t for t in str(s).split("|") if t]

    exploded = hist_df.assign(task_tag=hist_df["tags"].apply(split_tags)).explode("task_tag")

    grp = exploded.groupby(["tech","task_tag"]).agg(

        n=("ticket_id","count"),

        rework=("reticketed","mean"),

        overrun=("overran","mean"),

        avg_eta=("eta_minutes","mean"),

        avg_completed=("completed_minutes","mean"),

        risk=("redundancy_risk","mean"),

        avg_priority=("priority", lambda x: x.map({"Low":1,"Medium":2,"High":3,"Critical":4}).mean()),

        tech_skill=("tech_skill","mean")

    ).reset_index()

    # Label: needs_training if rework rate high OR overruns high, with minimum volume

    grp["needs_training"] = ((grp["rework"] > 0.18) | (grp["overrun"] > 0.30)) & (grp["n"] >= 8)

    grp.to_csv(TRAIN_TECH_CSV, index=False)

    # ---- Model B: predictive maintenance ----

    # Binary label: fail soon (<=3 days) vs not (including no reopen)

    fail_df = fail_df.copy()

    if fail_df.empty:

        pd.DataFrame(columns=["feature_placeholder","label"]).to_csv(TRAIN_PDM_CSV, index=False)

        return

    fail_df["label_fail_soon"] = (fail_df["days_to_fail"] <= 3).astype(int)

    # Simple features: failure_tag one-hot, priority, redundancy_risk

    X = pd.get_dummies(fail_df[["failure_tag","priority","redundancy_risk"]], columns=["failure_tag","priority"])

    X["days_to_fail"] = fail_df["days_to_fail"]

    train_pdm = pd.concat([X, fail_df[["label_fail_soon"]]], axis=1)

    train_pdm.to_csv(TRAIN_PDM_CSV, index=False)

