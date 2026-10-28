import streamlit as st
import pandas as pd
import json
import os
import math
from ortools.sat.python import cp_model

st.set_page_config(page_title="Shift Scheduler Pro", layout="wide")
st.title("📋 Αυτόματο Πρόγραμμα Βαρδιών")

DAYS = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]
ROLES = ["Service", "Bar", "Υποδοχή"]
HOURS = list(range(11, 26))  # 11:00 έως 25 (01:00)
DATA_FILE = "scheduler_data.json"

STAFF_NAMES = [
    "Άρης", "Γιάννης", "Κώστας", "Βαγγέλης", "Μαρία",
    "Φωτεινή", "Θεόφιλος", "Σαλώμη", "Ευαγγελία", "Faith", "Ραφαήλ"
]

def format_hour(h):
    if h < 24:
        return f"{h:02d}:00"
    elif h == 24:
        return "00:00"
    else:
        return "01:00"

def parse_hour(h_str):
    if str(h_str) == "01:00":
        return 25
    if str(h_str) == "00:00":
        return 24
    return int(str(h_str).split(":")[0])

# ---------------------------------------------------------
# ΜΟΝΙΜΗ ΑΠΟΘΗΚΕΥΣΗ (JSON)
# ---------------------------------------------------------
def load_persistent_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "employees" in data and "zones" in data:
                    return data["employees"], data["zones"]
        except Exception:
            pass

    default_employees = [
        {
            "id": i + 1,
            "name": name,
            "role": "Service" if i % 3 == 0 else ("Bar" if i % 3 == 1 else "Υποδοχή"),
            "is_marine": True if i in [0, 1, 4, 6] else False,
            "target_shifts": 5,
            "unavailability": {d: {"status": "available", "start": 11, "end": 17} for d in DAYS}
        }
        for i, name in enumerate(STAFF_NAMES)
    ]
    default_zones = [
        {"id": 1, "day": "Όλες", "role": "Service", "start": 11, "end": 18, "min_staff": 1, "require_marine": False},
        {"id": 2, "day": "Όλες", "role": "Service", "start": 18, "end": 25, "min_staff": 2, "require_marine": True},
        {"id": 3, "day": "Όλες", "role": "Bar", "start": 11, "end": 18, "min_staff": 1, "require_marine": False},
        {"id": 4, "day": "Όλες", "role": "Bar", "start": 18, "end": 25, "min_staff": 2, "require_marine": True},
        {"id": 5, "day": "Όλες", "role": "Υποδοχή", "start": 19, "end": 24, "min_staff": 1, "require_marine": False},
    ]
    save_persistent_data(default_employees, default_zones)
    return default_employees, default_zones

def save_persistent_data(employees, zones):
    data = {"employees": employees, "zones": zones}
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if "employees" not in st.session_state or "zones" not in st.session_state:
    loaded_emps, loaded_zones = load_persistent_data()
    st.session_state.employees = loaded_emps
    st.session_state.zones = loaded_zones

if "schedule_df" not in st.session_state:
    st.session_state.schedule_df = None

# ---------------------------------------------------------
# ΑΝΑΛΥΤΙΚΗ ΔΙΑΓΝΩΣΗ ΜΑΘΗΜΑΤΙΚΩΝ ΣΥΓΚΡΟΥΣΕΩΝ
# ---------------------------------------------------------
def run_deep_diagnostics(employees, zones):
    results = {
        "shift_count_conflicts": [],
        "marine_issues": [],
        "staff_shortages": [],
        "min_shift_issues": [],
        "max_hours_issues": [],
        "role_stats": {}
    }

    # 1. Ντετερμινιστικός Έλεγχος Βαρδιών ανά Ημέρα & Ρόλο (Shift Span Check)
    for r in ROLES:
        staff_r = [e for e in employees if e["role"] == r]
        marines_r = [e for e in staff_r if e["is_marine"]]
        
        total_hours_demanded = 0
        min_shifts_needed_week = 0
        marine_shifts_needed_week = 0

        for d in DAYS:
            daily_hours_needed = 0
            closing_staff_needed = 0  # Άτομα που πρέπει να μείνουν μέχρι τη 01:00
            opening_staff_needed = 0  # Άτομα που πρέπει να ανοίξουν στις 11:00
            marine_hours_today = 0

            for h in range(11, 25):
                matching = [z for z in zones if (z["day"] == "Όλες" or z["day"] == d) and z["role"] == r and z["start"] <= h < z["end"]]
                m_staff = max([z["min_staff"] for z in matching], default=0)
                daily_hours_needed += m_staff

                if h == 11:
                    opening_staff_needed = m_staff
                if h == 24:  # 00:00 - 01:00
                    closing_staff_needed = m_staff
                if any(z["require_marine"] for z in matching):
                    marine_hours_today += 1

            total_hours_demanded += daily_hours_needed

            # Υπολογισμός ελάχιστων ατόμων που πρέπει να δουλέψουν σήμερα:
            # Όποιος κλείνει (μέχρι 01:00) μπορεί να ξεκινήσει το νωρίτερο στις 15:00 (10ωρο).
            # Άρα όσα άτομα χρειάζονται πριν τις 15:00 δεν μπορούν να είναι τα ίδια με εκείνα που κλείνουν!
            early_hours_sum = 0
            for h in range(11, 15):
                matching = [z for z in zones if (z["day"] == "Όλες" or z["day"] == d) and z["role"] == r and z["start"] <= h < z["end"]]
                early_hours_sum = max(early_hours_sum, max([z["min_staff"] for z in matching], default=0))

            min_shifts_today = max(
                math.ceil(daily_hours_needed / 10.0),  # Κανένας δεν δουλεύει πάνω από 10 ώρες
                closing_staff_needed + early_hours_sum # Οι πρωινοί + οι κλείνοντες
            )
            min_shifts_needed_week += min_shifts_today

            if marine_hours_today > 0:
                marine_shifts_needed_week += math.ceil(marine_hours_today / 10.0)

        total_shifts_available = sum(e["target_shifts"] for e in staff_r)
        total_marine_shifts_avail = sum(e["target_shifts"] for e in marines_r)

        if min_shifts_needed_week > total_shifts_available:
            results["shift_count_conflicts"].append({
                "role": r,
                "needed": min_shifts_needed_week,
                "available": total_shifts_available,
                "deficit": min_shifts_needed_week - total_shifts_available,
                "staff_count": len(staff_r)
            })

        if marine_shifts_needed_week > total_marine_shifts_avail:
            results["marine_issues"].append({
                "role": r,
                "needed": marine_shifts_needed_week,
                "available": total_marine_shifts_avail,
                "deficit": marine_shifts_needed_week - total_marine_shifts_avail
            })

        results["role_stats"][r] = {
            "staff_count": len(staff_r),
            "marine_count": len(marines_r),
            "hours_demanded": total_hours_demanded,
            "shifts_needed": min_shifts_needed_week,
            "shifts_available": total_shifts_available,
            "marine_shifts_needed": marine_shifts_needed_week,
            "marine_shifts_avail": total_marine_shifts_avail
        }

    return results

tab1, tab2, tab3 = st.tabs(["👤 Καρτέλα Υπαλλήλου", "⚙️ Ρυθμίσεις Manager (Ζώνες)", "📅 Τελικό Πρόγραμμα"])

# ---------------------------------------------------------
# TAB 1: ΚΑΡΤΕΛΑ ΥΠΑΛΛΗΛΟΥ
# ---------------------------------------------------------
with tab1:
    st.subheader("Δήλωση Στοιχείων & Διαθεσιμότητας")
    
    emp_names = [e["name"] for e in st.session_state.employees]
    selected_name = st.selectbox("Επιλέξτε το όνομά σας:", emp_names, key="selected_employee_dropdown")
    emp = next(e for e in st.session_state.employees if e["name"] == selected_name)

    col_role, col_marine, col_shifts = st.columns(3)
    with col_role:
        new_role = st.selectbox("Πόστο εργασίας:", ROLES, index=ROLES.index(emp["role"]), key=f"ui_role_{emp['id']}")
    with col_marine:
        new_marine = st.checkbox("Ναυτολογημένος/η", value=emp["is_marine"], key=f"ui_marine_{emp['id']}")
    with col_shifts:
        new_shifts = st.slider("Επιθυμητά μεροκάματα εβδομάδας:", 1, 7, value=emp["target_shifts"], key=f"ui_shifts_{emp['id']}", help="Ανάθεση: [στόχος - 1] έως [στόχος] ημέρες.")

    st.divider()
    st.markdown("### 📅 Πρόγραμμα Διαθεσιμότητας ανά Ημέρα")

    STATUS_OPTS = ["🟢 Διαθέσιμος/η", "🔴 Όλη μέρα ρεπό", "🟡 Κώλυμα συγκεκριμένες ώρες"]
    status_to_code = {STATUS_OPTS[0]: "available", STATUS_OPTS[1]: "all_day", STATUS_OPTS[2]: "custom"}
    code_to_status = {v: k for k, v in status_to_code.items()}

    for d in DAYS:
        cur_day_data = emp["unavailability"][d]
        cur_status = code_to_status.get(cur_day_data["status"], STATUS_OPTS[0])

        with st.container():
            st.markdown(f"#### 🗓️ {d}")
            col_status, col_hours = st.columns([1.5, 2.5])

            with col_status:
                st.radio(f"Κατάσταση για {d}:", STATUS_OPTS, index=STATUS_OPTS.index(cur_status), key=f"ui_status_{emp['id']}_{d}", label_visibility="collapsed")

            with col_hours:
                cur_chosen_status = st.session_state.get(f"ui_status_{emp['id']}_{d}", cur_status)
                if cur_chosen_status == "🟡 Κώλυμα συγκεκριμένες ώρες":
                    st.select_slider(
                        f"Ώρες κωλύματος ({d}):",
                        options=HOURS,
                        value=(cur_day_data.get("start", 11), cur_day_data.get("end", 17)),
                        format_func=format_hour,
                        key=f"ui_slider_{emp['id']}_{d}"
                    )
                elif cur_chosen_status == "🔴 Όλη μέρα ρεπό":
                    st.info(f"🚫 Ρεπό για την {d}.")
                else:
                    st.success(f"✅ Πλήρως διαθέσιμος/η για εργασία την {d}.")

            st.write("---")

    col_submit, col_reset = st.columns([2, 1])

    with col_submit:
        if st.button("💾 Αποθήκευση Όλων (Submit All)", type="primary", use_container_width=True):
            emp["role"] = new_role
            emp["is_marine"] = new_marine
            emp["target_shifts"] = new_shifts

            for d in DAYS:
                chosen_st = st.session_state.get(f"ui_status_{emp['id']}_{d}", STATUS_OPTS[0])
                code = status_to_code[chosen_st]
                slider_val = st.session_state.get(f"ui_slider_{emp['id']}_{d}", (11, 17))
                emp["unavailability"][d] = {"status": code, "start": slider_val[0], "end": slider_val[1]}

            save_persistent_data(st.session_state.employees, st.session_state.zones)
            st.success(f"🎉 Όλα τα στοιχεία για τον/την **{emp['name']}** αποθηκεύτηκαν μόνιμα!")

    with col_reset:
        if st.button("🗑️ Καθαρισμός Κωλυμάτων (Reset)", use_container_width=True):
            for d in DAYS:
                emp["unavailability"][d] = {"status": "available", "start": 11, "end": 17}
                if f"ui_status_{emp['id']}_{d}" in st.session_state:
                    st.session_state[f"ui_status_{emp['id']}_{d}"] = STATUS_OPTS[0]
                if f"ui_slider_{emp['id']}_{d}" in st.session_state:
                    st.session_state[f"ui_slider_{emp['id']}_{d}"] = (11, 17)

            save_persistent_data(st.session_state.employees, st.session_state.zones)
            st.info(f"Τα κωλύματα του/της {emp['name']} μηδενίστηκαν.")
            st.rerun()

# ---------------------------------------------------------
# TAB 2: ΡΥΘΜΙΣΕΙΣ MANAGER
# ---------------------------------------------------------
with tab2:
    st.subheader("Διαχείριση Ζωνών & Αναγκών Προσωπικού")
    st.info("💡 **Κάντε διπλό κλικ σε οποιοδήποτε κελί** του πίνακα για άμεση αλλαγή.")

    zones_list_data = [
        {
            "ID": z["id"],
            "Ημέρα": z["day"],
            "Πόστο": z["role"],
            "Έναρξη": format_hour(z["start"]),
            "Λήξη": format_hour(z["end"]),
            "Άτομα": z["min_staff"],
            "Ναυτολογημένος": z["require_marine"]
        }
        for z in st.session_state.zones
    ]
    zones_df = pd.DataFrame(zones_list_data)
    time_options = [format_hour(h) for h in HOURS]

    edited_zones_df = st.data_editor(
        zones_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "ID": st.column_config.NumberColumn("ID", disabled=True),
            "Ημέρα": st.column_config.SelectboxColumn("Ημέρα", options=["Όλες"] + DAYS, required=True),
            "Πόστο": st.column_config.SelectboxColumn("Πόστο", options=ROLES, required=True),
            "Έναρξη": st.column_config.SelectboxColumn("Έναρξη", options=time_options[:-1], required=True),
            "Λήξη": st.column_config.SelectboxColumn("Λήξη", options=time_options[1:], required=True),
            "Άτομα": st.column_config.NumberColumn("Άτομα", min_value=1, max_value=10, step=1, required=True),
            "Ναυτολογημένος": st.column_config.CheckboxColumn("Ναυτολογημένος", default=False)
        },
        key="zones_table_editor"
    )

    updated_zones = []
    for idx, row in edited_zones_df.iterrows():
        s_val = parse_hour(str(row["Έναρξη"]))
        e_val = parse_hour(str(row["Λήξη"]))
        if s_val < e_val:
            z_id = int(row["ID"]) if ("ID" in row and pd.notna(row["ID"])) else (idx + 1)
            updated_zones.append({
                "id": z_id,
                "day": str(row["Ημέρα"]),
                "role": str(row["Πόστο"]),
                "start": s_val,
                "end": e_val,
                "min_staff": int(row["Άτομα"]),
                "require_marine": bool(row["Ναυτολογημένος"])
            })

    if updated_zones != st.session_state.zones:
        st.session_state.zones = updated_zones
        save_persistent_data(st.session_state.employees, st.session_state.zones)

    st.write("")
    with st.expander("➕ Προσθήκη Νέας Ζώνης", expanded=False):
        with st.form("add_zone_form"):
            new_day = st.selectbox("Ημέρα:", ["Όλες"] + DAYS)
            new_z_role = st.selectbox("Πόστο:", ROLES)
            new_start, new_end = st.select_slider("Ωράριο Ζώνης:", options=HOURS, value=(18, 25), format_func=format_hour)
            new_min_staff = st.number_input("Ελάχιστα απαιτούμενα άτομα:", min_value=1, max_value=10, value=2)
            new_require_marine = st.checkbox("Απαιτείται τουλάχιστον 1 ναυτολογημένος")
            
            if st.form_submit_button("Αποθήκευση Νέας Ζώνης"):
                new_id = max([z["id"] for z in st.session_state.zones], default=0) + 1
                st.session_state.zones.append({
                    "id": new_id,
                    "day": new_day,
                    "role": new_z_role,
                    "start": new_start,
                    "end": new_end,
                    "min_staff": new_min_staff,
                    "require_marine": new_require_marine
                })
                save_persistent_data(st.session_state.employees, st.session_state.zones)
                if "zones_table_editor" in st.session_state:
                    del st.session_state["zones_table_editor"]
                st.success("Η ζώνη προστέθηκε και αποθηκεύτηκε επιτυχώς!")
                st.rerun()

# ---------------------------------------------------------
# TAB 3: ΕΠΙΛΥΣΗ ΜΕ ΑΠΟΛΥΤΗ ΔΙΑΓΝΩΣΗ
# ---------------------------------------------------------
with tab3:
    st.subheader("Αυτόματη Δημιουργία & Επεξεργασία Προγράμματος")

    if st.button("🚀 Υπολογισμός Προγράμματος (OR-Tools)", type="primary"):
        model = cp_model.CpModel()
        
        x = {}
        for e in st.session_state.employees:
            for d in DAYS:
                for h in range(11, 25):
                    x[(e["id"], d, h)] = model.NewBoolVar(f"x_{e['id']}_{d}_{h}")

        works_day = {}
        for e in st.session_state.employees:
            for d in DAYS:
                works_day[(e["id"], d)] = model.NewBoolVar(f"works_{e['id']}_{d}")
                hours_worked = [x[(e["id"], d, h)] for h in range(11, 25)]
                model.Add(sum(hours_worked) >= 1).OnlyEnforceIf(works_day[(e["id"], d)])
                model.Add(sum(hours_worked) == 0).OnlyEnforceIf(works_day[(e["id"], d)].Not())

            available_days_count = sum(1 for d in DAYS if e["unavailability"][d]["status"] != "all_day")
            effective_max = min(e["target_shifts"], available_days_count)
            effective_min = max(0, min(e["target_shifts"] - 1, available_days_count))

            total_days_worked = sum(works_day[(e["id"], d)] for d in DAYS)
            model.Add(total_days_worked >= effective_min)
            model.Add(total_days_worked <= effective_max)

            for d, u_info in e["unavailability"].items():
                if u_info["status"] == "all_day":
                    for h in range(11, 25):
                        model.Add(x[(e["id"], d, h)] == 0)
                elif u_info["status"] == "custom":
                    for h in range(u_info["start"], u_info["end"]):
                        if h in range(11, 25):
                            model.Add(x[(e["id"], d, h)] == 0)

            for d in DAYS:
                daily_h = [x[(e["id"], d, h)] for h in range(11, 25)]
                model.Add(sum(daily_h) <= 10)
                model.Add(sum(daily_h) >= 5).OnlyEnforceIf(works_day[(e["id"], d)])

                starts = []
                for i, h in enumerate(range(11, 25)):
                    start_var = model.NewBoolVar(f"start_{e['id']}_{d}_{h}")
                    if i == 0:
                        model.Add(start_var == x[(e["id"], d, h)])
                    else:
                        model.Add(start_var >= x[(e["id"], d, h)] - x[(e["id"], d, h - 1)])
                    starts.append(start_var)
                model.Add(sum(starts) <= 1)

        for zone in st.session_state.zones:
            target_days = DAYS if zone["day"] == "Όλες" else [zone["day"]]
            eligible_staff = [e for e in st.session_state.employees if e["role"] == zone["role"]]
            marine_staff = [e for e in eligible_staff if e["is_marine"]]

            for d in target_days:
                for h in range(zone["start"], zone["end"]):
                    staff_h = [x[(e["id"], d, h)] for e in eligible_staff]
                    model.Add(sum(staff_h) >= zone["min_staff"])

                    if zone["require_marine"]:
                        marine_h = [x[(e["id"], d, h)] for e in marine_staff]
                        model.Add(sum(marine_h) >= 1)

        total_hours_sum = sum(x[(e["id"], d, h)] for e in st.session_state.employees for d in DAYS for h in range(11, 25))
        model.Minimize(total_hours_sum)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10.0
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            st.success("🎉 Το πρόγραμμα υπολογίστηκε επιτυχώς με όλους τους περιορισμούς!")
            
            results = []
            for d in DAYS:
                for e in st.session_state.employees:
                    worked = [h for h in range(11, 25) if solver.Value(x[(e["id"], d, h)]) == 1]
                    if worked:
                        start_h = min(worked)
                        end_h = max(worked) + 1
                        results.append({
                            "Ημέρα": d,
                            "Εργαζόμενος": e["name"],
                            "Πόστο": e["role"],
                            "Ναυτολογημένος": "Ναι" if e["is_marine"] else "Όχι",
                            "Έναρξη": format_hour(start_h),
                            "Λήξη": format_hour(end_h),
                            "Σύνολο Ωρών": len(worked)
                        })

            st.session_state.schedule_df = pd.DataFrame(results)
        else:
            st.session_state.schedule_df = None
            st.error("❌ Αδύνατη η εύρεση λύσης! Εντοπίστηκε ακριβώς ποιος περιορισμός χτυπάει:")

            diag = run_deep_diagnostics(st.session_state.employees, st.session_state.zones)

            # 1. ΠΡΟΒΟΛΗ ΣΥΓΚΡΟΥΣΗΣ ΜΕΡΟΚΑΜΑΤΩΝ (Η ΒΑΣΙΚΗ ΑΙΤΙΑ)
            if diag["shift_count_conflicts"]:
                st.error("### 🚨 1. Έλλειψη Διαθέσιμων Μεροκάματων (ΕΔΩ ΧΤΥΠΑΕΙ!)")
                for conf in diag["shift_count_conflicts"]:
                    st.markdown(f"#### Πόστο: **{conf['role']}**")
                    st.write(
                        f"• **Απαιτούμενες Βάρδιες Εβδομάδας:** `{conf['needed']} βάρδιες` (χρειάζονται τουλάχιστον 3 άτομα κάθε μέρα για να καλυφθεί το 11:00-01:00 με όριο 10ωρου).\n\n"
                        f"• **Διαθέσιμες Βάρδιες Προσωπικού:** `{conf['available']} βάρδιες` (τα {conf['staff_count']} άτομα προσφέρουν συνολικά {conf['available']} μεροκάματα).\n\n"
                        f"👉 **Λείπουν ακριβώς `{conf['deficit']}` μεροκάματα!**"
                    )
                    st.info(f"💡 **Άμεση λύση:** Αυξήστε τα επιθυμητά μεροκάματα ενός ή δύο υπαλλήλων στο {conf['role']} (π.χ. από 5 σε 6), ή προσθέστε ένα άτομο στο πόστο.")

            # 2. ΠΡΟΒΟΛΗ ΝΑΥΤΟΛΟΓΗΜΕΝΩΝ
            if diag["marine_issues"]:
                st.warning("### ⚓ 2. Έλλειψη Ναυτολογημένων Βαρδιών")
                for m in diag["marine_issues"]:
                    st.write(f"Στο πόστο **{m['role']}** απαιτούνται **{m['needed']}** ναυτολογημένες βάρδιες, αλλά οι ναυτολογημένοι καλύπτουν μόνο **{m['available']}**.")

            # 3. ΠΙΝΑΚΑΣ
            st.markdown("### 📊 Συγκεντρωτικός Πίνακας Ανάλυσης")
            stats_table = []
            for r, s in diag["role_stats"].items():
                stats_table.append({
                    "Πόστο": r,
                    "Προσωπικό": f"{s['staff_count']} άτομα ({s['marine_count']} ναυτ.)",
                    "Ώρες Ζήτησης": f"{s['hours_demanded']} ώρες",
                    "Απαιτούμενα Μεροκάματα": f"{s['shifts_needed']} βάρδιες",
                    "Διαθέσιμα Μεροκάματα": f"{s['shifts_available']} βάρδιες",
                    "Κατάσταση": "❌ Λείπει μεροκάματο" if s["shifts_needed"] > s["shifts_available"] else "✅ Εντάξει"
                })
            st.dataframe(pd.DataFrame(stats_table), use_container_width=True, hide_index=True)

    # ---------------------------------------------------------
    # EDITABLE TABLE & LIVE PREVIEW
    # ---------------------------------------------------------
    if st.session_state.schedule_df is not None:
        st.divider()
        st.markdown("### ✏️ Ζωντανή Επεξεργασία Προγράμματος (Live Editor)")
        st.info("💡 Κάντε διπλό κλικ σε οποιοδήποτε κελί για να αλλάξετε βάρδιες ή ώρες.")

        time_options = [format_hour(h) for h in HOURS]
        edited_df = st.data_editor(
            st.session_state.schedule_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Ημέρα": st.column_config.SelectboxColumn("Ημέρα", options=DAYS, required=True),
                "Εργαζόμενος": st.column_config.SelectboxColumn("Εργαζόμενος", options=STAFF_NAMES, required=True),
                "Πόστο": st.column_config.SelectboxColumn("Πόστο", options=ROLES, required=True),
                "Ναυτολογημένος": st.column_config.SelectboxColumn("Ναυτολογημένος", options=["Ναι", "Όχι"]),
                "Έναρξη": st.column_config.SelectboxColumn("Έναρξη", options=time_options, required=True),
                "Λήξη": st.column_config.SelectboxColumn("Λήξη", options=time_options, required=True),
                "Σύνολο Ωρών": st.column_config.NumberColumn("Σύνολο Ωρών", min_value=5, max_value=10, step=1)
            },
            key="final_schedule_editor"
        )
        st.session_state.schedule_df = edited_df

        st.markdown("#### 📊 Σύνοψη Μεροκάματων Προγράμματος")
        shift_counts = edited_df["Εργαζόμενος"].value_counts().reset_index()
        shift_counts.columns = ["Εργαζόμενος", "Μεροκάματα στο Πρόγραμμα"]
        
        target_dict = {e["name"]: f"{max(0, e['target_shifts']-1)} έως {e['target_shifts']}" for e in st.session_state.employees}
        shift_counts["Επιθυμητός Στόχος"] = shift_counts["Εργαζόμενος"].map(target_dict)
        st.dataframe(shift_counts, use_container_width=True, hide_index=True)

        csv_data = edited_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 Λήψη Προγράμματος σε Excel / CSV",
            data=csv_data,
            file_name="programma_vardion.csv",
            mime="text/csv"
        )

        st.markdown("#### 📅 Αναλυτική Προβολή ανά Ημέρα")
        for d in DAYS:
            day_df = edited_df[edited_df["Ημέρα"] == d]
            if not day_df.empty:
                with st.expander(f"📅 {d} ({len(day_df)} βάρδιες)", expanded=False):
                    st.dataframe(day_df[["Εργαζόμενος", "Πόστο", "Ναυτολογημένος", "Έναρξη", "Λήξη", "Σύνολο Ωρών"]], use_container_width=True, hide_index=True)