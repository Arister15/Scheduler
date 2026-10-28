import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model

st.set_page_config(page_title="Shift Scheduler Pro", layout="wide")
st.title("📋 Αυτόματο Πρόγραμμα Βαρδιών")

DAYS = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]
ROLES = ["Service", "Bar", "Υποδοχή"]
HOURS = list(range(11, 26))  # 11:00 έως 25 (01:00)

def format_hour(h):
    """Μετατρέπει τον ακέραιο ώρας σε μορφή hh:00."""
    if h < 24:
        return f"{h:02d}:00"
    elif h == 24:
        return "00:00"
    else:
        return "01:00"

def parse_hour(h_str):
    """Μετατρέπει τη συμβολοσειρά ώρας σε ακέραιο (11-25)."""
    if h_str == "01:00":
        return 25
    if h_str == "00:00":
        return 24
    return int(str(h_str).split(":")[0])

def is_emp_available_at_hour(emp, day, h):
    """Ελέγχει αν ο υπάλληλος είναι διαθέσιμος τη συγκεκριμένη ώρα."""
    u = emp["unavailability"][day]
    if u["status"] == "all_day":
        return False
    if u["status"] == "custom" and (u["start"] <= h < u["end"]):
        return False
    return True

def get_max_continuous_free_hours(emp, day):
    """Βρίσκει το μέγιστο συνεχόμενο ελεύθερο μπλοκ ωρών του υπαλλήλου σε μια ημέρα."""
    max_streak = 0
    current_streak = 0
    for h in range(11, 25):
        if is_emp_available_at_hour(emp, day, h):
            current_streak += 1
            if current_streak > max_streak:
                max_streak = current_streak
        else:
            current_streak = 0
    return max_streak

# ---------------------------------------------------------
# ΣΥΝΑΡΤΗΣΗ ΔΙΑΓΝΩΣΗΣ ΑΔΥΝΑΤΗΣ ΕΠΙΛΥΣΗΣ
# ---------------------------------------------------------
def run_infeasibility_diagnostics(employees, zones):
    """Αναλύει γιατί είναι αδύνατο να βγει το πρόγραμμα και εντοπίζει τις αιτίες."""
    role_reports = {}
    hourly_shortages = []
    marine_shortages = []
    emp_shift_issues = []

    # 1. Έλεγχος ανά Υπάλληλο για το αν μπορεί να πιάσει το 5ωρο
    for e in employees:
        valid_days_for_shift = 0
        for d in DAYS:
            if get_max_continuous_free_hours(e, d) >= 5:
                valid_days_for_shift += 1
        
        avail_days_general = sum(1 for d in DAYS if e["unavailability"][d]["status"] != "all_day")
        target_min = max(0, min(e["target_shifts"] - 1, avail_days_general))
        
        if valid_days_for_shift < target_min:
            emp_shift_issues.append({
                "name": e["name"],
                "role": e["role"],
                "valid_days": valid_days_for_shift,
                "needed": target_min
            })

    # 2. Ανάλυση ανά Πόστο & Ωριαία Bottlenecks
    for role in ROLES:
        staff_role = [e for e in employees if e["role"] == role]
        marine_role = [e for e in staff_role if e["is_marine"]]

        total_demanded_hours = 0
        role_hourly_issues = []
        role_marine_issues = []

        for d in DAYS:
            for h in range(11, 25):
                # Υπολογισμός απαίτησης ζώνης για τη συγκεκριμένη ώρα
                matching_zones = [
                    z for z in zones
                    if (z["day"] == "Όλες" or z["day"] == d)
                    and z["role"] == role
                    and z["start"] <= h < z["end"]
                ]
                
                needed_staff = max([z["min_staff"] for z in matching_zones], default=0)
                require_marine = any(z["require_marine"] for z in matching_zones)

                total_demanded_hours += needed_staff

                if needed_staff > 0:
                    avail_staff_count = sum(1 for e in staff_role if is_emp_available_at_hour(e, d, h))
                    if avail_staff_count < needed_staff:
                        issue = {
                            "day": d,
                            "hour": h,
                            "role": role,
                            "needed": needed_staff,
                            "available": avail_staff_count
                        }
                        hourly_shortages.append(issue)
                        role_hourly_issues.append(issue)

                    if require_marine:
                        avail_marine_count = sum(1 for e in marine_role if is_emp_available_at_hour(e, d, h))
                        if avail_marine_count == 0:
                            m_issue = {"day": d, "hour": h, "role": role}
                            marine_shortages.append(m_issue)
                            role_marine_issues.append(m_issue)

        # Υπολογισμός Προσφοράς Εργασίας (Μεροκάματα & Ώρες)
        total_min_shifts = 0
        total_max_shifts = 0
        for e in staff_role:
            avail_days_gen = sum(1 for d in DAYS if e["unavailability"][d]["status"] != "all_day")
            total_min_shifts += max(0, min(e["target_shifts"] - 1, avail_days_gen))
            total_max_shifts += min(e["target_shifts"], avail_days_gen)

        min_forced_hours = total_min_shifts * 5
        max_possible_hours = total_max_shifts * 10

        # Κατηγοριοποίηση Πόστου
        if len(staff_role) == 0 and total_demanded_hours > 0:
            status = "❌ Ελλειπές (Δεν υπάρχει κανένας υπάλληλος)"
            badge_color = "red"
            explanation = "Ζητούνται ώρες από τον manager αλλά δεν υπάρχει κανένας εργαζόμενος δηλωμένος σε αυτό το πόστο."
        elif role_hourly_issues:
            status = "❌ Ελλειπές (Θέλει άτομα / ώρες)"
            badge_color = "red"
            explanation = f"Υπάρχουν {len(role_hourly_issues)} ώρες μέσα στην εβδομάδα όπου τα διαθέσιμα άτομα δεν φτάνουν να καλύψουν τις απαιτήσεις λόγω κωλυμάτων."
        elif role_marine_issues:
            status = "⚓ Έλλειψη Ναυτολογημένου"
            badge_color = "orange"
            explanation = "Σε ορισμένες ώρες απαιτείται ναυτολογημένος, αλλά κανένας ναυτολογημένος του πόστου δεν είναι διαθέσιμος."
        elif total_demanded_hours > 0 and min_forced_hours > (total_demanded_hours * 1.35):
            status = "⚠️ Πολλά άτομα για τις διαθέσιμες βάρδιες"
            badge_color = "orange"
            explanation = (
                f"Οι υπάλληλοι πρέπει υποχρεωτικά να πάρουν τουλάχιστον {total_min_shifts} μεροκάματα των 5+ ωρών "
                f"({min_forced_hours} ώρες μίνιμουμ), ενώ το μαγαζί ζητάει μόνο {total_demanded_hours} ώρες συνολικά."
            )
        elif max_possible_hours < total_demanded_hours:
            status = "❌ Ελλειπές (Θέλει άτομα)"
            badge_color = "red"
            explanation = f"Οι συνολικές απαιτήσεις ({total_demanded_hours} ώρες) υπερβαίνουν το μέγιστο όριο των υπαλλήλων ({max_possible_hours} ώρες)."
        else:
            status = "✅ Εντάξει"
            badge_color = "green"
            explanation = f"Η διαθεσιμότητα και οι απαιτήσεις είναι ισορροπημένες (Ζήτηση: ~{total_demanded_hours} ώρες)."

        role_reports[role] = {
            "status": status,
            "badge_color": badge_color,
            "explanation": explanation,
            "staff_count": len(staff_role),
            "marine_count": len(marine_role),
            "demanded_hours": total_demanded_hours
        }

    return role_reports, hourly_shortages, marine_shortages, emp_shift_issues

# ---------------------------------------------------------
# ΑΡΧΙΚΟΠΟΙΗΣΗ SESSION STATE
# ---------------------------------------------------------
STAFF_NAMES = [
    "Άρης", "Γιάννης", "Κώστας", "Βαγγέλης", "Μαρία",
    "Φωτεινή", "Θεόφιλος", "Σαλώμη", "Ευαγγελία", "Faith", "Ραφαήλ"
]

if "employees" not in st.session_state:
    st.session_state.employees = [
        {
            "id": i + 1,
            "name": name,
            "role": "Service" if i % 3 == 0 else ("Bar" if i % 3 == 1 else "Υποδοχή"),
            "is_marine": True if i in [0, 1, 4, 6] else False,
            "target_shifts": 5,
            "unavailability": {
                d: {"status": "available", "start": 11, "end": 17} for d in DAYS
            }
        }
        for i, name in enumerate(STAFF_NAMES)
    ]
else:
    for e in st.session_state.employees:
        if not isinstance(e.get("unavailability"), dict):
            e["unavailability"] = {d: {"status": "available", "start": 11, "end": 17} for d in DAYS}

if "zones" not in st.session_state:
    st.session_state.zones = [
        {"id": 1, "day": "Όλες", "role": "Service", "start": 11, "end": 18, "min_staff": 2, "require_marine": False},
        {"id": 2, "day": "Όλες", "role": "Service", "start": 18, "end": 25, "min_staff": 3, "require_marine": True},
        {"id": 3, "day": "Όλες", "role": "Bar", "start": 11, "end": 18, "min_staff": 1, "require_marine": True},
        {"id": 4, "day": "Όλες", "role": "Bar", "start": 18, "end": 25, "min_staff": 2, "require_marine": True},
        {"id": 5, "day": "Όλες", "role": "Υποδοχή", "start": 19, "end": 24, "min_staff": 1, "require_marine": False},
    ]

if "schedule_df" not in st.session_state:
    st.session_state.schedule_df = None

tab1, tab2, tab3 = st.tabs(["👤 Καρτέλα Υπαλλήλου", "⚙️ Ρυθμίσεις Manager (Ζώνες)", "📅 Τελικό Πρόγραμμα"])

# ---------------------------------------------------------
# TAB 1: ΚΑΡΤΕΛΑ ΥΠΑΛΛΗΛΟΥ
# ---------------------------------------------------------
with tab1:
    st.subheader("Δήλωση Στοιχείων & Διαθεσιμότητας")
    
    emp_names = [e["name"] for e in st.session_state.employees]
    selected_name = st.selectbox("Επιλέξτε το όνομά σας:", emp_names)
    emp = next(e for e in st.session_state.employees if e["name"] == selected_name)

    col_role, col_marine, col_shifts = st.columns(3)
    with col_role:
        st.selectbox("Πόστο εργασίας:", ROLES, index=ROLES.index(emp["role"]), key=f"role_{emp['id']}")
    with col_marine:
        st.checkbox("Ναυτολογημένος/η", value=emp["is_marine"], key=f"marine_{emp['id']}")
    with col_shifts:
        st.slider("Επιθυμητά μεροκάματα εβδομάδας:", 1, 7, emp["target_shifts"], key=f"shifts_{emp['id']}", help="Ανάθεση: [στόχος - 1] έως [στόχος] ημέρες.")

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
                st.radio(f"Κατάσταση για {d}:", STATUS_OPTS, index=STATUS_OPTS.index(cur_status), key=f"status_{emp['id']}_{d}", label_visibility="collapsed")

            with col_hours:
                cur_chosen_status = st.session_state.get(f"status_{emp['id']}_{d}", cur_status)
                if cur_chosen_status == "🟡 Κώλυμα συγκεκριμένες ώρες":
                    st.select_slider(
                        f"Ώρες κωλύματος ({d}):",
                        options=HOURS,
                        value=(cur_day_data.get("start", 11), cur_day_data.get("end", 17)),
                        format_func=format_hour,
                        key=f"slider_{emp['id']}_{d}"
                    )
                elif cur_chosen_status == "🔴 Όλη μέρα ρεπό":
                    st.info(f"🚫 Ρεπό για την {d}.")
                else:
                    st.success(f"✅ Πλήρως διαθέσιμος/η για εργασία την {d}.")

            st.write("---")

    col_submit, col_reset = st.columns([2, 1])

    with col_submit:
        if st.button("💾 Αποθήκευση Όλων (Submit All)", type="primary", use_container_width=True):
            emp["role"] = st.session_state[f"role_{emp['id']}"]
            emp["is_marine"] = st.session_state[f"marine_{emp['id']}"]
            emp["target_shifts"] = st.session_state[f"shifts_{emp['id']}"]

            for d in DAYS:
                selected_st = st.session_state.get(f"status_{emp['id']}_{d}", STATUS_OPTS[0])
                code = status_to_code[selected_st]
                slider_val = st.session_state.get(f"slider_{emp['id']}_{d}", (11, 17))
                emp["unavailability"][d] = {"status": code, "start": slider_val[0], "end": slider_val[1]}

            st.success(f"🎉 Όλα τα στοιχεία και τα κωλύματα για τον/την **{emp['name']}** αποθηκεύτηκαν επιτυχώς!")

    with col_reset:
        if st.button("🗑️ Καθαρισμός Κωλυμάτων (Reset)", use_container_width=True):
            for d in DAYS:
                emp["unavailability"][d] = {"status": "available", "start": 11, "end": 17}
                st.session_state[f"status_{emp['id']}_{d}"] = STATUS_OPTS[0]
                if f"slider_{emp['id']}_{d}" in st.session_state:
                    st.session_state[f"slider_{emp['id']}_{d}"] = (11, 17)
            st.info(f"Τα κωλύματα του/της {emp['name']} μηδενίστηκαν.")
            st.rerun()

    st.markdown("#### 📋 Τρέχουσα Κατάσταση Προφίλ & Κωλυμάτων")
    min_shifts_disp = max(0, emp["target_shifts"] - 1)
    st.write(f"**Πόστο:** `{emp['role']}` | **Ναυτολόγηση:** `{'Ναι' if emp['is_marine'] else 'Όχι'}` | **Όριο Βαρδιών:** `{min_shifts_disp} έως {emp['target_shifts']} ημέρες`")

    summary_data = []
    for d in DAYS:
        u_info = emp["unavailability"][d]
        if u_info["status"] == "all_day":
            katastasi = "🔴 Ρεπό (Όλη μέρα)"
        elif u_info["status"] == "custom":
            katastasi = f"🟡 Κώλυμα: {format_hour(u_info['start'])} - {format_hour(u_info['end'])}"
        else:
            katastasi = "🟢 Πλήρως Διαθέσιμος/η"
        summary_data.append({"Ημέρα": d, "Κατάσταση": katastasi})

    st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# TAB 2: ΡΥΘΜΙΣΕΙΣ MANAGER (LIVE DOUBLE-TAP EDITING)
# ---------------------------------------------------------
with tab2:
    st.subheader("Διαχείριση Ζωνών & Αναγκών Προσωπικού")
    st.info("💡 **Κάντε διπλό κλικ (ή double tap) σε οποιοδήποτε κελί** του παρακάτω πίνακα για να αλλάξετε άμεσα Ημέρα, Πόστο, Ώρες, Άτομα ή Ναυτολόγηση.")

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
    st.session_state.zones = updated_zones

    st.write("")
    with st.expander("➕ Προσθήκη Νέας Ζώνης", expanded=False):
        with st.form("add_zone_form"):
            new_day = st.selectbox("Ημέρα:", ["Όλες"] + DAYS)
            new_z_role = st.selectbox("Πόστο:", ROLES)
            new_start, new_end = st.select_slider(
                "Ωράριο Ζώνης:",
                options=HOURS,
                value=(18, 25),
                format_func=format_hour
            )
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
                if "zones_table_editor" in st.session_state:
                    del st.session_state["zones_table_editor"]
                st.success("Η ζώνη προστέθηκε επιτυχώς!")
                st.rerun()

# ---------------------------------------------------------
# TAB 3: ΕΠΙΛΥΣΗ ΜΕ GOOGLE OR-TOOLS & ΣΥΣΤΗΜΑ ΔΙΑΓΝΩΣΗΣ
# ---------------------------------------------------------
with tab3:
    st.subheader("Αυτόματη Δημιουργία & Επεξεργασία Προγράμματος")

    if st.button("🚀 Υπολογισμός Προγράμματος (OR-Tools)", type="primary"):
        model = cp_model.CpModel()
        
        x = {}
        for e in st.session_state.employees:
            for d in DAYS:
                for h in range(11, 25):  # 11:00 έως 01:00
                    x[(e["id"], d, h)] = model.NewBoolVar(f"x_{e['id']}_{d}_{h}")

        works_day = {}
        for e in st.session_state.employees:
            for d in DAYS:
                works_day[(e["id"], d)] = model.NewBoolVar(f"works_{e['id']}_{d}")
                hours_worked = [x[(e["id"], d, h)] for h in range(11, 25)]
                model.Add(sum(hours_worked) >= 1).OnlyEnforceIf(works_day[(e["id"], d)])
                model.Add(sum(hours_worked) == 0).OnlyEnforceIf(works_day[(e["id"], d)].Not())

            # 1. Κανόνας: Μεροκάματα από (Στόχος - 1) έως Στόχος
            available_days_count = sum(1 for d in DAYS if e["unavailability"][d]["status"] != "all_day")
            effective_max = min(e["target_shifts"], available_days_count)
            effective_min = max(0, min(e["target_shifts"] - 1, available_days_count))

            total_days_worked = sum(works_day[(e["id"], d)] for d in DAYS)
            model.Add(total_days_worked >= effective_min)
            model.Add(total_days_worked <= effective_max)

            # 2. Κανόνας: Κωλύματα
            for d, u_info in e["unavailability"].items():
                if u_info["status"] == "all_day":
                    for h in range(11, 25):
                        model.Add(x[(e["id"], d, h)] == 0)
                elif u_info["status"] == "custom":
                    for h in range(u_info["start"], u_info["end"]):
                        if h in range(11, 25):
                            model.Add(x[(e["id"], d, h)] == 0)

            # 3. Κανόνας: Βάρδια 5 έως 10 ώρες & Συνεχόμενο ωράριο
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

        # 4. Κανόνας: Κάλυψη Custom Ζωνών Manager
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
            # ---------------------------------------------------------
            # ΕΚΤΕΛΕΣΗ ΔΙΑΓΝΩΣΗΣ ΟΤΑΝ ΔΕΝ ΒΓΑΙΝΕΙ ΤΟ ΠΡΟΓΡΑΜΜΑ
            # ---------------------------------------------------------
            st.session_state.schedule_df = None
            st.error("❌ Αδύνατη η εύρεση λύσης! Το πρόγραμμα δεν μπορεί να δημιουργηθεί με τους ισχύοντες περιορισμούς.")
            
            # Τρέχουμε τον διαγνωστικό έλεγχο
            role_rep, h_issues, m_issues, emp_issues = run_infeasibility_diagnostics(
                st.session_state.employees,
                st.session_state.zones
            )

            st.markdown("### 🔍 Ανάλυση Αιτιών & Διάγνωση Προβλήματος")
            
            # 1. Σύνοψη ανά Πόστο
            st.markdown("#### 1. Κατάσταση ανά Πόστο")
            c1, c2, c3 = st.columns(3)
            cols = [c1, c2, c3]
            for i, r in enumerate(ROLES):
                info = role_rep[r]
                with cols[i]:
                    st.markdown(f"**{r}**")
                    st.markdown(f"**Κατάσταση:** `{info['status']}`")
                    st.caption(f"👥 Προσωπικό: {info['staff_count']} άτομα ({info['marine_count']} ναυτολ.)")
                    st.info(info["explanation"])

            # 2. Συγκεκριμένες Ελλείψεις ανά Ώρα & Ημέρα
            if h_issues:
                st.markdown("#### 2. Συγκεκριμένες Ελλείψεις Προσωπικού (Bottlenecks)")
                st.warning(f"Βρέθηκαν **{len(h_issues)}** ωριαία παράθυρα όπου τα διαθέσιμα άτομα είναι λιγότερα από όσα ζητάει ο manager:")
                shortage_rows = []
                for item in h_issues[:8]:  # Προβολή των πρώτων 8
                    shortage_rows.append({
                        "Ημέρα": item["day"],
                        "Ώρα": f"{format_hour(item['hour'])} - {format_hour(item['hour']+1)}",
                        "Πόστο": item["role"],
                        "Απαιτούμενα Άτομα": item["needed"],
                        "Διαθέσιμα Άτομα": item["available"]
                    })
                st.table(pd.DataFrame(shortage_rows))
                if len(h_issues) > 8:
                    st.caption(f"...και άλλες {len(h_issues)-8} ώρες με έλλειψη.")

            # 3. Ελλείψεις Ναυτολογημένων
            if m_issues:
                st.markdown("#### 3. Ελλείψεις Ναυτολογημένου Προσωπικού")
                st.error("Στις παρακάτω ώρες απαιτείται ναυτολογημένος, αλλά κανένας δεν είναι διαθέσιμος:")
                m_rows = [{"Ημέρα": m["day"], "Ώρα": f"{format_hour(m['hour'])} - {format_hour(m['hour']+1)}", "Πόστο": m["role"]} for m in m_issues]
                st.table(pd.DataFrame(m_rows))

            # 4. Θέματα με το 5ωρο ανά εργαζόμενο
            if emp_issues:
                st.markdown("#### 4. Κωλύματα Εργαζομένων & Ελάχιστη Βάρδια (5 ώρες)")
                st.warning("Οι παρακάτω εργαζόμενοι δήλωσαν τόσα κωλύματα που δεν τους απομένουν αρκετές ημέρες με **συνεχόμενο 5ωρο** για να καλύψουν τα επιθυμητά μεροκάματα:")
                e_rows = [
                    {
                        "Εργαζόμενος": ei["name"],
                        "Πόστο": ei["role"],
                        "Ημέρες με ελεύθερο 5ωρο": ei["valid_days"],
                        "Ελάχιστα μεροκάματα που ζήτησε": ei["needed"]
                    }
                    for ei in emp_issues
                ]
                st.table(pd.DataFrame(e_rows))

            # 5. Πρακτικές Συμβουλές Επίλυσης
            st.markdown("#### 💡 Πώς να το επιλύσετε:")
            st.markdown("""
            * **Αν ένα πόστο είναι ελλειπές:** Μειώστε τα ελάχιστα απαιτούμενα άτομα στις ρυθμίσεις Manager ή μειώστε τα κωλύματα των εργαζομένων.
            * **Αν ένα πόστο έχει πολλά άτομα:** Μειώστε τα επιθυμητά μεροκάματα των υπαλλήλων (π.χ. από 5 σε 3) ώστε να μην επιβάλλεται υποχρεωτικά μεγάλος αριθμός βαρδιών.
            * **Αν λείπει ναυτολογημένος:** Βεβαιωθείτε ότι υπάρχει έστω ένας ναυτολογημένος στο πόστο που δεν έχει δηλώσει ρεπό/κώλυμα εκείνες τις ώρες.
            """)

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