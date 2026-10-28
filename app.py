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

DEFAULT_STAFF = [
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
        for i, name in enumerate(DEFAULT_STAFF)
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
# ΠΛΗΡΕΣ ΣΥΣΤΗΜΑ ΔΙΑΓΝΩΣΗΣ ΚΑΘΕ ΠΙΘΑΝΟΥ ΑΙΤΙΟΥ
# ---------------------------------------------------------
def run_deep_diagnostics(employees, zones):
    results = {
        "shift_count_conflicts": [],
        "zero_slack_conflicts": [],
        "marine_issues": [],
        "unavail_conflicts": [],
        "staff_shortages": [],
        "min_shift_issues": [],
        "role_stats": {}
    }

    # 1. Μαθηματικός Έλεγχος Βαρδιών & Ισοζυγίου
    for r in ROLES:
        staff_r = [e for e in employees if e["role"] == r]
        marines_r = [e for e in staff_r if e["is_marine"]]
        
        total_hours_demanded = 0
        min_shifts_needed_week = 0
        marine_shifts_needed_week = 0

        for d in DAYS:
            daily_hours_needed = 0
            closing_staff_needed = 0
            early_hours_sum = 0
            marine_hours_today = 0

            for h in range(11, 25):
                matching = [z for z in zones if (z["day"] == "Όλες" or z["day"] == d) and z["role"] == r and z["start"] <= h < z["end"]]
                m_staff = max([z["min_staff"] for z in matching], default=0)
                daily_hours_needed += m_staff

                if h == 24:  # 00:00 - 01:00
                    closing_staff_needed = m_staff
                if any(z["require_marine"] for z in matching):
                    marine_hours_today += 1

            total_hours_demanded += daily_hours_needed

            for h in range(11, 15):
                matching = [z for z in zones if (z["day"] == "Όλες" or z["day"] == d) and z["role"] == r and z["start"] <= h < z["end"]]
                early_hours_sum = max(early_hours_sum, max([z["min_staff"] for z in matching], default=0))

            min_shifts_today = max(
                math.ceil(daily_hours_needed / 10.0),
                closing_staff_needed + early_hours_sum
            )
            min_shifts_needed_week += min_shifts_today

            if marine_hours_today > 0:
                marine_shifts_needed_week += math.ceil(marine_hours_today / 10.0)

        total_shifts_available = sum(e["target_shifts"] for e in staff_r)
        total_marine_shifts_avail = sum(e["target_shifts"] for e in marines_r)

        # Έλλειψη βαρδιών
        if min_shifts_needed_week > total_shifts_available:
            results["shift_count_conflicts"].append({
                "role": r,
                "needed": min_shifts_needed_week,
                "available": total_shifts_available,
                "deficit": min_shifts_needed_week - total_shifts_available,
                "staff_count": len(staff_r)
            })
        # Οριακό ισοζύγιο (Zero Slack)
        elif min_shifts_needed_week == total_shifts_available and total_shifts_available > 0:
            results["zero_slack_conflicts"].append({
                "role": r,
                "shifts": min_shifts_needed_week,
                "staff_count": len(staff_r)
            })

        # Έλλειψη ναυτολογημένων
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

    # 2. Relaxed Optimization Solver για ανίχνευση κωλυμάτων και ωριαίων bottlenecks
    diag_model = cp_model.CpModel()
    x = {}
    for e in employees:
        for d in DAYS:
            for h in range(11, 25):
                x[(e["id"], d, h)] = diag_model.NewBoolVar(f"dx_{e['id']}_{d}_{h}")

    works_day = {}
    for e in employees:
        for d in DAYS:
            works_day[(e["id"], d)] = diag_model.NewBoolVar(f"dw_{e['id']}_{d}")
            hours_worked = [x[(e["id"], d, h)] for h in range(11, 25)]
            diag_model.Add(sum(hours_worked) >= 1).OnlyEnforceIf(works_day[(e["id"], d)])
            diag_model.Add(sum(hours_worked) == 0).OnlyEnforceIf(works_day[(e["id"], d)].Not())

    penalties = []
    slack_unavail = {}
    for e in employees:
        for d, u_info in e["unavailability"].items():
            if u_info["status"] == "all_day":
                for h in range(11, 25):
                    s = diag_model.NewBoolVar(f"su_{e['id']}_{d}_{h}")
                    diag_model.Add(x[(e["id"], d, h)] <= s)
                    penalties.append(s * 1000)
                    slack_unavail[(e["id"], d, h)] = s
            elif u_info["status"] == "custom":
                for h in range(u_info["start"], u_info["end"]):
                    if h in range(11, 25):
                        s = diag_model.NewBoolVar(f"su_{e['id']}_{d}_{h}")
                        diag_model.Add(x[(e["id"], d, h)] <= s)
                        penalties.append(s * 1000)
                        slack_unavail[(e["id"], d, h)] = s

    slack_staff = {}
    for z in zones:
        target_days = DAYS if z["day"] == "Όλες" else [z["day"]]
        eligible = [e for e in employees if e["role"] == z["role"]]
        for d in target_days:
            for h in range(z["start"], z["end"]):
                s_st = diag_model.NewIntVar(0, 10, f"sst_{z['id']}_{d}_{h}")
                diag_model.Add(sum(x[(e["id"], d, h)] for e in eligible) + s_st >= z["min_staff"])
                penalties.append(s_st * 2000)
                slack_staff[(z["id"], d, h)] = s_st

    diag_model.Minimize(sum(penalties))
    diag_solver = cp_model.CpSolver()
    diag_solver.parameters.max_time_in_seconds = 5.0
    d_status = diag_solver.Solve(diag_model)

    if d_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for (e_id, d, h), var in slack_unavail.items():
            if diag_solver.Value(var) > 0:
                emp = next(e for e in employees if e["id"] == e_id)
                results["unavail_conflicts"].append({"name": emp["name"], "role": emp["role"], "day": d, "hour": h})

        for (z_id, d, h), var in slack_staff.items():
            val = diag_solver.Value(var)
            if val > 0:
                zone = next(z for z in zones if z["id"] == z_id)
                results["staff_shortages"].append({"day": d, "hour": h, "role": zone["role"], "missing": val})

    return results

tab1, tab2, tab3 = st.tabs(["👤 Καρτέλα Υπαλλήλου", "⚙️ Ρυθμίσεις Manager (Ζώνες)", "📅 Τελικό Πρόγραμμα"])

# ---------------------------------------------------------
# TAB 1: ΚΑΡΤΕΛΑ ΥΠΑΛΛΗΛΟΥ (ΜΕ ΠΡΟΣΘΗΚΗ / ΔΙΑΓΡΑΦΗ)
# ---------------------------------------------------------
with tab1:
    st.subheader("Δήλωση Στοιχείων & Διαθεσιμότητας")

    # ΕΝΟΤΗΤΑ: ΠΡΟΣΘΗΚΗ / ΔΙΑΓΡΑΦΗ ΥΠΑΛΛΗΛΩΝ
    with st.expander("👥 Διαχείριση Προσωπικού (Προσθήκη / Διαγραφή Υπαλλήλου)", expanded=False):
        c_add_emp, c_del_emp = st.columns(2)
        
        with c_add_emp:
            st.markdown("##### ➕ Προσθήκη Νέου Υπαλλήλου")
            with st.form("add_employee_form"):
                new_emp_name = st.text_input("Ονοματεπώνυμο:")
                new_emp_role = st.selectbox("Πόστο:", ROLES, key="new_emp_role")
                new_emp_marine = st.checkbox("Ναυτολογημένος/η", key="new_emp_marine")
                new_emp_shifts = st.slider("Επιθυμητά μεροκάματα:", 1, 7, 5, key="new_emp_shifts")
                
                if st.form_submit_button("Αποθήκευση Υπαλλήλου"):
                    if not new_emp_name.strip():
                        st.error("Παρακαλώ εισάγετε όνομα.")
                    elif any(e["name"].lower() == new_emp_name.strip().lower() for e in st.session_state.employees):
                        st.error("Υπάρχει ήδη υπάλληλος με αυτό το όνομα.")
                    else:
                        new_id = max([e["id"] for e in st.session_state.employees], default=0) + 1
                        st.session_state.employees.append({
                            "id": new_id,
                            "name": new_emp_name.strip(),
                            "role": new_emp_role,
                            "is_marine": new_emp_marine,
                            "target_shifts": new_emp_shifts,
                            "unavailability": {d: {"status": "available", "start": 11, "end": 17} for d in DAYS}
                        })
                        save_persistent_data(st.session_state.employees, st.session_state.zones)
                        st.success(f"Ο/Η {new_emp_name} προστέθηκε επιτυχώς!")
                        st.rerun()

        with c_del_emp:
            st.markdown("##### 🗑️ Διαγραφή Υπαλλήλου")
            if st.session_state.employees:
                emp_to_del_name = st.selectbox("Επιλέξτε υπάλληλο προς διαγραφή:", [e["name"] for e in st.session_state.employees], key="emp_del_select")
                if st.button("❌ Οριστική Διαγραφή", type="secondary"):
                    st.session_state.employees = [e for e in st.session_state.employees if e["name"] != emp_to_del_name]
                    save_persistent_data(st.session_state.employees, st.session_state.zones)
                    st.success(f"Ο/Η {emp_to_del_name} διαγράφηκε!")
                    st.rerun()

    st.divider()

    if not st.session_state.employees:
        st.warning("Δεν υπάρχουν καταχωρημένοι υπάλληλοι. Προσθέστε παραπάνω.")
        st.stop()

    emp_names = [e["name"] for e in st.session_state.employees]
    selected_name = st.selectbox("Επιλέξτε το όνομά σας:", emp_names, key="selected_employee_dropdown")
    emp = next(e for e in st.session_state.employees if e["name"] == selected_name)

    # Σύντομη επισκόπηση διαθεσιμότητας επάνω
    st.markdown("#### ⚡ Σύντομη Επισκόπηση Εβδομάδας")
    quick_summary_dict = {}
    for d in DAYS:
        u_info = emp["unavailability"][d]
        if u_info["status"] == "all_day":
            quick_summary_dict[d] = "🔴 Ρεπό"
        elif u_info["status"] == "custom":
            quick_summary_dict[d] = f"🟡 {format_hour(u_info['start'])}-{format_hour(u_info['end'])}"
        else:
            quick_summary_dict[d] = "🟢 Διαθέσιμος"
    st.dataframe(pd.DataFrame([quick_summary_dict]), use_container_width=True, hide_index=True)

    col_role, col_marine, col_shifts = st.columns(3)
    with col_role:
        new_role = st.selectbox("Πόστο εργασίας:", ROLES, index=ROLES.index(emp["role"]), key=f"ui_role_{emp['id']}")
    with col_marine:
        new_marine = st.checkbox("Ναυτολογημένος/η", value=emp["is_marine"], key=f"ui_marine_{emp['id']}")
    with col_shifts:
        new_shifts = st.slider("Επιθυμητά μεροκάματα εβδομάδας:", 1, 7, value=emp["target_shifts"], key=f"ui_shifts_{emp['id']}", help="Ανάθεση: [στόχος - 1] έως [στόχος] ημέρες.")

    st.divider()
    st.markdown("### 📅 Αναλυτική Ρύθμιση ανά Ημέρα")

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
            st.rerun()

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
# TAB 2: ΡΥΘΜΙΣΕΙΣ MANAGER (ΖΩΝΕΣ)
# ---------------------------------------------------------
with tab2:
    st.subheader("Διαχείριση Ζωνών & Αναγκών Προσωπικού")
    st.caption("Επεξεργαστείτε τις ζώνες στον πίνακα ή χρησιμοποιήστε τα εργαλεία προσθήκης και διαγραφής παρακάτω.")

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
    col_add, col_del = st.columns(2)

    with col_add:
        with st.expander("➕ Προσθήκη Νέας Ζώνης (Πολλαπλές Ημέρες)", expanded=False):
            with st.form("add_zone_form"):
                chosen_days = st.multiselect(
                    "Ημέρες εφαρμογής:",
                    options=["Όλες"] + DAYS,
                    default=["Όλες"]
                )
                new_z_role = st.selectbox("Πόστο:", ROLES)
                new_start, new_end = st.select_slider("Ωράριο Ζώνης:", options=HOURS, value=(18, 25), format_func=format_hour)
                new_min_staff = st.number_input("Ελάχιστα απαιτούμενα άτομα:", min_value=1, max_value=10, value=2)
                new_require_marine = st.checkbox("Απαιτείται τουλάχιστον 1 ναυτολογημένος")
                
                if st.form_submit_button("Αποθήκευση Νέας Ζώνης"):
                    if not chosen_days:
                        st.error("Παρακαλώ επιλέξτε τουλάχιστον μία ημέρα ή 'Όλες'.")
                    else:
                        max_id = max([z["id"] for z in st.session_state.zones], default=0)
                        days_to_apply = ["Όλες"] if "Όλες" in chosen_days else chosen_days

                        for d in days_to_apply:
                            max_id += 1
                            st.session_state.zones.append({
                                "id": max_id,
                                "day": d,
                                "role": new_z_role,
                                "start": new_start,
                                "end": new_end,
                                "min_staff": new_min_staff,
                                "require_marine": new_require_marine
                            })

                        save_persistent_data(st.session_state.employees, st.session_state.zones)
                        if "zones_table_editor" in st.session_state:
                            del st.session_state["zones_table_editor"]
                        st.success(f"Προστέθηκαν επιτυχώς {len(days_to_apply)} ζώνες!")
                        st.rerun()

    with col_del:
        with st.expander("🗑️ Άμεση Διαγραφή Ζώνης", expanded=False):
            if st.session_state.zones:
                zone_options_map = {
                    z["id"]: f"ID {z['id']} | {z['day']} | {z['role']} | {format_hour(z['start'])}-{format_hour(z['end'])} ({z['min_staff']} άτομα)"
                    for z in st.session_state.zones
                }
                zone_to_delete = st.selectbox(
                    "Επιλέξτε τη ζώνη προς διαγραφή:",
                    options=list(zone_options_map.keys()),
                    format_func=lambda x: zone_options_map[x]
                )
                
                if st.button("❌ Οριστική Διαγραφή Ζώνης", type="secondary"):
                    st.session_state.zones = [z for z in st.session_state.zones if z["id"] != zone_to_delete]
                    save_persistent_data(st.session_state.employees, st.session_state.zones)
                    if "zones_table_editor" in st.session_state:
                        del st.session_state["zones_table_editor"]
                    st.success("Η ζώνη διαγράφηκε επιτυχώς!")
                    st.rerun()

# ---------------------------------------------------------
# TAB 3: ΕΠΙΛΥΣΗ ΜΕ ΠΛΗΡΗ ΑΙΤΙΟΛΟΓΗΣΗ
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
            st.error("❌ Αδύνατη η εύρεση λύσης! Δείτε παρακάτω ακριβώς τι μπλοκάρει τον αλγόριθμο:")

            diag = run_deep_diagnostics(st.session_state.employees, st.session_state.zones)

            # ΑΙΤΙΑ 1: ΕΛΛΕΙΨΗ ΜΕΡΟΚΑΜΑΤΩΝ
            if diag["shift_count_conflicts"]:
                st.error("### 🚨 1. Έλλειψη Διαθέσιμων Μεροκάματων (Απόλυτη Αδυναμία)")
                for conf in diag["shift_count_conflicts"]:
                    st.write(
                        f"Στο πόστο **{conf['role']}** απαιτούνται **{conf['needed']}** βάρδιες την εβδομάδα, "
                        f"αλλά τα {conf['staff_count']} άτομα προσφέρουν συνολικά μόνο **{conf['available']}** μεροκάματα.\n\n"
                        f"👉 **Λείπουν τουλάχιστον {conf['deficit']} μεροκάματα!**"
                    )

            # ΑΙΤΙΑ 2: ΟΡΙΑΚΟ ΙΣΟΖΥΓΙΟ (ZERO SLACK)
            if diag["zero_slack_conflicts"]:
                st.warning("### ⚠️ 2. Οριακό Ισοζύγιο Προσωπικού (Μηδενική Ευελιξία)")
                for zc in diag["zero_slack_conflicts"]:
                    st.markdown(f"#### Πόστο: **{zc['role']}**")
                    st.write(
                        f"• **Απαιτούμενες Βάρδιες:** `{zc['shifts']}` | **Διαθέσιμες Βάρδιες:** `{zc['shifts']}`\n\n"
                        f"⚠️ **Γιατί μπλοκάρει:** Τα διαθέσιμα μεροκάματα είναι **ακριβώς ίσα** με τις απαιτήσεις! "
                        f"Αυτό σημαίνει ότι όλοι οι υπάλληλοι πρέπει να δουλέψουν στο 100% των επιθυμητών ημερών τους. "
                        f"Αν έστω και ένας υπάλληλος έχει δηλώσει κώλυμα ή ρεπό μια συγκεκριμένη ημέρα, **δεν υπάρχει κανένας εφεδρικός** να τον αντικαταστήσει χωρίς να παραβιαστεί το όριο μεροκάματων!"
                    )
                    st.info(f"💡 **Άμεση Λύση για το {zc['role']}:** Αυξήστε τα επιθυμητά μεροκάματα σε 1-2 άτομα (π.χ. από 5 σε 6) ή προσθέστε ακόμα 1 άτομο στο πόστο για να αποκτήσει ευελιξία ο αλγόριθμος.")

            # ΑΙΤΙΑ 3: ΝΑΥΤΟΛΟΓΗΜΕΝΟΙ
            if diag["marine_issues"]:
                st.error("### ⚓ 3. Έλλειψη Ναυτολογημένων")
                for m in diag["marine_issues"]:
                    st.write(f"Στο πόστο **{m['role']}** απαιτούνται **{m['needed']}** βάρδιες ναυτολογημένων, αλλά είναι διαθέσιμες μόνο **{m['available']}**.")

            # ΑΙΤΙΑ 4: ΣΥΓΚΡΟΥΣΕΙΣ ΚΩΛΥΜΑΤΩΝ
            if diag["unavail_conflicts"]:
                st.error("### 🚫 4. Συγκρούσεις Κωλυμάτων με τις Βάρδιες")
                st.write("Οι παρακάτω υπάλληλοι δήλωσαν ότι δεν μπορούν σε ώρες που το μαγαζί μένει χωρίς προσωπικό αν δεν μπουν:")
                un_df = pd.DataFrame(diag["unavail_conflicts"][:8])
                un_df["Ώρα"] = un_df["hour"].apply(lambda h: f"{format_hour(h)} - {format_hour(h+1)}")
                st.table(un_df[["name", "role", "day", "Ώρα"]].rename(columns={"name": "Εργαζόμενος", "role": "Πόστο", "day": "Ημέρα"}))

            # ΣΥΓΚΕΝΤΡΩΤΙΚΟΣ ΠΙΝΑΚΑΣ
            st.markdown("### 📊 Συγκεντρωτικός Πίνακας Ανάλυσης")
            stats_table = []
            for r, s in diag["role_stats"].items():
                if s["shifts_needed"] > s["shifts_available"]:
                    katastasi = "❌ Έλλειψη"
                elif s["shifts_needed"] == s["shifts_available"]:
                    katastasi = "⚠️ Οριακό (0 Ευελιξία)"
                else:
                    katastasi = "✅ Εντάξει"

                stats_table.append({
                    "Πόστο": r,
                    "Προσωπικό": f"{s['staff_count']} άτομα ({s['marine_count']} ναυτ.)",
                    "Ώρες Ζήτησης": f"{s['hours_demanded']} ώρες",
                    "Απαιτούμενα Μεροκάματα": f"{s['shifts_needed']} βάρδιες",
                    "Διαθέσιμα Μεροκάματα": f"{s['shifts_available']} βάρδιες",
                    "Κατάσταση": katastasi
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
        staff_current_names = [e["name"] for e in st.session_state.employees]

        edited_df = st.data_editor(
            st.session_state.schedule_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Ημέρα": st.column_config.SelectboxColumn("Ημέρα", options=DAYS, required=True),
                "Εργαζόμενος": st.column_config.SelectboxColumn("Εργαζόμενος", options=staff_current_names, required=True),
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