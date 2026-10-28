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
# TAB 2: ΡΥΘΜΙΣΕΙΣ MANAGER (LIVE DOUBLE-TAP EDITING & ΠΡΟΣΘΗΚΗ)
# ---------------------------------------------------------
with tab2:
    st.subheader("Διαχείριση Ζωνών & Αναγκών Προσωπικού")
    st.info("💡 **Κάντε διπλό κλικ (ή double tap) σε οποιοδήποτε κελί** του παρακάτω πίνακα για να αλλάξετε άμεσα Ημέρα, Πόστο, Ώρες, Άτομα ή Ναυτολόγηση. Για διαγραφή γραμμής, επιλέξτε την και πατήστε το εικονίδιο του κάδου.")

    # 1. Πίνακας με άμεση επεξεργασία (Double Tap Edit)
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

    # Συγχρονισμός των αλλαγών του πίνακα στο st.session_state.zones
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
    # 2. Φόρμα Προσθήκης Νέας Ζώνης (Παραμένει ίδια)
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
# TAB 3: ΕΠΙΛΥΣΗ ΜΕ GOOGLE OR-TOOLS (5 ΕΩΣ 10 ΩΡΕΣ)
# ---------------------------------------------------------
with tab3:
    st.subheader("Αυτόματη Δημιουργία & Επεξεργασία Προγράμματος")

    if st.button("🚀 Υπολογισμός Προγράμματος (OR-Tools)", type="primary"):
        model = cp_model.CpModel()
        
        # x[(emp_id, day, hour)]: 1 αν εργάζεται τη συγκεκριμένη ώρα
        x = {}
        for e in st.session_state.employees:
            for d in DAYS:
                for h in range(11, 25):  # 11:00 έως 01:00 (14 ώρες)
                    x[(e["id"], d, h)] = model.NewBoolVar(f"x_{e['id']}_{d}_{h}")

        # works_day[(emp_id, day)]: 1 αν κάνει μεροκάματο
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
                model.Add(sum(daily_h) <= 10)  # Μέγιστο 10 ώρες
                model.Add(sum(daily_h) >= 5).OnlyEnforceIf(works_day[(e["id"], d)])  # Ελάχιστο 5 ώρες

                starts = []
                for i, h in enumerate(range(11, 25)):
                    start_var = model.NewBoolVar(f"start_{e['id']}_{d}_{h}")
                    if i == 0:
                        model.Add(start_var == x[(e["id"], d, h)])
                    else:
                        model.Add(start_var >= x[(e["id"], d, h)] - x[(e["id"], d, h - 1)])
                    starts.append(start_var)
                model.Add(sum(starts) <= 1)

        # 4. Κανόνας: Κάλυψη Ζωνών (Υπάλληλοι μπορούν να καλύπτουν πολλαπλές ζώνες)
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

        # Βελτιστοποίηση: Ελαχιστοποίηση των συνολικών ωρών εργασίας
        # Εξασφαλίζει ότι το σύστημα βάζει ακριβώς όσα άτομα ζητήθηκαν, αποφεύγοντας περιττή υπεραριθμία
        total_hours_sum = sum(x[(e["id"], d, h)] for e in st.session_state.employees for d in DAYS for h in range(11, 25))
        model.Minimize(total_hours_sum)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10.0
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            st.success("🎉 Το πρόγραμμα υπολογίστηκε επιτυχώς με βάρδιες 5-10 ωρών και ακριβή κάλυψη των ζωνών!")
            
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
            st.error("❌ Αδύνατη η εύρεση λύσης! Ελέγξτε αν οι απαιτήσεις σε προσωπικό υπερβαίνουν τα διαθέσιμα άτομα ή τα κωλύματα που δηλώθηκαν.")

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