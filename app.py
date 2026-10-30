import streamlit as st  
import pandas as pd  
import json  
import os  
import io  
import math  
import copy  
from ortools.sat.python import cp_model  
import openpyxl  
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side  
  
st.set_page_config(page_title="Shift Scheduler Pro", layout="wide")  
st.title("📋 Αυτόματο Πρόγραμμα Βαρδιών")  
  
DAYS = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]  
ROLES = ["Bar", "Service", "Υποδοχή"]  
HOURS = list(range(11, 26))  # 11:00 έως 25 (01:00)  
DATA_FILE = "scheduler_data.json"  

# ---------------------------------------------------------  
# ΠΡΟΚΑΘΟΡΙΣΜΕΝΟ ΠΡΟΣΩΠΙΚΟ & ΡΟΛΟΙ
# ---------------------------------------------------------  
DEFAULT_STAFF_CONFIG = [
    # Bar
    {"name": "Άρης", "role": "Bar", "is_marine": False, "target_shifts": 5},
    {"name": "Βαγγέλης", "role": "Bar", "is_marine": False, "target_shifts": 5},
    {"name": "Γιάννης", "role": "Bar", "is_marine": True, "target_shifts": 5},
    {"name": "Κώστας", "role": "Bar", "is_marine": True, "target_shifts": 6},
    # Service
    {"name": "Φωτεινή", "role": "Service", "is_marine": True, "target_shifts": 5},
    {"name": "Μαρία", "role": "Service", "is_marine": False, "target_shifts": 5},
    {"name": "Θεόφιλος", "role": "Service", "is_marine": True, "target_shifts": 6},
    {"name": "Σαλώμη", "role": "Service", "is_marine": False, "target_shifts": 5},
    # Υποδοχή (δεν επηρεάζεται από ναυτολόγηση)
    {"name": "Ευαγγελία", "role": "Υποδοχή", "is_marine": False, "target_shifts": 5},
    {"name": "Faith", "role": "Υποδοχή", "is_marine": False, "target_shifts": 5},
    {"name": "Ραφαήλ", "role": "Υποδοχή", "is_marine": False, "target_shifts": 5},
    {"name": "Kaba", "role": "Υποδοχή", "is_marine": False, "target_shifts": 5},
]
  
STANDARD_SLOTS = [  
    {"label": "11:00 - 18:00", "start": 11, "end": 18, "duration": 7},  
    {"label": "18:00 - 22:00", "start": 18, "end": 22, "duration": 4},  
    {"label": "22:00 - 01:00", "start": 22, "end": 25, "duration": 3}  
]  
  
def format_hour(h):  
    if h < 24:  
        return f"{h:02d}:00"  
    elif h == 24:  
        return "00:00"  
    else:  
        return "01:00"  
  
def get_slot_bounds(slot_str):  
    for s in STANDARD_SLOTS:  
        if s["label"] == slot_str:  
            return s["start"], s["end"], s["duration"]  
    try:
        parts = slot_str.split(" - ")  
        s_val = int(parts[0].split(":")[0])  
        e_raw = parts[1].split(":")[0]  
        e_val = 25 if e_raw in ["01", "1"] else (24 if e_raw in ["00", "0"] else int(e_raw))  
        return s_val, e_val, (e_val - s_val)  
    except Exception:
        return 11, 18, 7
  
# ---------------------------------------------------------  
# ΑΡΧΙΚΗ ΒΑΣΗ ΖΩΝΩΝ  
# ---------------------------------------------------------  
def get_initial_base_matrix():  
    return [  
        # Bar  
        {"Πόστο": "Bar", "Ωράριο": "11:00 - 18:00", "⚓ Ναυτολόγηση": "Όχι", "Δευτέρα": 1, "Τρίτη": 1, "Τετάρτη": 1, "Πέμπτη": 1, "Παρασκευή": 1, "Σάββατο": 1, "Κυριακή": 1},  
        {"Πόστο": "Bar", "Ωράριο": "18:00 - 22:00", "⚓ Ναυτολόγηση": "Όλες τις ημέρες", "Δευτέρα": 2, "Τρίτη": 2, "Τετάρτη": 2, "Πέμπτη": 2, "Παρασκευή": 2, "Σάββατο": 2, "Κυριακή": 2},  
        {"Πόστο": "Bar", "Ωράριο": "22:00 - 01:00", "⚓ Ναυτολόγηση": "Όλες τις ημέρες", "Δευτέρα": 1, "Τρίτη": 1, "Τετάρτη": 1, "Πέμπτη": 1, "Παρασκευή": 1, "Σάββατο": 1, "Κυριακή": 1},  
        # Service  
        {"Πόστο": "Service", "Ωράριο": "11:00 - 18:00", "⚓ Ναυτολόγηση": "Όχι", "Δευτέρα": 1, "Τρίτη": 1, "Τετάρτη": 1, "Πέμπτη": 1, "Παρασκευή": 1, "Σάββατο": 1, "Κυριακή": 1},  
        {"Πόστο": "Service", "Ωράριο": "18:00 - 22:00", "⚓ Ναυτολόγηση": "Όλες τις ημέρες", "Δευτέρα": 2, "Τρίτη": 2, "Τετάρτη": 2, "Πέμπτη": 2, "Παρασκευή": 2, "Σάββατο": 2, "Κυριακή": 2},  
        {"Πόστο": "Service", "Ωράριο": "22:00 - 01:00", "⚓ Ναυτολόγηση": "Όλες τις ημέρες", "Δευτέρα": 1, "Τρίτη": 1, "Τετάρτη": 1, "Πέμπτη": 1, "Παρασκευή": 1, "Σάββατο": 1, "Κυριακή": 1},  
        # Υποδοχή  
        {"Πόστο": "Υποδοχή", "Ωράριο": "11:00 - 18:00", "⚓ Ναυτολόγηση": "Όχι", "Δευτέρα": 1, "Τρίτη": 1, "Τετάρτη": 1, "Πέμπτη": 1, "Παρασκευή": 1, "Σάββατο": 1, "Κυριακή": 1},  
        {"Πόστο": "Υποδοχή", "Ωράριο": "18:00 - 22:00", "⚓ Ναυτολόγηση": "Όχι", "Δευτέρα": 1, "Τρίτη": 1, "Τετάρτη": 1, "Πέμπτη": 1, "Παρασκευή": 2, "Σάββατο": 2, "Κυριακή": 1},  
        {"Πόστο": "Υποδοχή", "Ωράριο": "22:00 - 01:00", "⚓ Ναυτολόγηση": "Όχι", "Δευτέρα": 1, "Τρίτη": 1, "Τετάρτη": 1, "Πέμπτη": 1, "Παρασκευή": 1, "Σάββατο": 1, "Κυριακή": 1},  
    ]  
  
def build_default_employees():
    return [
        {
            "id": i + 1,
            "name": cfg["name"],
            "role": cfg["role"],
            "is_marine": cfg["is_marine"],
            "target_shifts": cfg["target_shifts"],
            "unavailability": {d: {"status": "available", "start": 11, "end": 17} for d in DAYS}
        }
        for i, cfg in enumerate(DEFAULT_STAFF_CONFIG)
    ]

# ---------------------------------------------------------  
# ΜΟΝΙΜΗ ΑΠΟΘΗΚΕΥΣΗ (JSON) ΜΕ ΑΣΦΑΛΕΣ TYPE SANITIZATION  
# ---------------------------------------------------------  
def sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    elif hasattr(obj, "item"):
        return obj.item()
    return obj

def load_persistent_data():  
    if os.path.exists(DATA_FILE):  
        try:  
            with open(DATA_FILE, "r", encoding="utf-8") as f:  
                data = json.load(f)  
                if "employees" in data and "base_matrix" in data:  
                    emps = data["employees"]
                    # Έλεγχος αν υπάρχει ο Kaba στο αρχείο, αλλιώς αυτόματη μετάπτωση στα νέα defaults
                    emp_names = [e.get("name") for e in emps]
                    if "Kaba" in emp_names and len(emps) >= 12:
                        active = data.get("active_matrix", copy.deepcopy(data["base_matrix"]))  
                        return emps, data["base_matrix"], active  
        except Exception:  
            pass  
  
    default_employees = build_default_employees()  
    base_m = get_initial_base_matrix()  
    active_m = copy.deepcopy(base_m)  
    save_persistent_data(default_employees, base_m, active_m)  
    return default_employees, base_m, active_m  
  
def save_persistent_data(employees, base_matrix, active_matrix):  
    data = {  
        "employees": sanitize_for_json(employees),  
        "base_matrix": sanitize_for_json(base_matrix),  
        "active_matrix": sanitize_for_json(active_matrix)  
    }  
    with open(DATA_FILE, "w", encoding="utf-8") as f:  
        json.dump(data, f, ensure_ascii=False, indent=2)  
  
if "employees" not in st.session_state or "base_matrix" not in st.session_state:  
    loaded_emps, loaded_base, loaded_active = load_persistent_data()  
    st.session_state.employees = loaded_emps  
    st.session_state.base_matrix = loaded_base  
    st.session_state.active_matrix = loaded_active  
  
if "matrix_schedule" not in st.session_state:  
    st.session_state.matrix_schedule = None  
  
# ---------------------------------------------------------  
# ΥΠΟΛΟΓΙΣΜΟΣ KPIs  
# ---------------------------------------------------------  
def calculate_role_kpis(matrix, employees):  
    kpis = {}  
    for r in ROLES:  
        staff_r = [e for e in employees if e["role"] == r]  
        marines_r = [e for e in staff_r if e["is_marine"]]  
        role_rows = [row for row in matrix if row["Πόστο"] == r]  
  
        total_hours = 0  
        min_shifts_week = 0  
  
        for d in DAYS:  
            daily_hours = 0  
            closing_staff = 0  
            early_staff = 0  
  
            for row in role_rows:  
                s_val, e_val, dur = get_slot_bounds(row["Ωράριο"])  
                needed = int(row.get(d, 0))  
                daily_hours += (needed * dur)  
  
                if s_val == 11:  
                    early_staff = max(early_staff, needed)  
                if e_val == 25:  
                    closing_staff = max(closing_staff, needed)  
  
            total_hours += daily_hours  
            shifts_today = max(math.ceil(daily_hours / 8.0), closing_staff + early_staff)  
            min_shifts_week += shifts_today  
  
        avail_shifts = sum(e["target_shifts"] for e in staff_r)  
        avail_mar_shifts = sum(e["target_shifts"] for e in marines_r)  
  
        if avail_shifts < min_shifts_week:  
            status = "🔴 Έλλειψη Προσωπικού"  
            badge = "red"  
        elif avail_shifts == min_shifts_week:  
            status = "⚠️ Οριακό (0 Slack)"  
            badge = "orange"  
        else:  
            status = "🟢 Πλήρης Κάλυψη"  
            badge = "green"  
  
        kpis[r] = {  
            "staff_count": len(staff_r),  
            "marine_count": len(marines_r),  
            "hours": total_hours,  
            "needed_shifts": min_shifts_week,  
            "avail_shifts": avail_shifts,  
            "avail_mar_shifts": avail_mar_shifts,  
            "status": status,  
            "badge": badge  
        }  
    return kpis  

# ---------------------------------------------------------  
# CONVERT MATRIX TO SOLVER REQUIREMENTS  
# ---------------------------------------------------------  
def matrix_to_requirements(matrix):  
    reqs = []  
    for row in matrix:  
        role = row["Πόστο"]  
        s_val, e_val, _ = get_slot_bounds(row["Ωράριο"])  
        mar_rule = row.get("⚓ Ναυτολόγηση", "Όχι")  
  
        for d in DAYS:  
            staff_count = int(row.get(d, 0))  
            if staff_count > 0:  
                is_mar = False  
                if mar_rule == "Όλες τις ημέρες":  
                    is_mar = True  
                elif mar_rule == "Μόνο Παρ - Κυρ" and d in ["Παρασκευή", "Σάββατο", "Κυριακή"]:  
                    is_mar = True  
                elif mar_rule == "Μόνο Δευτ - Πεμ" and d in ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη"]:  
                    is_mar = True  
  
                reqs.append({  
                    "role": role,  
                    "day": d,  
                    "start": s_val,  
                    "end": e_val,  
                    "min_staff": staff_count,  
                    "require_marine": is_mar  
                })  
    return reqs  

# ---------------------------------------------------------  
# ΕΝΙΑΙΟΣ SOLVER (OR-TOOLS CP-SAT) ΜΕ ΚΟΙΝΗ ΝΑΥΤΟΛΟΓΗΣΗ  
# ---------------------------------------------------------  
def solve_full_schedule(employees, all_reqs, relax=None):  
    model = cp_model.CpModel()  
    
    x = {}  
    works_day = {}  
    
    for e in employees:  
        eid = e["id"]  
        for d in DAYS:  
            works_day[(eid, d)] = model.NewBoolVar(f"w_{eid}_{d}")  
            for h in range(11, 25):  
                x[(eid, d, h)] = model.NewBoolVar(f"x_{eid}_{d}_{h}")  
                
            daily_hours = [x[(eid, d, h)] for h in range(11, 25)]  
            model.Add(sum(daily_hours) >= 1).OnlyEnforceIf(works_day[(eid, d)])  
            model.Add(sum(daily_hours) == 0).OnlyEnforceIf(works_day[(eid, d)].Not())  
            
            # Μέγιστη διάρκεια βάρδιας 10 ώρες  
            model.Add(sum(daily_hours) <= 10)  
            
            # Ελάχιστη βάρδια (4 ώρες - επιτρέπει και 4ωρη απογευματινή 18-22)  
            if relax != "no_min_hours":  
                model.Add(sum(daily_hours) >= 4).OnlyEnforceIf(works_day[(eid, d)])  
                
            # Συνεχόμενο ωράριο (όχι σπαστό)  
            starts = []  
            for i, h in enumerate(range(11, 25)):  
                st_var = model.NewBoolVar(f"st_{eid}_{d}_{h}")  
                if i == 0:  
                    model.Add(st_var == x[(eid, d, h)])  
                else:  
                    model.Add(st_var >= x[(eid, d, h)] - x[(eid, d, h - 1)])  
                starts.append(st_var)  
            model.Add(sum(starts) <= 1)  
            
        # Διαθεσιμότητα / Κωλύματα  
        avail_count = sum(1 for d in DAYS if e["unavailability"][d]["status"] != "all_day")  
        
        if relax not in ("no_unavail", "compound_all"):  
            for d, u in e["unavailability"].items():  
                if u["status"] == "all_day":  
                    model.Add(works_day[(eid, d)] == 0)  
                    for h in range(11, 25):  
                        model.Add(x[(eid, d, h)] == 0)  
                elif u["status"] == "custom":  
                    for h in range(u["start"], u["end"]):  
                        if h in range(11, 25):  
                            model.Add(x[(eid, d, h)] == 0)  
                            
        # Περιορισμοί Μεροκάματων  
        # Κανόνας: Ναυτολογημένοι => 5+ μεροκάματα πάντα (εκτός αν έχουν δηλώσει πάνω από 2 ρεπό)
        if e["is_marine"] and e["role"] in ["Bar", "Service"]:  
            marine_min = min(5, avail_count)  
            marine_max = min(max(e["target_shifts"], 6), avail_count)  
            if relax not in ("no_min_shifts", "compound_shifts"):  
                model.Add(sum(works_day[(eid, d)] for d in DAYS) >= marine_min)  
            if relax not in ("no_max_shifts", "compound_shifts"):  
                model.Add(sum(works_day[(eid, d)] for d in DAYS) <= marine_max)  
        else:  
            eff_max = min(max(e["target_shifts"], 5), avail_count)  
            eff_min = max(0, min(e["target_shifts"] - 1, avail_count))  
            if relax not in ("no_min_shifts", "compound_shifts"):  
                model.Add(sum(works_day[(eid, d)] for d in DAYS) >= eff_min)  
            if relax not in ("no_max_shifts", "compound_shifts"):  
                model.Add(sum(works_day[(eid, d)] for d in DAYS) <= eff_max)  
                
    # 1. Κάλυψη Αναγκών ανά Πόστο & Ώρα  
    for r in ROLES:  
        staff_r = [e for e in employees if e["role"] == r]  
        reqs_r = [rq for rq in all_reqs if rq["role"] == r]  
        
        for d in DAYS:  
            for h in range(11, 25):  
                needed_staff = 0  
                for rq in reqs_r:  
                    if rq["day"] == d and rq["start"] <= h < rq["end"]:  
                        needed_staff = max(needed_staff, rq["min_staff"])  
                if needed_staff > 0:  
                    model.Add(sum(x[(e["id"], d, h)] for e in staff_r) >= needed_staff)  
                    
    # 2. Κανόνας Ναυτολογημένων (Bar + Service Κοινό Άθροισμα >= 2)  
    # "ναυτολογημένοι σε κάθε βάρδια πρεπει να ειναι 2 ατομα απο bar και service, δεν εχει σημασια αν ειναι 1 και 1 η 2 και 0 αρκει να ειναι 2 στο συνολο"  
    # "ναυτολογημενοι δεν μας ενδιαφερουν οσον αφορα την υποδοχη"  
    marines_bs = [e for e in employees if e["is_marine"] and e["role"] in ["Bar", "Service"]]  
    
    if relax not in ("no_marine", "compound_all"):  
        for d in DAYS:  
            for h in range(11, 25):  
                # Ελέγχουμε αν υπάρχει απαίτηση ναυτολόγησης σε Bar ή Service  
                marine_required_here = False  
                for rq in all_reqs:  
                    if rq["role"] in ["Bar", "Service"] and rq["day"] == d and rq["start"] <= h < rq["end"]:  
                        if rq["require_marine"]:  
                            marine_required_here = True  
                            break  
                if marine_required_here:  
                    model.Add(sum(x[(e["id"], d, h)] for e in marines_bs) >= 2)  
                    
    # Στόχος: Ελαχιστοποίηση συνολικών ωρών & διατήρηση ισορροπίας με τα target shifts  
    total_hours = sum(x[(e["id"], d, h)] for e in employees for d in DAYS for h in range(11, 25))  
    model.Minimize(total_hours)  
    
    solver = cp_model.CpSolver()  
    solver.parameters.max_time_in_seconds = 10.0  
    status = solver.Solve(model)  
    
    res = []  
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):  
        for d in DAYS:  
            for e in employees:  
                w = [h for h in range(11, 25) if solver.Value(x[(e["id"], d, h)]) == 1]  
                if w:  
                    res.append({  
                        "day": d,  
                        "name": e["name"],  
                        "role": e["role"],  
                        "is_marine": e["is_marine"],  
                        "shift": f"{format_hour(min(w))}-{format_hour(max(w) + 1)}",  
                        "start_h": min(w),  
                        "end_h": max(w) + 1  
                    })  
    return status, res  

# ---------------------------------------------------------  
# ΔΙΑΓΝΩΣΤΙΚΟΣ ΕΛΕΓΧΟΣ ΑΠΟΤΥΧΙΑΣ  
# ---------------------------------------------------------  
def diagnose_schedule_failure(employees, all_reqs, status):  
    reasons = []  
    if status == cp_model.UNKNOWN:  
        reasons.append("⏱️ **Χρονικό Όριο (Timeout):** Το πρόγραμμα είναι υπερβολικά περίπλοκο ή οριακό για τον solver.")  
        return reasons  
        
    # Έλεγχος ανά πόστο  
    for r in ROLES:  
        staff_r = [e for e in employees if e["role"] == r]  
        reqs_r = [rq for rq in all_reqs if rq["role"] == r]  
        if not staff_r and reqs_r:  
            reasons.append(f"❌ Κανένας εργαζόμενος καταχωρημένος στο πόστο **{r}**.")  
            
    # Έλεγχος επάρκειας ναυτολογημένων  
    marines = [e for e in employees if e["is_marine"] and e["role"] in ["Bar", "Service"]]  
    if len(marines) < 2:  
        reasons.append(f"⚓ **Έλλειψη Ναυτολογημένων:** Υπάρχουν μόνο {len(marines)} ναυτολογημένοι σε Bar/Service, ενώ απαιτούνται τουλάχιστον 2 ταυτόχρονα.")  
        
    st_no_mar, _ = solve_full_schedule(employees, all_reqs, relax="no_marine")  
    if st_no_mar in (cp_model.OPTIMAL, cp_model.FEASIBLE):  
        reasons.append("⚓ **Περιορισμός Ναυτολογημένων:** Το πρόγραμμα βγαίνει μόνο αν καταργηθεί η απαίτηση για 2 ναυτολογημένους ανά βάρδια (πιθανό κώλυμα ή ρεπό των ναυτολογημένων).")  
        
    st_no_unavail, _ = solve_full_schedule(employees, all_reqs, relax="no_unavail")  
    if st_no_unavail in (cp_model.OPTIMAL, cp_model.FEASIBLE):  
        reasons.append("🚫 **Σύγκρουση Κωλυμάτων/Ρεπό:** Τα δηλωμένα ρεπό συμπίπτουν σε ημέρες με αυξημένη ανάγκη προσωπικού.")  
        
    st_no_min_sh, _ = solve_full_schedule(employees, all_reqs, relax="no_min_shifts")  
    if st_no_min_sh in (cp_model.OPTIMAL, cp_model.FEASIBLE):  
        reasons.append("📉 **Κανόνας 5+ Μεροκάματων:** Δεν υπάρχουν αρκετές διαθέσιμες βάρδιες στο μαγαζί για να πάρουν όλοι οι ναυτολογημένοι τουλάχιστον 5 μεροκάματα.")  
        
    if not reasons:  
        reasons.append("⚠️ **Σύνθετη Σύγκρουση Περιορισμών:** Συνδυασμός ορίων ωρών (4-10 ώρες), συνεχόμενου ωραρίου και επικαλυπτόμενων βαρδιών.")  
        
    return reasons  

# ---------------------------------------------------------  
# ΕΓΧΡΩΜΟ EXCEL EXPORT  
# ---------------------------------------------------------  
def create_styled_excel(df):  
    wb = openpyxl.Workbook()  
    ws = wb.active  
    ws.title = "Πρόγραμμα Βαρδιών"  
  
    role_hex_colors = {  
        "Service": "FCE5CD",  
        "Bar": "CFE2F3",  
        "Υποδοχή": "FFF2CC"  
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
  
    headers = list(df.columns)  
    ws.append(headers)  
    for col_idx in range(1, len(headers) + 1):  
        cell = ws.cell(row=1, column=col_idx)  
        cell.font = header_font  
        cell.fill = header_fill  
        cell.alignment = Alignment(horizontal='center', vertical='center')  
        cell.border = thin_border  
  
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
  
    for col in ws.columns:  
        col_letter = col[0].column_letter  
        ws.column_dimensions[col_letter].width = 18  
  
    output = io.BytesIO()  
    wb.save(output)  
    output.seek(0)  
    return output  
  
tab1, tab2, tab3 = st.tabs(["👤 Καρτέλα Υπαλλήλου", "⚙️ Ρυθμίσεις Manager (Ζώνες)", "📅 Τελικό Πρόγραμμα"])  
  
# ---------------------------------------------------------  
# TAB 1: ΚΑΡΤΕΛΑ ΥΠΑΛΛΗΛΟΥ  
# ---------------------------------------------------------  
with tab1:  
    st.subheader("Δήλωση Στοιχείων & Διαθεσιμότητας")  
  
    with st.expander("👥 Διαχείριση Προσωπικού (Προσθήκη / Διαγραφή / Επαναφορά)", expanded=False):  
        c_add, c_del = st.columns(2)  
        with c_add:  
            st.markdown("##### ➕ Προσθήκη Νέου Υπαλλήλου")  
            with st.form("add_new_emp_form"):  
                new_name = st.text_input("Ονοματεπώνυμο:")  
                new_r = st.selectbox("Πόστο:", ROLES, key="add_emp_role")  
                new_mar = st.checkbox("Ναυτολογημένος/η (μόνο Bar/Service)", key="add_emp_marine")  
                new_sh = st.slider("Επιθυμητά μεροκάματα:", 1, 7, 5, key="add_emp_shifts")  
                  
                if st.form_submit_button("Αποθήκευση Υπαλλήλου"):  
                    if not new_name.strip():  
                        st.error("Εισάγετε όνομα.")  
                    elif any(e["name"].lower() == new_name.strip().lower() for e in st.session_state.employees):  
                        st.error("Υπάρχει ήδη υπάλληλος με αυτό το όνομα.")  
                    else:  
                        nid = max([e["id"] for e in st.session_state.employees], default=0) + 1  
                        is_actual_marine = new_mar if new_r in ["Bar", "Service"] else False
                        st.session_state.employees.append({  
                            "id": nid,  
                            "name": new_name.strip(),  
                            "role": new_r,  
                            "is_marine": is_actual_marine,  
                            "target_shifts": new_sh,  
                            "unavailability": {d: {"status": "available", "start": 11, "end": 17} for d in DAYS}  
                        })  
                        save_persistent_data(st.session_state.employees, st.session_state.base_matrix, st.session_state.active_matrix)  
                        st.success(f"Ο/Η {new_name} προστέθηκε επιτυχώς!")  
                        st.rerun()  
  
        with c_del:  
            st.markdown("##### 🗑️ Διαγραφή ή Επαναφορά")  
            if st.session_state.employees:  
                del_name = st.selectbox("Επιλέξτε υπάλληλο προς διαγραφή:", [e["name"] for e in st.session_state.employees], key="del_emp_select")  
                if st.button("❌ Οριστική Διαγραφή", type="secondary"):  
                    st.session_state.employees = [e for e in st.session_state.employees if e["name"] != del_name]  
                    save_persistent_data(st.session_state.employees, st.session_state.base_matrix, st.session_state.active_matrix)  
                    st.success(f"Ο/Η {del_name} διαγράφηκε!")  
                    st.rerun()  

            st.write("")
            if st.button("🔄 Επαναφορά Προεπιλεγμένων Εργαζομένων (Reset All)", type="secondary"):
                st.session_state.employees = build_default_employees()
                save_persistent_data(st.session_state.employees, st.session_state.base_matrix, st.session_state.active_matrix)
                st.success("Επανήλθαν οι 12 προεπιλεγμένοι εργαζόμενοι!")
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
        marine_disabled = (new_role == "Υποδοχή")
        marine_val = False if marine_disabled else emp["is_marine"]
        new_marine = st.checkbox("Ναυτολογημένος/η ⚓", value=marine_val, disabled=marine_disabled, key=f"ui_marine_{emp['id']}")  
        if marine_disabled:
            st.caption("ℹ️ Η υποδοχή δεν συμμετέχει σε ναυτολόγηση.")
    with col_shifts:  
        min_allowed_shifts = 5 if (new_marine and new_role in ["Bar", "Service"]) else 1
        new_shifts = st.slider("Επιθυμητά μεροκάματα εβδομάδας:", 1, 7, value=max(emp["target_shifts"], min_allowed_shifts), key=f"ui_shifts_{emp['id']}")  
        if new_marine:
            st.caption("⚓ Υποχρεωτικά 5+ μεροκάματα.")
  
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
            emp["is_marine"] = (new_marine and new_role in ["Bar", "Service"])  
            emp["target_shifts"] = new_shifts  
  
            for d in DAYS:  
                chosen_st = st.session_state.get(f"ui_status_{emp['id']}_{d}", STATUS_OPTS[0])  
                code = status_to_code[chosen_st]  
                slider_val = st.session_state.get(f"ui_slider_{emp['id']}_{d}", (11, 17))  
                emp["unavailability"][d] = {"status": code, "start": slider_val[0], "end": slider_val[1]}  
  
            save_persistent_data(st.session_state.employees, st.session_state.base_matrix, st.session_state.active_matrix)  
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
  
            save_persistent_data(st.session_state.employees, st.session_state.base_matrix, st.session_state.active_matrix)  
            st.info(f"Τα κωλύματα του/της {emp['name']} μηδενίστηκαν.")  
            st.rerun()  
  
# ---------------------------------------------------------  
# TAB 2: ΡΥΘΜΙΣΕΙΣ MANAGER  
# ---------------------------------------------------------  
with tab2:  
    st.subheader("Διαχείριση Αναγκών & Ζωνών Προσωπικού")  
  
    active_kpis = calculate_role_kpis(st.session_state.active_matrix, st.session_state.employees)  
    k1, k2, k3 = st.columns(3)  
    cols_k = [k1, k2, k3]  
    for idx, r in enumerate(ROLES):  
        kpi = active_kpis[r]  
        with cols_k[idx]:  
            st.markdown(f"#### 🏷️ {r}")  
            st.metric(  
                label=f"Ζήτηση: {kpi['hours']} ώρες | Προσωπικό: {kpi['staff_count']} άτομα ({kpi['marine_count']} ⚓)",  
                value=f"{kpi['avail_shifts']} / {kpi['needed_shifts']} βάρδιες",  
                delta=f"{kpi['status']}",  
                delta_color="normal" if "Πλήρης" in kpi['status'] else "inverse"  
            )  
  
    st.divider()  
  
    board_mode = st.radio(  
        "Επιλέξτε Ταμπλό προς Προβολή / Επεξεργασία:",  
        ["⚡ Πρόγραμμα Εβδομάδας (Εξαιρέσεις)", "📌 Βασικό Πρόγραμμα (Σταθερή Βάση)"],  
        horizontal=True  
    )  
  
    is_base_mode = (board_mode == "📌 Βασικό Πρόγραμμα (Σταθερή Βάση)")  
    current_matrix = st.session_state.base_matrix if is_base_mode else st.session_state.active_matrix  
  
    c_action1, c_action2 = st.columns([2, 1])  
    with c_action1:  
        if not is_base_mode:  
            is_different = (st.session_state.active_matrix != st.session_state.base_matrix)  
            if is_different:  
                st.info("🟡 **Ενεργές Εξαιρέσεις:** Το ταμπλό περιέχει αλλαγές για την τρέχουσα εβδομάδα σε σχέση με τη βάση.")  
            else:  
                st.success("🟢 **Σε συμφωνία με τη Βάση:** Δεν υπάρχουν τροποποιημένες εξαιρέσεις.")  
        else:  
            st.info("ℹ️ Επεξεργάζεστε τη **Μόνιμη Βάση**. Οι αλλαγές εδώ διατηρούνται σταθερές από εβδομάδα σε εβδομάδα.")  
  
    with c_action2:  
        if not is_base_mode:  
            if st.button("🧹 Καθαρισμός Εξαιρέσεων με 1 κλικ", type="secondary", use_container_width=True):  
                st.session_state.active_matrix = copy.deepcopy(st.session_state.base_matrix)  
                save_persistent_data(st.session_state.employees, st.session_state.base_matrix, st.session_state.active_matrix)  
                st.success("Όλες οι εξαιρέσεις μηδενίστηκαν και επανήλθε η Βάση!")  
                st.rerun()  
        else:  
            if st.button("💾 Αποθήκευση ως Νέα Βάση", type="primary", use_container_width=True):  
                save_persistent_data(st.session_state.employees, st.session_state.base_matrix, st.session_state.active_matrix)  
                st.success("Η Βάση αποθηκεύτηκε επιτυχώς!")  
  
    with st.expander("⚡ Γρήγορη Μαζική Συμπλήρωση Ζωνών (Δευτέρα - Πέμπτη κ.α.)", expanded=False):  
        with st.form("bulk_fill_form"):  
            c_b1, c_b2, c_b3 = st.columns(3)  
            with c_b1:  
                b_role = st.selectbox("Πόστο:", ["Όλα τα Πόστα"] + ROLES)  
            with c_b2:  
                b_slot = st.selectbox("Ωράριο Ζώνης:", [s["label"] for s in STANDARD_SLOTS])  
            with c_b3:  
                b_marine = st.selectbox("⚓ Απαίτηση Ναυτολόγησης:", ["Όχι", "Όλες τις ημέρες", "Μόνο Παρ - Κυρ", "Μόνο Δευτ - Πεμ"])  
  
            c_b4, c_b5 = st.columns([2, 1])  
            with c_b4:  
                b_preset = st.radio("Πρότυπο Ημερών:", ["Δευτέρα - Πέμπτη", "Παρασκευή - Κυριακή", "Όλες οι Ημέρες", "Επιλογή Συγκεκριμένων Ημερών"], horizontal=True)  
                if b_preset == "Δευτέρα - Πέμπτη":  
                    chosen_bulk_days = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη"]  
                elif b_preset == "Παρασκευή - Κυριακή":  
                    chosen_bulk_days = ["Παρασκευή", "Σάββατο", "Κυριακή"]  
                elif b_preset == "Όλες οι Ημέρες":  
                    chosen_bulk_days = DAYS  
                else:  
                    chosen_bulk_days = st.multiselect("Επιλέξτε ημέρες:", DAYS, default=DAYS)  
            with c_b5:  
                b_staff_count = st.number_input("Άτομα στη ζώνη:", min_value=0, max_value=10, value=2)  
  
            if st.form_submit_button("⚡ Μαζική Ενημέρωση στον Πίνακα"):  
                target_roles = ROLES if b_role == "Όλα τα Πόστα" else [b_role]  
                target_mat = st.session_state.base_matrix if is_base_mode else st.session_state.active_matrix  
  
                for row in target_mat:  
                    if row["Πόστο"] in target_roles and row["Ωράριο"] == b_slot:  
                        row["⚓ Ναυτολόγηση"] = b_marine  
                        for d in chosen_bulk_days:  
                            row[d] = int(b_staff_count)  
  
                save_persistent_data(st.session_state.employees, st.session_state.base_matrix, st.session_state.active_matrix)  
                st.success("Ο πίνακας ενημερώθηκε επιτυχώς!")  
                st.rerun()  
  
    st.markdown("#### 📊 Ταμπλό Ζωνών ανά Πόστο (Matrix Format)")  
    sub_tab_all, sub_tab_bar, sub_tab_srv, sub_tab_ypo = st.tabs(["🌐 Όλα τα Πόστα (Ενοποιημένο)", "🍸 Bar", "🍽️ Service", "🛎️ Υποδοχή"])  
  
    marine_options = ["Όχι", "Όλες τις ημέρες", "Μόνο Παρ - Κυρ", "Μόνο Δευτ - Πεμ"]  
  
    def render_role_matrix_editor(filtered_df, key_suffix):  
        return st.data_editor(  
            filtered_df,  
            use_container_width=True,  
            num_rows="fixed",  
            column_config={  
                "Πόστο": st.column_config.TextColumn("Πόστο", disabled=True),  
                "Ωράριο": st.column_config.TextColumn("Ωράριο", disabled=True),  
                "⚓ Ναυτολόγηση": st.column_config.SelectboxColumn("⚓ Ναυτολόγηση", options=marine_options, required=True),  
                "Δευτέρα": st.column_config.NumberColumn("Δευτέρα", min_value=0, max_value=10, step=1, required=True),  
                "Τρίτη": st.column_config.NumberColumn("Τρίτη", min_value=0, max_value=10, step=1, required=True),  
                "Τετάρτη": st.column_config.NumberColumn("Τετάρτη", min_value=0, max_value=10, step=1, required=True),  
                "Πέμπτη": st.column_config.NumberColumn("Πέμπτη", min_value=0, max_value=10, step=1, required=True),  
                "Παρασκευή": st.column_config.NumberColumn("Παρασκευή", min_value=0, max_value=10, step=1, required=True),  
                "Σάββατο": st.column_config.NumberColumn("Σάββατο", min_value=0, max_value=10, step=1, required=True),  
                "Κυριακή": st.column_config.NumberColumn("Κυριακή", min_value=0, max_value=10, step=1, required=True),  
            },  
            key=f"zones_editor_{key_suffix}"  
        )  
  
    with sub_tab_all:  
        df_all = pd.DataFrame(current_matrix)  
        edited_all = render_role_matrix_editor(df_all, "all")  
        if not edited_all.equals(df_all):  
            new_mat = edited_all.to_dict('records')  
            if is_base_mode:  
                st.session_state.base_matrix = new_mat  
            else:  
                st.session_state.active_matrix = new_mat  
            save_persistent_data(st.session_state.employees, st.session_state.base_matrix, st.session_state.active_matrix)  
            st.rerun()  
  
    with sub_tab_bar:  
        df_bar = pd.DataFrame([r for r in current_matrix if r["Πόστο"] == "Bar"])  
        edited_bar = render_role_matrix_editor(df_bar, "bar")  
        if not edited_bar.equals(df_bar):  
            bar_records = edited_bar.to_dict('records')  
            for i, r in enumerate(current_matrix):  
                if r["Πόστο"] == "Bar":  
                    match_rec = next((b for b in bar_records if b["Ωράριο"] == r["Ωράριο"]), None)  
                    if match_rec:  
                        current_matrix[i] = match_rec  
            save_persistent_data(st.session_state.employees, st.session_state.base_matrix, st.session_state.active_matrix)  
            st.rerun()  
  
    with sub_tab_srv:  
        df_srv = pd.DataFrame([r for r in current_matrix if r["Πόστο"] == "Service"])  
        edited_srv = render_role_matrix_editor(df_srv, "srv")  
        if not edited_srv.equals(df_srv):  
            srv_records = edited_srv.to_dict('records')  
            for i, r in enumerate(current_matrix):  
                if r["Πόστο"] == "Service":  
                    match_rec = next((b for b in srv_records if b["Ωράριο"] == r["Ωράριο"]), None)  
                    if match_rec:  
                        current_matrix[i] = match_rec  
            save_persistent_data(st.session_state.employees, st.session_state.base_matrix, st.session_state.active_matrix)  
            st.rerun()  
  
    with sub_tab_ypo:  
        df_ypo = pd.DataFrame([r for r in current_matrix if r["Πόστο"] == "Υποδοχή"])  
        edited_ypo = render_role_matrix_editor(df_ypo, "ypo")  
        if not edited_ypo.equals(df_ypo):  
            ypo_records = edited_ypo.to_dict('records')  
            for i, r in enumerate(current_matrix):  
                if r["Πόστο"] == "Υποδοχή":  
                    match_rec = next((b for b in ypo_records if b["Ωράριο"] == r["Ωράριο"]), None)  
                    if match_rec:  
                        current_matrix[i] = match_rec  
            save_persistent_data(st.session_state.employees, st.session_state.base_matrix, st.session_state.active_matrix)  
            st.rerun()  
  
    st.markdown("#### 🎨 Οπτική Προεπισκόπηση & Σήμανση Ναυτολόγησης")  
    st.caption("🟦 Οι ζώνες με σήμανση ναυτολόγησης απαιτούν τουλάχιστον 2 ναυτολογημένους συνολικά από Bar και Service.")  
  
    preview_rows = []  
    for row in current_matrix:  
        p_row = {"Πόστο": row["Πόστο"], "Ωράριο": row["Ωράριο"]}  
        mar_rule = row.get("⚓ Ναυτολόγηση", "Όχι")  
        for d in DAYS:  
            count = row[d]  
            is_mar = False  
            if mar_rule == "Όλες τις ημέρες":  
                is_mar = True  
            elif mar_rule == "Μόνο Παρ - Κυρ" and d in ["Παρασκευή", "Σάββατο", "Κυριακή"]:  
                is_mar = True  
            elif mar_rule == "Μόνο Δευτ - Πεμ" and d in ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη"]:  
                is_mar = True  
  
            p_row[d] = f"{count} ⚓" if (is_mar and count > 0) else f"{count}"  
        preview_rows.append(p_row)  
  
    df_preview = pd.DataFrame(preview_rows)  
  
    def highlight_zones(row):  
        role = row["Πόστο"]  
        if role == "Bar":  
            base_color = "background-color: #CFE2F3; color: black;"  
        elif role == "Service":  
            base_color = "background-color: #FCE5CD; color: black;"  
        else:  
            base_color = "background-color: #FFF2CC; color: black;"  
  
        styles = []  
        for col_name, val in row.items():  
            if "⚓" in str(val):  
                styles.append("background-color: #A9CCE3; color: #003366; font-weight: bold; border: 1px solid #1B4F72;")  
            else:  
                styles.append(base_color)  
        return styles  
  
    st.dataframe(df_preview.style.apply(highlight_zones, axis=1), use_container_width=True, hide_index=True)  
  
# ---------------------------------------------------------  
# TAB 3: ΕΠΙΛΥΣΗ, ΕΓΧΡΩΜΟ FORMAT & EXCEL EXPORT  
# ---------------------------------------------------------  
with tab3:  
    st.subheader("Αυτόματη Δημιουργία & Επεξεργασία Προγράμματος")  
  
    if st.button("🚀 Υπολογισμός Προγράμματος (OR-Tools)", type="primary"):  
        active_reqs = matrix_to_requirements(st.session_state.active_matrix)  
        
        status, all_shifts = solve_full_schedule(st.session_state.employees, active_reqs)  
  
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):  
            st.success("🎉 Το πρόγραμμα υπολογίστηκε επιτυχώς με τήρηση όλων των κανόνων και των ναυτολογήσεων!")  
  
            shift_dict = {(item["day"], item["name"]): item["shift"] for item in all_shifts}  
            sorted_employees = sorted(  
                st.session_state.employees,  
                key=lambda e: (ROLES.index(e["role"]) if e["role"] in ROLES else 99, e["name"])  
            )  
  
            matrix_rows = []  
            for e in sorted_employees:  
                emp_display = f"{e['name']} ⚓" if e["is_marine"] else e["name"]  
                row_data = {  
                    "Πόστο": e["role"],  
                    "Εργαζόμενος": emp_display  
                }  
                for d in DAYS:  
                    row_data[d] = shift_dict.get((d, e["name"]), "ΡΕΠΟ")  
                matrix_rows.append(row_data)  
  
            st.session_state.matrix_schedule = pd.DataFrame(matrix_rows)  
            st.session_state.last_shifts_raw = all_shifts  
        else:  
            st.session_state.matrix_schedule = None  
            st.error("❌ Αδύνατη η εύρεση λύσης! Δείτε παρακάτω τους λόγους σύγκρουσης:")  
            reasons = diagnose_schedule_failure(st.session_state.employees, active_reqs, status)  
            for reason in reasons:  
                st.markdown(f"* {reason}")  
  
    # ---------------------------------------------------------  
    # EDITABLE MATRIX & COLOR PREVIEW  
    # ---------------------------------------------------------  
    if st.session_state.matrix_schedule is not None:  
        st.divider()  
        st.markdown("### ✏️ Επεξεργάσιμο Πρόγραμμα Βαρδιών")  
        st.caption("⚓ Δίπλα στα ονόματα των ναυτολογημένων εμφανίζεται η άγκυρα. Όλοι έχουν τουλάχιστον 5 μεροκάματα.")  
  
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
  
        # Έλεγχος Παρουσίας Ναυτολογημένων (Audit)  
        with st.expander("⚓ Έλεγχος Ναυτολόγησης (Bar + Service) ανά Ημέρα", expanded=False):  
            audit_data = []  
            raw_shifts = st.session_state.get("last_shifts_raw", [])  
            for d in DAYS:  
                day_marines = [s for s in raw_shifts if s["day"] == d and s["is_marine"] and s["role"] in ["Bar", "Service"]]  
                names_bar = [s["name"] for s in day_marines if s["role"] == "Bar"]  
                names_srv = [s["name"] for s in day_marines if s["role"] == "Service"]  
                audit_data.append({  
                    "Ημέρα": d,  
                    "Σύνολο Ναυτολογημένων": len(day_marines),  
                    "Bar": f"{len(names_bar)} ({', '.join(names_bar)})" if names_bar else "0",  
                    "Service": f"{len(names_srv)} ({', '.join(names_srv)})" if names_srv else "0",  
                    "Κάλυψη >= 2": "✅ Πλήρης" if len(day_marines) >= 2 else "❌ Έλλειψη"  
                })  
            st.dataframe(pd.DataFrame(audit_data), use_container_width=True, hide_index=True)  
  
        excel_data = create_styled_excel(edited_matrix)  
        st.download_button(  
            label="📥 Λήψη σε Έγχρωμο Excel (.xlsx)",  
            data=excel_data,  
            file_name="programma_vardion.xlsx",  
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  
            type="primary"  
        )  
  
        st.markdown("#### 🎨 Προεπισκόπηση με Χρώματα ανά Πόστο")  
        def highlight_roles(row):  
            role = row["Πόστο"]  
            if role == "Service":  
                bg = "background-color: #FCE5CD; color: black;"  
            elif role == "Bar":  
                bg = "background-color: #CFE2F3; color: black;"  
            else:  
                bg = "background-color: #FFF2CC; color: black;"  
            return [bg] * len(row)  
  
        styled_df = edited_matrix.style.apply(highlight_roles, axis=1)  
        st.dataframe(styled_df, use_container_width=True, hide_index=True)