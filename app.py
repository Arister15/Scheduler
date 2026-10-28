import streamlit as st
import pandas as pd
import json
import os
import io
import math
from ortools.sat.python import cp_model
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

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
    # Μόνιμη ταξινόμηση ζωνών ανά Πόστο πριν την αποθήκευση
    zones.sort(key=lambda z: (ROLES.index(z["role"]) if z["role"] in ROLES else 99, z["day"], z["start"]))
    data = {"employees": employees, "zones": zones}
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if "employees" not in st.session_state or "zones" not in st.session_state:
    loaded_emps, loaded_zones = load_persistent_data()
    st.session_state.employees = loaded_emps
    st.session_state.zones = loaded_zones

if "matrix_schedule" not in st.session_state:
    st.session_state.matrix_schedule = None

# ---------------------------------------------------------
# ΕΞΑΓΩΓΗ ΣΕ ΕΓΧΡΩΜΟ EXCEL (.XLSX)
# ---------------------------------------------------------
def create_styled_excel(df):
    """Δημιουργεί έγχρωμο Excel με τα ακριβή χρώματα της φωτογραφίας ανά πόστο."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Πρόγραμμα Βαρδιών"

    # Χρώματα ανά ρόλο βάσει φωτογραφίας (Hex)
    role_hex_colors = {
        "Service": "FCE5CD",   # Απαλό Πορτοκαλί / Ροδακινί
        "Bar": "CFE2F3",       # Απαλό Γαλάζιο
        "Υποδοχή": "FFF2CC"    # Απαλό Κίτρινο
    }

    thin_border = Border(
        left=Side(style='thin', color='A6A6A6'),
        right=Side(style='thin', color='A6A6A6'),
        top=Side(style='thin', color='A6A6A6'),
        bottom=Side(style='thin', color='A6A6A6')
    )

    header_font = Font(name='Arial', size=11, bold=True, color='000000')
    header_fill = PatternFill(start_color='F3F3F3', end_color='F3F3F3', fill_type='solid')
    bold_repo_font = Font(name='Arial', size=10, bold=True, color='7F6000')
    regular_font = Font(name='Arial', size=10, bold=False, color='000000')
    emp_font = Font(name='Arial', size=10, bold=True, color='000000')

    # Εγγραφή Κεφαλίδων (Headers)
    headers = list(df.columns)
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin_border

    # Εγγραφή Δεδομένων με Background Χρώμα ανά Ρόλο
    for r_idx, row in df.iterrows():
        ws.append(list(row))
        curr_row = r_idx + 2
        role = row["Πόστο"]
        bg_hex = role_hex_colors.get(role, "FFFFFF")
        fill_color = PatternFill(start_color=bg_hex, end_color=bg_hex, fill_type='solid')

        for c_idx, col_name in enumerate(headers, start=1):
            cell = ws.cell(row=curr_row, column=c_idx)
            cell.fill = fill_color
            cell.border = thin_border
            val_str = str(cell.value)

            if col_name in ["Εργαζόμενος", "Πόστο"]:
                cell.font = emp_font
                cell.alignment = Alignment(horizontal='left', vertical='center', indent=1)
            else:
                cell.alignment = Alignment(horizontal='center', vertical='center')
                if val_str == "ΡΕΠΟ":
                    cell.font = bold_repo_font
                else:
                    cell.font = regular_font

    # Ρύθμιση πλάτους στηλών
    for col in ws.columns:
        col_letter = col[0].column_letter
        ws.column_dimensions[col_letter].width = 17

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output

# ---------------------------------------------------------
# ΜΟΝΑΔΙΑΙΟΣ SOLVER & ΔΙΑΓΝΩΣΗ
# ---------------------------------------------------------
def solve_single_role(role, employees, zones, relax=None):
    staff_r = [e for e in employees if e["role"] == role]
    zones_r = [z for z in zones if z["role"] == role]

    if not zones_r:
        return cp_model.OPTIMAL, [], []
    if not staff_r:
        return cp_model.INFEASIBLE, [], ["Δεν υπάρχει κανένας υπάλληλος καταχωρημένος σε αυτό το πόστο!"]

    model = cp_model.CpModel()
    x = {}
    for e in staff_r:
        for d in DAYS:
            for h in range(11, 25):
                x[(e["id"], d, h)] = model.NewBoolVar(f"x_{e['id']}_{d}_{h}")

    works_day = {}
    for e in staff_r:
        for d in DAYS:
            works_day[(e["id"], d)] = model.NewBoolVar(f"works_{e['id']}_{d}")
            hours_worked = [x[(e["id"], d, h)] for h in range(11, 25)]
            model.Add(sum(hours_worked) >= 1).OnlyEnforceIf(works_day[(e["id"], d)])
            model.Add(sum(hours_worked) == 0).OnlyEnforceIf(works_day[(e["id"], d)].Not())

        avail_count = sum(1 for d in DAYS if e["unavailability"][d]["status"] != "all_day")
        eff_max = min(e["target_shifts"], avail_count)
        eff_min = max(0, min(e["target_shifts"] - 1, avail_count))

        if relax != "no_min_shifts":
            model.Add(sum(works_day[(e["id"], d)] for d in DAYS) >= eff_min)
        if relax != "no_max_shifts":
            model.Add(sum(works_day[(e["id"], d)] for d in DAYS) <= eff_max)

        if relax != "no_unavail":
            for d, u in e["unavailability"].items():
                if u["status"] == "all_day":
                    for h in range(11, 25):
                        model.Add(x[(e["id"], d, h)] == 0)
                elif u["status"] == "custom":
                    for h in range(u["start"], u["end"]):
                        if h in range(11, 25):
                            model.Add(x[(e["id"], d, h)] == 0)

        for d in DAYS:
            daily_h = [x[(e["id"], d, h)] for h in range(11, 25)]
            model.Add(sum(daily_h) <= 10)
            if relax != "no_min_hours":
                model.Add(sum(daily_h) >= 5).OnlyEnforceIf(works_day[(e["id"], d)])

            starts = []
            for i, h in enumerate(range(11, 25)):
                st_var = model.NewBoolVar(f"st_{e['id']}_{d}_{h}")
                if i == 0:
                    model.Add(st_var == x[(e["id"], d, h)])
                else:
                    model.Add(st_var >= x[(e["id"], d, h)] - x[(e["id"], d, h - 1)])
                starts.append(st_var)
            model.Add(sum(starts) <= 1)

    marines_r = [e for e in staff_r if e["is_marine"]]
    for z in zones_r:
        t_days = DAYS if z["day"] == "Όλες" else [z["day"]]
        for d in t_days:
            for h in range(z["start"], z["end"]):
                model.Add(sum(x[(e["id"], d, h)] for e in staff_r) >= z["min_staff"])
                if z["require_marine"] and relax != "no_marine":
                    model.Add(sum(x[(e["id"], d, h)] for e in marines_r) >= 1)

    total_h = sum(x[(e["id"], d, h)] for e in staff_r for d in DAYS for h in range(11, 25))
    model.Minimize(total_h)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 3.0
    status = solver.Solve(model)

    res = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for d in DAYS:
            for e in staff_r:
                w = [h for h in range(11, 25) if solver.Value(x[(e["id"], d, h)]) == 1]
                if w:
                    res.append({
                        "day": d,
                        "name": e["name"],
                        "role": e["role"],
                        "shift": f"{format_hour(min(w))}-{format_hour(max(w) + 1)}"
                    })
    return status, res, []

def diagnose_role_failure(role, employees, zones):
    reasons = []
    st_min, _, _ = solve_single_role(role, employees, zones, relax="no_min_shifts")
    if st_min in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        reasons.append("📉 **Πλεόνασμα Προσωπικού / Υποχρεωτικά Μεροκάματα:** Ο αλγόριθμος υποχρεώνεται να δώσει σε όλους τουλάχιστον (Στόχος - 1) μεροκάματα, αλλά οι βάρδιες του μαγαζιού είναι λιγότερες! Μειώστε τα επιθυμητά μεροκάματα ορισμένων υπαλλήλων.")

    st_mar, _, _ = solve_single_role(role, employees, zones, relax="no_marine")
    if st_mar in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        reasons.append("⚓ **Περιορισμός Ναυτολογημένων:** Οι ναυτολογημένοι εργαζόμενοι δεν επαρκούν ή έχουν δηλώσει κώλυμα στις ναυτολογημένες ζώνες. Ορίστε επιπλέον ναυτολογημένο ή αφαιρέστε την απαίτηση από πρωινές ζώνες.")

    st_un, _, _ = solve_single_role(role, employees, zones, relax="no_unavail")
    if st_un in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        reasons.append("🚫 **Σύγκρουση Κωλυμάτων:** Τα ρεπό ή οι ώρες κωλυμάτων συμπίπτουν και αφήνουν το μαγαζί χωρίς κάλυψη.")

    st_h, _, _ = solve_single_role(role, employees, zones, relax="no_min_hours")
    if st_h in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        reasons.append("⏱️ **Ελάχιστη Βάρδια 5 Ωρών:** Κάποια ζώνη είναι μικρότερη από 5 ώρες ή κάποιο κώλυμα αφήνει λιγότερο από 5ωρο ελεύθερο.")

    st_max, _, _ = solve_single_role(role, employees, zones, relax="no_max_shifts")
    if st_max in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        reasons.append("📈 **Έλλειψη Μεροκάματων:** Οι υπάλληλοι δεν φτάνουν για να καλύψουν όλες τις βάρδιες. Αυξήστε τα μεροκάματα σε 1-2 άτομα ή προσθέστε προσωπικό.")

    if not reasons:
        reasons.append("⚠️ **Σύνθετη Σύγκρουση:** Συνδυασμός οριακού αριθμού ατόμων και αυστηρών ωραρίων.")
    return reasons

tab1, tab2, tab3 = st.tabs(["👤 Καρτέλα Υπαλλήλου", "⚙️ Ρυθμίσεις Manager (Ζώνες)", "📅 Τελικό Πρόγραμμα"])

# ---------------------------------------------------------
# TAB 1: ΚΑΡΤΕΛΑ ΥΠΑΛΛΗΛΟΥ
# ---------------------------------------------------------
with tab1:
    st.subheader("Δήλωση Στοιχείων & Διαθεσιμότητας")

    with st.expander("👥 Διαχείριση Προσωπικού (Προσθήκη / Διαγραφή Υπαλλήλου)", expanded=False):
        c_add, c_del = st.columns(2)
        with c_add:
            st.markdown("##### ➕ Προσθήκη Νέου Υπαλλήλου")
            with st.form("add_new_emp_form"):
                new_name = st.text_input("Ονοματεπώνυμο:")
                new_r = st.selectbox("Πόστο:", ROLES, key="add_emp_role")
                new_mar = st.checkbox("Ναυτολογημένος/η", key="add_emp_marine")
                new_sh = st.slider("Επιθυμητά μεροκάματα:", 1, 7, 5, key="add_emp_shifts")
                
                if st.form_submit_button("Αποθήκευση Υπαλλήλου"):
                    if not new_name.strip():
                        st.error("Εισάγετε όνομα.")
                    elif any(e["name"].lower() == new_name.strip().lower() for e in st.session_state.employees):
                        st.error("Υπάρχει ήδη υπάλληλος με αυτό το όνομα.")
                    else:
                        nid = max([e["id"] for e in st.session_state.employees], default=0) + 1
                        st.session_state.employees.append({
                            "id": nid,
                            "name": new_name.strip(),
                            "role": new_r,
                            "is_marine": new_mar,
                            "target_shifts": new_sh,
                            "unavailability": {d: {"status": "available", "start": 11, "end": 17} for d in DAYS}
                        })
                        save_persistent_data(st.session_state.employees, st.session_state.zones)
                        st.success(f"Ο/Η {new_name} προστέθηκε επιτυχώς!")
                        st.rerun()

        with c_del:
            st.markdown("##### 🗑️ Διαγραφή Υπαλλήλου")
            if st.session_state.employees:
                del_name = st.selectbox("Επιλέξτε υπάλληλο προς διαγραφή:", [e["name"] for e in st.session_state.employees], key="del_emp_select")
                if st.button("❌ Οριστική Διαγραφή", type="secondary"):
                    st.session_state.employees = [e for e in st.session_state.employees if e["name"] != del_name]
                    save_persistent_data(st.session_state.employees, st.session_state.zones)
                    st.success(f"Ο/Η {del_name} διαγράφηκε!")
                    st.rerun()

    st.divider()

    if not st.session_state.employees:
        st.warning("Δεν υπάρχουν καταχωρημένοι υπάλληλοι.")
        st.stop()

    emp_names = [e["name"] for e in st.session_state.employees]
    selected_name = st.selectbox("Επιλέξτε το όνομά σας:", emp_names, key="selected_employee_dropdown")
    emp = next(e for e in st.session_state.employees if e["name"] == selected_name)

    st.markdown("#### ⚡ Σύντομη Επισκόπηση Εβδομάδας")
    quick_dict = {}
    for d in DAYS:
        u = emp["unavailability"][d]
        if u["status"] == "all_day":
            quick_dict[d] = "🔴 Ρεπό"
        elif u["status"] == "custom":
            quick_dict[d] = f"🟡 {format_hour(u['start'])}-{format_hour(u['end'])}"
        else:
            quick_dict[d] = "🟢 Διαθέσιμος"
    st.dataframe(pd.DataFrame([quick_dict]), use_container_width=True, hide_index=True)

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
# TAB 2: ΡΥΘΜΙΣΕΙΣ MANAGER (ΤΑΞΙΝΟΜΗΣΗ ΑΝΑ ΠΟΣΤΟ)
# ---------------------------------------------------------
with tab2:
    st.subheader("Διαχείριση Ζωνών & Αναγκών Προσωπικού")
    st.info("💡 Οι ζώνες είναι **ταξινομημένες ανά Πόστο** (Service ➔ Bar ➔ Υποδοχή). Κάντε διπλό κλικ σε οποιοδήποτε κελί για άμεση αλλαγή.")

    # Ταξινόμηση ζωνών ανά Πόστο
    st.session_state.zones.sort(key=lambda z: (ROLES.index(z["role"]) if z["role"] in ROLES else 99, z["day"], z["start"]))

    zones_list_data = [
        {
            "ID": z["id"],
            "Πόστο": z["role"],
            "Ημέρα": z["day"],
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
            "Πόστο": st.column_config.SelectboxColumn("Πόστο", options=ROLES, required=True),
            "Ημέρα": st.column_config.SelectboxColumn("Ημέρα", options=["Όλες"] + DAYS, required=True),
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
                new_z_role = st.selectbox("Πόστο:", ROLES)
                chosen_days = st.multiselect(
                    "Ημέρες εφαρμογής:",
                    options=["Όλες"] + DAYS,
                    default=["Όλες"]
                )
                new_start, new_end = st.select_slider("Ωράριο Ζώνης:", options=HOURS, value=(18, 25), format_func=format_hour)
                new_min_staff = st.number_input("Ελάχιστα απαιτούμενα άτομα:", min_value=1, max_value=10, value=2)
                new_require_marine = st.checkbox("Απαιτείται τουλάχιστον 1 ναυτολογημένος")
                
                if st.form_submit_button("Αποθήκευση Νέας Ζώνης"):
                    if not chosen_days:
                        st.error("Επιλέξτε τουλάχιστον μία ημέρα ή 'Όλες'.")
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
                    z["id"]: f"ID {z['id']} | [{z['role']}] | {z['day']} | {format_hour(z['start'])}-{format_hour(z['end'])} ({z['min_staff']} άτομα)"
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
# TAB 3: ΕΠΙΛΥΣΗ, ΕΓΧΡΩΜΟ FORMAT & EXCEL EXPORT
# ---------------------------------------------------------
with tab3:
    st.subheader("Αυτόματη Δημιουργία & Επεξεργασία Προγράμματος")

    if st.button("🚀 Υπολογισμός Προγράμματος (OR-Tools)", type="primary"):
        all_shifts = []
        role_status_report = {}
        has_failure = False

        for r in ROLES:
            status, res, _ = solve_single_role(r, st.session_state.employees, st.session_state.zones)
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                all_shifts.extend(res)
                role_status_report[r] = {"success": True, "reasons": []}
            else:
                has_failure = True
                reasons = diagnose_role_failure(r, st.session_state.employees, st.session_state.zones)
                role_status_report[r] = {"success": False, "reasons": reasons}

        if not has_failure:
            st.success("🎉 Το πρόγραμμα υπολογίστηκε επιτυχώς!")

            # 1. Κατασκευή του Matrix DataFrame (Όπως στη φωτογραφία)
            shift_dict = {(item["day"], item["name"]): item["shift"] for item in all_shifts}
            
            # Ταξινόμηση υπαλλήλων ανά Πόστο
            sorted_employees = sorted(
                st.session_state.employees,
                key=lambda e: (ROLES.index(e["role"]) if e["role"] in ROLES else 99, e["name"])
            )

            matrix_rows = []
            for e in sorted_employees:
                row_data = {
                    "Πόστο": e["role"],
                    "Εργαζόμενος": e["name"]
                }
                for d in DAYS:
                    # Αν έχει βάρδια, βάζουμε το ωράριο, αλλιώς ΡΕΠΟ
                    row_data[d] = shift_dict.get((d, e["name"]), "ΡΕΠΟ")
                matrix_rows.append(row_data)

            st.session_state.matrix_schedule = pd.DataFrame(matrix_rows)
        else:
            st.session_state.matrix_schedule = None
            st.error("❌ Αδύνατη η εύρεση λύσης! Δείτε παρακάτω ακριβώς ποιο πόστο μπλοκάρει:")

            for r in ROLES:
                rep = role_status_report[r]
                if not rep["success"]:
                    st.markdown(f"### 🚨 Σφάλμα στο πόστο: **{r}**")
                    for reason in rep["reasons"]:
                        st.markdown(f"* {reason}")
                    st.write("")

            st.markdown("### 📊 Συγκεντρωτικός Πίνακας Ανάλυσης")
            summary_table = []
            for r in ROLES:
                staff_r = [e for e in st.session_state.employees if e["role"] == r]
                zones_r = [z for z in st.session_state.zones if z["role"] == r]
                total_h = sum(
                    max([z["min_staff"] for z in zones_r if (z["day"] == "Όλες" or z["day"] == d) and z["start"] <= h < z["end"]], default=0)
                    for d in DAYS for h in range(11, 25)
                )
                avail_shifts = sum(e["target_shifts"] for e in staff_r)
                status_label = "✅ Εντάξει" if role_status_report[r]["success"] else "❌ Μπλοκάρει"

                summary_table.append({
                    "Πόστο": r,
                    "Προσωπικό": f"{len(staff_r)} άτομα",
                    "Ώρες Ζήτησης": f"{total_h} ώρες",
                    "Διαθέσιμα Μεροκάματα": f"{avail_shifts} βάρδιες",
                    "Κατάσταση": status_label
                })
            st.dataframe(pd.DataFrame(summary_table), use_container_width=True, hide_index=True)

    # ---------------------------------------------------------
    # EDITABLE MATRIX & COLOR PREVIEW (ΟΠΩΣ ΣΤΗ ΦΩΤΟΓΡΑΦΙΑ)
    # ---------------------------------------------------------
    if st.session_state.matrix_schedule is not None:
        st.divider()
        st.markdown("### ✏️ Επεξεργάσιμο Πρόγραμμα Βαρδιών")
        st.info("💡 **Κάντε διπλό κλικ σε οποιοδήποτε κελί** για να αλλάξετε ωράριο (π.χ. `18:00-01:00`) ή να γράψετε `ΡΕΠΟ`.")

        edited_matrix = st.data_editor(
            st.session_state.matrix_schedule,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "Πόστο": st.column_config.TextColumn("Πόστο", disabled=True),
                "Εργαζόμενος": st.column_config.TextColumn("Εργαζόμενος", disabled=True),
                "Δευτέρα": st.column_config.TextColumn("Δευτέρα"),
                "Τρίτη": st.column_config.TextColumn("Τρίτη"),
                "Τετάρτη": st.column_config.TextColumn("Τετάρτη"),
                "Πέμπτη": st.column_config.TextColumn("Πέμπτη"),
                "Παρασκευή": st.column_config.TextColumn("Παρασκευή"),
                "Σάββατο": st.column_config.TextColumn("Σάββατο"),
                "Κυριακή": st.column_config.TextColumn("Κυριακή")
            },
            key="matrix_schedule_editor"
        )
        st.session_state.matrix_schedule = edited_matrix

        # 2. ΕΞΑΓΩΓΗ ΣΕ ΕΓΧΡΩΜΟ EXCEL (.XLSX)
        excel_data = create_styled_excel(edited_matrix)
        st.download_button(
            label="📥 Λήψη σε Έγχρωμο Excel (.xlsx)",
            data=excel_data,
            file_name="programma_vardion.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

        # 3. ΕΓΧΡΩΜΗ ΠΡΟΕΠΙΣΚΟΠΗΣΗ HTML (ΑΚΡΙΒΩΣ ΟΠΩΣ ΣΤΗ ΦΩΤΟΓΡΑΦΙΑ)
        st.markdown("#### 🎨 Προεπισκόπηση με Χρώματα ανά Πόστο")
        
        def highlight_roles(row):
            role = row["Πόστο"]
            if role == "Service":
                bg = "background-color: #FCE5CD; color: black;"  # Απαλό Πορτοκαλί
            elif role == "Bar":
                bg = "background-color: #CFE2F3; color: black;"  # Απαλό Μπλε
            else:
                bg = "background-color: #FFF2CC; color: black;"  # Απαλό Κίτρινο
            return [bg] * len(row)

        styled_df = edited_matrix.style.apply(highlight_roles, axis=1)
        st.dataframe(styled_df, use_container_width=True, hide_index=True)