import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model

st.set_page_config(page_title="Shift Scheduler", layout="wide")
st.title("📋 Αυτόματο Πρόγραμμα Βαρδιών")

DAYS = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]
HOURS = list(range(11, 25))

# Mock Προσωπικό (Σε πραγματικό app αποθηκεύεται σε βάση)
if "employees" not in st.session_state:
    st.session_state.employees = [
        {"id": 1, "name": "Γιάννης", "role": "service", "is_marine": True, "target_shifts": 5, "unavailability": []},
        {"id": 2, "name": "Μαρία", "role": "service", "is_marine": False, "target_shifts": 4, "unavailability": []},
        {"id": 3, "name": "Κώστας", "role": "service", "is_marine": True, "target_shifts": 5, "unavailability": []},
        {"id": 4, "name": "Ελένη", "role": "service", "is_marine": False, "target_shifts": 4, "unavailability": []},
        {"id": 5, "name": "Νίκος", "role": "bar", "is_marine": True, "target_shifts": 5, "unavailability": []},
        {"id": 6, "name": "Πέτρος", "role": "bar", "is_marine": False, "target_shifts": 4, "unavailability": []},
        {"id": 7, "name": "Άννα", "role": "bar", "is_marine": True, "target_shifts": 5, "unavailability": []},
    ]

tab1, tab2, tab3 = st.tabs(["👤 Καρτέλα Υπαλλήλου", "⚙️ Ρυθμίσεις Manager", "📅 Τελικό Πρόγραμμα"])

# ----------------- TAB 1: ΥΠΑΛΛΗΛΟΣ -----------------
with tab1:
    st.subheader("Δήλωση Διαθεσιμότητας & Μεροκάματων")
    emp_names = [e["name"] for e in st.session_state.employees]
    selected_name = st.selectbox("Επιλέξτε το όνομά σας:", emp_names)
    emp = next(e for e in st.session_state.employees if e["name"] == selected_name)
    
    emp["target_shifts"] = st.slider("Επιθυμητά μεροκάματα εβδομάδας:", 1, 7, emp["target_shifts"])
    
    st.markdown("**Μη διαθέσιμες ώρες:**")
    u_day = st.selectbox("Ημέρα κωλύματος:", DAYS)
    u_start, u_end = st.slider("Χρονικό διάστημα (11:00 - 01:00):", 11, 25, (11, 15))
    
    if st.button("Προσθήκη Κωλύματος"):
        emp["unavailability"].append((u_day, u_start, u_end))
        st.success(f"Καταχωρήθηκε κώλυμα: {u_day} {u_start}:00 - {u_end}:00")

# ----------------- TAB 2: MANAGER -----------------
with tab2:
    st.subheader("Απαιτήσεις Προσωπικού ανά Ζώνη")
    st.info("Ρύθμιση ελάχιστου προσωπικού για Service και Bar")
    
    # Custom ρυθμίσεις Manager
    s_mid_min = st.number_input("Service: 13:00-18:00 (Ελάχιστα άτομα)", min_value=1, value=2)
    s_night_min = st.number_input("Service: 18:00-01:00 (Ελάχιστα άτομα)", min_value=1, value=3)
    b_night_min = st.number_input("Bar: 18:00-01:00 (Ελάχιστα άτομα)", min_value=1, value=2)

# ----------------- TAB 3: ΕΠΙΛΥΣΗ & ΠΡΟΓΡΑΜΜΑ -----------------
with tab3:
    if st.button("🚀 Υπολογισμός Προγράμματος"):
        model = cp_model.CpModel()
        x = {}
        for e in st.session_state.employees:
            for d in DAYS:
                for h in HOURS:
                    x[(e["id"], d, h)] = model.NewBoolVar(f"x_{e['id']}_{d}_{h}")

        works_day = {}
        for e in st.session_state.employees:
            for d in DAYS:
                works_day[(e["id"], d)] = model.NewBoolVar(f"works_{e['id']}_{d}")
                hours_worked = [x[(e["id"], d, h)] for h in HOURS]
                model.Add(sum(hours_worked) >= 1).OnlyEnforceIf(works_day[(e["id"], d)])
                model.Add(sum(hours_worked) == 0).OnlyEnforceIf(works_day[(e["id"], d)].Not())
            
            # Μέγιστα μεροκάματα
            model.Add(sum([works_day[(e["id"], d)] for d in DAYS]) <= e["target_shifts"])
            
            # Κωλύματα
            for (u_day, u_start, u_end) in e["unavailability"]:
                for h in range(u_start, u_end):
                    if h in HOURS:
                        model.Add(x[(e["id"], u_day, h)] == 0)

        # Βάρδιες & κάλυψη
        for d in DAYS:
            for h in HOURS:
                # Service κάλυψη
                srv = [x[(e["id"], d, h)] for e in st.session_state.employees if e["role"] == "service"]
                min_s = s_night_min if h >= 18 else (s_mid_min if h >= 13 else 1)
                model.Add(sum(srv) >= min_s)
                
                # Bar κάλυψη
                bar = [x[(e["id"], d, h)] for e in st.session_state.employees if e["role"] == "bar"]
                min_b = b_night_min if h >= 18 else 1
                model.Add(sum(bar) >= min_b)

        solver = cp_model.CpSolver()
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            st.success("Το πρόγραμμα δημιουργήθηκε επιτυχώς!")
            results = []
            for d in DAYS:
                for e in st.session_state.employees:
                    worked = [h for h in HOURS if solver.Value(x[(e["id"], d, h)]) == 1]
                    if worked:
                        results.append({
                            "Ημέρα": d,
                            "Εργαζόμενος": e["name"],
                            "Πόστο": e["role"].upper(),
                            "Ναυτολογημένος": "Ναι" if e["is_marine"] else "Όχι",
                            "Έναρξη": f"{min(worked):02d}:00",
                            "Λήξη": f"{max(worked)+1:02d}:00",
                            "Σύνολο Ωρών": len(worked)
                        })
            st.dataframe(pd.DataFrame(results), use_container_width=True)
        else:
            st.error("Αδύνατη η επίλυση με αυτούς τους περιορισμούς. Μειώστε τις απαιτήσεις ή αυξήστε τη διαθεσιμότητα.")