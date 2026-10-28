import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model

st.set_page_config(page_title="Shift Scheduler Pro", layout="wide")
st.title("📋 Αυτόματο Πρόγραμμα Βαρδιών")

DAYS = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]
ROLES = ["Service", "Bar", "Υποδοχή"]
HOURS = list(range(11, 26))  # 11:00 έως 25 (01:00)

def format_hour(h):
    """Μετατρέπει τον αριθμό ώρας σε μορφή hh:00 (π.χ. 25 -> 01:00)."""
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
            "unavailability": []
        }
        for i, name in enumerate(STAFF_NAMES)
    ]

if "zones" not in st.session_state:
    st.session_state.zones = [
        {"id": 1, "day": "Όλες", "role": "Service", "start": 11, "end": 18, "min_staff": 2, "require_marine": False},
        {"id": 2, "day": "Όλες", "role": "Service", "start": 18, "end": 25, "min_staff": 3, "require_marine": True},
        {"id": 3, "day": "Όλες", "role": "Bar", "start": 11, "end": 18, "min_staff": 1, "require_marine": True},
        {"id": 4, "day": "Όλες", "role": "Bar", "start": 18, "end": 25, "min_staff": 2, "require_marine": True},
        {"id": 5, "day": "Όλες", "role": "Υποδοχή", "start": 19, "end": 24, "min_staff": 1, "require_marine": False},
    ]

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
        emp["role"] = st.selectbox("Πόστο εργασίας:", ROLES, index=ROLES.index(emp["role"]))
    with col_marine:
        emp["is_marine"] = st.checkbox("Ναυτολογημένος/η", value=emp["is_marine"])
    with col_shifts:
        emp["target_shifts"] = st.slider("Επιθυμητά μεροκάματα εβδομάδας:", 1, 7, emp["target_shifts"])

    st.divider()
    st.markdown("#### Καταχώρηση Κωλυμάτων (Ώρες που ΔΕΝ μπορείτε)")

    # Πολλαπλή επιλογή ημερών
    selected_days = st.multiselect("Επιλέξτε ημέρες κωλύματος:", DAYS, default=[])
    
    # Χρήση select_slider για αποφυγή του TypeError
    u_start, u_end = st.select_slider(
        "Χρονικό διάστημα κωλύματος:",
        options=HOURS,
        value=(11, 16),
        format_func=format_hour
    )

    col_btn_add, col_btn_reset = st.columns([1, 1])
    with col_btn_add:
        if st.button("➕ Προσθήκη Κωλύματος για τις επιλεγμένες ημέρες"):
            if not selected_days:
                st.warning("Παρακαλώ επιλέξτε τουλάχιστον μία ημέρα.")
            else:
                for day in selected_days:
                    if (day, u_start, u_end) not in emp["unavailability"]:
                        emp["unavailability"].append((day, u_start, u_end))
                st.success(f"Καταχωρήθηκαν {len(selected_days)} κωλύματα για: {format_hour(u_start)} - {format_hour(u_end)}!")

    with col_btn_reset:
        if st.button("🗑️ Καθαρισμός Όλων των Κωλυμάτων (Reset)"):
            emp["unavailability"] = []
            st.info("Όλα τα κωλύματά σας διαγράφηκαν.")

    if emp["unavailability"]:
        st.markdown("**Ενεργά κωλύματα:**")
        unavail_data = [{"Ημέρα": d, "Από": format_hour(s), "Έως": format_hour(e)} for d, s, e in emp["unavailability"]]
        st.table(pd.DataFrame(unavail_data))
    else:
        st.caption("Δεν υπάρχουν καταχωρημένα κωλύματα για τον συγκεκριμένο εργαζόμενο.")

# ---------------------------------------------------------
# TAB 2: ΡΥΘΜΙΣΕΙΣ MANAGER (CUSTOM ΖΩΝΕΣ & ΠΟΣΤΑ)
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
        st.dataframe(pd.DataFrame(display_zones), use_container_width=True)

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
# TAB 3: ΕΠΙΛΥΣΗ ΜΕ GOOGLE OR-TOOLS
# ---------------------------------------------------------
with tab3:
    st.subheader("Αυτόματη Δημιουργία Προγράμματος")

    if st.button("🚀 Υπολογισμός Προγράμματος (OR-Tools)"):
        model = cp_model.CpModel()
        
        # x[(emp_id, day, hour)]: 1 αν εργάζεται τη συγκεκριμένη ώρα
        x = {}
        for e in st.session_state.employees:
            for d in DAYS:
                for h in range(11, 25):  # 14 ωριαίες θυρίδες (11:00 έως 01:00)
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

            # Περιορισμός κωλυμάτων
            for u_day, u_start, u_end in e["unavailability"]:
                for h in range(u_start, u_end):
                    if h in range(11, 25):
                        model.Add(x[(e["id"], u_day, h)] == 0)

            # Συνεχόμενο ωράριο (όχι σπαστά) & όρια βάρδιας (4 έως 8 ώρες)
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
            st.success("🎉 Το πρόγραμμα υπολογίστηκε επιτυχώς χωρίς καμία παραβίαση κανόνα!")
            
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
                            "Ωράριο": f"{format_hour(start_h)} - {format_hour(end_h)}",
                            "Σύνολο Ωρών": len(worked)
                        })

            df_res = pd.DataFrame(results)
            st.dataframe(df_res, use_container_width=True)

            st.markdown("#### Αναλυτικό Πρόγραμμα ανά Ημέρα")
            for d in DAYS:
                day_df = df_res[df_res["Ημέρα"] == d]
                if not day_df.empty:
                    with st.expander(f"📅 {d} ({len(day_df)} άτομα)", expanded=True):
                        st.table(day_df[["Εργαζόμενος", "Πόστο", "Ναυτολογημένος", "Ωράριο", "Σύνολο Ωρών"]])
        else:
            st.error("❌ Αδύνατη η εύρεση λύσης! Οι απαιτήσεις προσωπικού υπερβαίνουν τα διαθέσιμα άτομα ή τα κωλύματα που δηλώθηκαν. Δοκιμάστε να μειώσετε τα ελάχιστα άτομα σε κάποιες ζώνες.")