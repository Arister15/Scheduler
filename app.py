import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model

st.set_page_config(page_title="Shift Scheduler Pro", layout="wide")
st.title("📋 Αυτόματο Πρόγραμμα Βαρδιών")

DAYS = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]
ROLES = ["Service", "Bar", "Υποδοχή"]
HOURS = list(range(11, 26))  # 11:00 έως 25 (01:00)

def format_hour(h):
    """Μετατρέπει τον αριθμό ώρας σε μορφή hh:00 (π.χ. 24 -> 00:00, 25 -> 01:00)."""
    if h < 24:
        return f"{h:02d}:00"
    elif h == 24:
        return "00:00"
    else:
        return "01:00"

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
            # Αποθήκευση κωλυμάτων ανά συγκεκριμένη ημέρα
            "unavailability": {
                d: {"status": "available", "start": 11, "end": 17} for d in DAYS
            }
        }
        for i, name in enumerate(STAFF_NAMES)
    ]
else:
    # Αυτόματη μετατροπή αν υπήρχε παλαιότερη δομή κωλυμάτων
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
# TAB 1: ΚΑΡΤΕΛΑ ΥΠΑΛΛΗΛΟΥ (CUSTOM ΩΡΕΣ ΑΝΑ ΗΜΕΡΑ)
# ---------------------------------------------------------
with tab1:
    st.subheader("Δήλωση Στοιχείων & Διαθεσιμότητας")
    
    emp_names = [e["name"] for e in st.session_state.employees]
    selected_name = st.selectbox("Επιλέξτε το όνομά σας:", emp_names)
    emp = next(e for e in st.session_state.employees if e["name"] == selected_name)

    col_role, col_marine, col_shifts = st.columns(3)
    with col_role:
        emp["role"] = st.selectbox("Πόστο εργασίας:", ROLES, index=ROLES.index(emp["role"]), key=f"role_{emp['id']}")
    with col_marine:
        emp["is_marine"] = st.checkbox("Ναυτολογημένος/η", value=emp["is_marine"], key=f"marine_{emp['id']}")
    with col_shifts:
        emp["target_shifts"] = st.slider("Επιθυμητά μεροκάματα εβδομάδας:", 1, 7, emp["target_shifts"], key=f"shifts_{emp['id']}")

    st.divider()
    st.markdown("#### 📅 Διαθεσιμότητα ανά Ημέρα")
    st.caption("Ορίστε ξεχωριστά για κάθε ημέρα αν είστε διαθέσιμος/η, αν έχετε ρεπό, ή τις συγκεκριμένες ώρες κωλύματος:")

    STATUS_OPTS = ["🟢 Διαθέσιμος/η", "🔴 Όλη μέρα μη διαθέσιμος/η (Ρεπό)", "🟡 Κώλυμα συγκεκριμένες ώρες"]
    status_to_code = {STATUS_OPTS[0]: "available", STATUS_OPTS[1]: "all_day", STATUS_OPTS[2]: "custom"}
    code_to_status = {v: k for k, v in status_to_code.items()}

    # Ανεξάρτητη ρύθμιση για κάθε ημέρα της εβδομάδας
    for d in DAYS:
        cur_day_data = emp["unavailability"][d]
        cur_status = code_to_status.get(cur_day_data["status"], STATUS_OPTS[0])
        
        # Εμφάνιση badge κατάστασης στον τίτλο
        if cur_day_data["status"] == "available":
            badge = "🟢 Διαθέσιμος/η"
        elif cur_day_data["status"] == "all_day":
            badge = "🔴 Ρεπό (Όλη μέρα)"
        else:
            badge = f"🟡 Κώλυμα: {format_hour(cur_day_data['start'])} - {format_hour(cur_day_data['end'])}"

        with st.expander(f"**{d}** — {badge}", expanded=(cur_day_data["status"] != "available")):
            c_choice, c_slider = st.columns([1.5, 2.5])
            
            with c_choice:
                selected_status = st.radio(
                    f"Κατάσταση για {d}:",
                    STATUS_OPTS,
                    index=STATUS_OPTS.index(cur_status),
                    key=f"status_{emp['id']}_{d}"
                )
                emp["unavailability"][d]["status"] = status_to_code[selected_status]

            with c_slider:
                if selected_status == "🟡 Κώλυμα συγκεκριμένες ώρες":
                    u_range = st.select_slider(
                        f"Ώρες που ΔΕΝ μπορείτε ({d}):",
                        options=HOURS,
                        value=(cur_day_data.get("start", 11), cur_day_data.get("end", 17)),
                        format_func=format_hour,
                        key=f"slider_{emp['id']}_{d}"
                    )
                    emp["unavailability"][d]["start"] = u_range[0]
                    emp["unavailability"][d]["end"] = u_range[1]
                elif selected_status == "🔴 Όλη μέρα μη διαθέσιμος/η (Ρεπό)":
                    st.info("Δεν θα σας ανατεθεί βάρδια αυτή την ημέρα.")
                else:
                    st.success("Πλήρως διαθέσιμος/η για εργασία.")

    st.write("")
    if st.button("🗑️ Καθαρισμός Όλων των Κωλυμάτων (Reset)"):
        for d in DAYS:
            emp["unavailability"][d] = {"status": "available", "start": 11, "end": 17}
            st.session_state[f"status_{emp['id']}_{d}"] = STATUS_OPTS[0]
            if f"slider_{emp['id']}_{d}" in st.session_state:
                st.session_state[f"slider_{emp['id']}_{d}"] = (11, 17)
        st.success(f"Όλα τα κωλύματα του/της {emp['name']} μηδενίστηκαν!")
        st.rerun()

# ---------------------------------------------------------
# TAB 2: ΡΥΘΜΙΣΕΙΣ MANAGER (CUSTOM ΖΩΝΕΣ)
# ---------------------------------------------------------
with tab2:
    st.subheader("Διαχείριση Ζωνών & Αναγκών Προσωπικού")
    st.caption("Ορίστε δυναμικά πόσα άτομα χρειάζονται ανά ώρα, ημέρα και πόστο.")

    if st.session_state.zones:
        display_zones = []
        for z in st.session_state.zones:
            display_zones.append({
                "ID": z["id"],
                "Ημέρα": z["day"],
                "Πόστο": z["role"],
                "Από": format_hour(z["start"]),
                "Έως": format_hour(z["end"]),
                "Ελάχιστο Προσωπικό": z["min_staff"],
                "Υποχρεωτικός Ναυτολογημένος": "Ναι" if z["require_marine"] else "Όχι"
            })
        st.dataframe(pd.DataFrame(display_zones), use_container_width=True, hide_index=True)

    col_add, col_edit_del = st.columns(2)

    with col_add:
        with st.expander("➕ Προσθήκη Νέας Ζώνης", expanded=False):
            with st.form("add_zone_form"):
                new_day = st.selectbox("Ημέρα:", ["Όλες"] + DAYS)
                new_role = st.selectbox("Πόστο:", ROLES)
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
                        "role": new_role,
                        "start": new_start,
                        "end": new_end,
                        "min_staff": new_min_staff,
                        "require_marine": new_require_marine
                    })
                    st.success("Η ζώνη προστέθηκε επιτυχώς!")
                    st.rerun()

    with col_edit_del:
        with st.expander("✏️ Επεξεργασία / Διαγραφή Ζώνης", expanded=False):
            if st.session_state.zones:
                zone_ids = [z["id"] for z in st.session_state.zones]
                sel_zone_id = st.selectbox("Επιλέξτε ID Ζώνης:", zone_ids)
                zone_to_edit = next(z for z in st.session_state.zones if z["id"] == sel_zone_id)

                with st.form("edit_zone_form"):
                    ed_day = st.selectbox("Ημέρα:", ["Όλες"] + DAYS, index=(["Όλες"] + DAYS).index(zone_to_edit["day"]))
                    ed_role = st.selectbox("Πόστο:", ROLES, index=ROLES.index(zone_to_edit["role"]))
                    ed_start, ed_end = st.select_slider(
                        "Ωράριο Ζώνης:",
                        options=HOURS,
                        value=(zone_to_edit["start"], zone_to_edit["end"]),
                        format_func=format_hour
                    )
                    ed_min_staff = st.number_input("Ελάχιστα απαιτούμενα άτομα:", min_value=1, max_value=10, value=zone_to_edit["min_staff"])
                    ed_require_marine = st.checkbox("Απαιτείται τουλάχιστον 1 ναυτολογημένος", value=zone_to_edit["require_marine"])

                    col_save, col_del = st.columns(2)
                    save_clicked = col_save.form_submit_button("💾 Ενημέρωση")
                    del_clicked = col_del.form_submit_button("❌ Διαγραφή")

                    if save_clicked:
                        zone_to_edit["day"] = ed_day
                        zone_to_edit["role"] = ed_role
                        zone_to_edit["start"] = ed_start
                        zone_to_edit["end"] = ed_end
                        zone_to_edit["min_staff"] = ed_min_staff
                        zone_to_edit["require_marine"] = ed_require_marine
                        st.success(f"Η ζώνη #{sel_zone_id} ενημερώθηκε!")
                        st.rerun()

                    if del_clicked:
                        st.session_state.zones = [z for z in st.session_state.zones if z["id"] != sel_zone_id]
                        st.warning(f"Η ζώνη #{sel_zone_id} διαγράφηκε!")
                        st.rerun()

# ---------------------------------------------------------
# TAB 3: ΕΠΙΛΥΣΗ ΚΑΙ EDITABLE ΤΕΛΙΚΟ ΠΡΟΓΡΑΜΜΑ
# ---------------------------------------------------------
with tab3:
    st.subheader("Αυτόματη Δημιουργία & Επεξεργασία Προγράμματος")

    if st.button("🚀 Υπολογισμός Προγράμματος (OR-Tools)"):
        model = cp_model.CpModel()
        
        # x[(emp_id, day, hour)]: 1 αν εργάζεται τη συγκεκριμένη ώρα
        x = {}
        for e in st.session_state.employees:
            for d in DAYS:
                for h in range(11, 25):  # 11:00 έως 01:00
                    x[(e["id"], d, h)] = model.NewBoolVar(f"x_{e['id']}_{d}_{h}")

        # works_day[(emp_id, day)]: 1 αν κάνει μεροκάματο
        works_day = {}
        for e in st.session_state.employees:
            for d in DAYS:
                works_day[(e["id"], d)] = model.NewBoolVar(f"works_{e['id']}_{d}")
                hours_worked = [x[(e["id"], d, h)] for h in range(11, 25)]
                model.Add(sum(hours_worked) >= 1).OnlyEnforceIf(works_day[(e["id"], d)])
                model.Add(sum(hours_worked) == 0).OnlyEnforceIf(works_day[(e["id"], d)].Not())

            # Περιορισμός μέγιστων μεροκάματων
            model.Add(sum(works_day[(e["id"], d)] for d in DAYS) <= e["target_shifts"])

            # Περιορισμοί Κωλυμάτων ανά Ημέρα
            for d, u_info in e["unavailability"].items():
                if u_info["status"] == "all_day":
                    for h in range(11, 25):
                        model.Add(x[(e["id"], d, h)] == 0)
                elif u_info["status"] == "custom":
                    for h in range(u_info["start"], u_info["end"]):
                        if h in range(11, 25):
                            model.Add(x[(e["id"], d, h)] == 0)

            # Συνεχόμενο ωράριο & όρια βάρδιας (4 έως 8 ώρες)
            for d in DAYS:
                daily_h = [x[(e["id"], d, h)] for h in range(11, 25)]
                model.Add(sum(daily_h) <= 8)
                model.Add(sum(daily_h) >= 4).OnlyEnforceIf(works_day[(e["id"], d)])

                starts = []
                for i, h in enumerate(range(11, 25)):
                    start_var = model.NewBoolVar(f"start_{e['id']}_{d}_{h}")
                    if i == 0:
                        model.Add(start_var == x[(e["id"], d, h)])
                    else:
                        model.Add(start_var >= x[(e["id"], d, h)] - x[(e["id"], d, h - 1)])
                    starts.append(start_var)
                model.Add(sum(starts) <= 1)

        # Επιβολή Custom Ζωνών Manager
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

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10.0
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            st.success("🎉 Το πρόγραμμα υπολογίστηκε επιτυχώς!")
            
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
            st.error("❌ Αδύνατη η εύρεση λύσης! Ελέγξτε αν οι απαιτήσεις υπερβαίνουν τα διαθέσιμα άτομα ή τα κωλύματα που δηλώθηκαν.")

    # ---------------------------------------------------------
    # EDITABLE TABLE & LIVE PREVIEW
    # ---------------------------------------------------------
    if st.session_state.schedule_df is not None:
        st.divider()
        st.markdown("### ✏️ Ζωντανή Επεξεργασία Προγράμματος (Live Editor)")
        st.info("💡 **Κάντε διπλό κλικ σε οποιοδήποτε κελί** για να αλλάξετε εργαζόμενο, πόστο ή ώρες. Μπορείτε επίσης να προσθέσετε γραμμές (`+`) ή να διαγράψετε.")

        # Editable Data Table
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
                "Σύνολο Ωρών": st.column_config.NumberColumn("Σύνολο Ωρών", min_value=1, max_value=14, step=1)
            },
            key="final_schedule_editor"
        )
        st.session_state.schedule_df = edited_df

        # Κουμπί Λήψης CSV
        csv_data = edited_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 Λήψη Προγράμματος σε Excel / CSV",
            data=csv_data,
            file_name="programma_vardion.csv",
            mime="text/csv"
        )

        # Καθημερινή προβολή βασισμένη στις αλλαγές του manager
        st.markdown("#### 📅 Αναλυτική Προβολή ανά Ημέρα")
        for d in DAYS:
            day_df = edited_df[edited_df["Ημέρα"] == d]
            if not day_df.empty:
                with st.expander(f"📅 {d} ({len(day_df)} βάρδιες)", expanded=False):
                    st.dataframe(day_df[["Εργαζόμενος", "Πόστο", "Ναυτολογημένος", "Έναρξη", "Λήξη", "Σύνολο Ωρών"]], use_container_width=True, hide_index=True)