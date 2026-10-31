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
# ΠΡΟΚΑΘΟΡΙΣΜΕΝΟ ΠΡΟΣΩΠΙΚΟ  
# ---------------------------------------------------------  
DEFAULT_STAFF_CONFIG = [
    # Bar (21+ βάρδιες/εβδομάδα)
    {"name": "Άρης", "role": "Bar", "is_marine": False, "target_shifts": 5},
    {"name": "Βαγγέλης", "role": "Bar", "is_marine": False, "target_shifts": 5},
    {"name": "Γιάννης", "role": "Bar", "is_marine": True, "target_shifts": 5},
    {"name": "Κώστας", "role": "Bar", "is_marine": True, "target_shifts": 6},
    # Service (21+ βάρδιες/εβδομάδα)
    {"name": "Φωτεινή", "role": "Service", "is_marine": True, "target_shifts": 5},
    {"name": "Μαρία", "role": "Service", "is_marine": False, "target_shifts": 5},
    {"name": "Θεόφιλος", "role": "Service", "is_marine": True, "target_shifts": 6},
    {"name": "Σαλώμη", "role": "Service", "is_marine": False, "target_shifts": 5},
    # Υποδοχή (καμία εμπλοκή με ναυτολόγηση)
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
    slot_clean = str(slot_str).strip()
    for s in STANDARD_SLOTS:  
        if s["label"] == slot_clean:  
            return s["start"], s["end"], s["duration"]  
    try:
        if " - " in slot_clean:
            parts = slot_clean.split(" - ")
        elif "-" in slot_clean:
            parts = slot_clean.split("-")
        else:
            return 11, 18, 7
            
        s_raw = parts[0].strip().split(":")[0]
        s_val = int(s_raw)
        e_raw = parts[1].strip().split(":")[0]
        e_val = 25 if e_raw in ["01", "1"] else (24 if e_raw in ["00", "0"] else int(e_raw))
        if e_val < s_val and e_val <= 3:
            e_val += 24
        dur = max(0, e_val - s_val)
        return s_val, e_val, dur
    except Exception:
        return 11, 18, 7

def sort_matrix(mat):
    role_order = {r: i for i, r in enumerate(ROLES)}
    return sorted(
        mat, 
        key=lambda row: (
            role_order.get(row.get("Πόστο", ""), 99),
            get_slot_bounds(str(row.get("Ωράριο", "")))[0],
            str(row.get("Ωράριο", ""))
        )
    )

def get_initial_zones_matrix():  
    zones = [  
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
    return sort_matrix(zones)

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
# ΜΟΝΙΜΗ ΑΠΟΘΗΚΕΥΣΗ (JSON)  
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
                if "employees" in data and isinstance(data["employees"], list) and len(data["employees"]) > 0:  
                    emps = data["employees"]
                    matrix = data.get("matrix") or data.get("zones_matrix") or get_initial_zones_matrix()
                    last_sched = data.get("last_schedule", None)
                    last_raw = data.get("last_shifts_raw", [])
                    return emps, sort_matrix(matrix), last_sched, last_raw
        except Exception:  
            pass  
  
    default_employees = build_default_employees()  
    matrix = get_initial_zones_matrix()  
    save_persistent_data(default_employees, matrix, None, [])  
    return default_employees, matrix, None, []  
  
def save_persistent_data(employees, matrix, last_schedule=None, last_shifts_raw=None):  
    sched_records = None
    if last_schedule is not None:
        if isinstance(last_schedule, pd.DataFrame):
            sched_records = last_schedule.to_dict('records')
        else:
            sched_records = last_schedule
            
    data = {  
        "employees": sanitize_for_json(employees),  
        "matrix": sanitize_for_json(sort_matrix(matrix)),
        "last_schedule": sanitize_for_json(sched_records),
        "last_shifts_raw": sanitize_for_json(last_shifts_raw if last_shifts_raw is not None else [])
    }  
    with open(DATA_FILE, "w", encoding="utf-8") as f:  
        json.dump(data, f, ensure_ascii=False, indent=2)  

def persist_current_state():
    save_persistent_data(
        st.session_state.employees,
        st.session_state.zones_matrix,
        st.session_state.matrix_schedule,
        st.session_state.get("last_shifts_raw", [])
    )

if "employees" not in st.session_state:  
    loaded_emps, loaded_matrix, loaded_sched, loaded_raw = load_persistent_data()  
    st.session_state.employees = loaded_emps  
    st.session_state.zones_matrix = loaded_matrix  
    st.session_state.matrix_schedule = pd.DataFrame(loaded_sched) if loaded_sched else None  
    st.session_state.last_shifts_raw = loaded_raw  

# ---------------------------------------------------------  
# KPIs ΑΝΑΓΚΩΝ & ΖΩΝΩΝ  
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
            hourly_demand = [0] * 26  
            daily_hours = 0  

            for row in role_rows:  
                s_val, e_val, dur = get_slot_bounds(str(row["Ωράριο"]))  
                needed = int(row.get(d, 0) or 0)  
                daily_hours += (needed * dur)  
                if needed > 0:
                    for h in range(s_val, e_val):
                        hourly_demand[h] += needed

            total_hours += daily_hours  
            morning_peak = max(hourly_demand[11:18]) if any(hourly_demand[11:18]) else 0
            evening_peak = max(hourly_demand[18:25]) if any(hourly_demand[18:25]) else 0
            overall_peak = max(hourly_demand[11:25]) if any(hourly_demand[11:25]) else 0
            
            shifts_today = max(morning_peak + evening_peak, overall_peak, math.ceil(daily_hours / 8.0))
            min_shifts_week += shifts_today  
  
        avail_shifts = sum(e["target_shifts"] for e in staff_r)  
        avail_mar_shifts = sum(e["target_shifts"] for e in marines_r)  
  
        if avail_shifts < min_shifts_week:  
            status = "🔴 Έλλειψη Προσωπικού"  
        elif avail_shifts == min_shifts_week:  
            status = "⚠️ Οριακό (0 Slack)"  
        else:  
            status = "🟢 Πλήρης Κάλυψη"  
  
        kpis[r] = {  
            "staff_count": len(staff_r),  
            "marine_count": len(marines_r),  
            "hours": total_hours,  
            "needed_shifts": min_shifts_week,  
            "avail_shifts": avail_shifts,  
            "avail_mar_shifts": avail_mar_shifts,  
            "status": status  
        }  
    return kpis  

# ---------------------------------------------------------  
# CONVERT MATRIX TO SOLVER REQUIREMENTS  
# ---------------------------------------------------------  
def matrix_to_requirements(matrix):  
    reqs = []  
    for row in matrix:  
        role = row["Πόστο"]  
        s_val, e_val, _ = get_slot_bounds(str(row["Ωράριο"]))  
        mar_rule = row.get("⚓ Ναυτολόγηση", "Όχι")  
  
        for d in DAYS:  
            staff_count = int(row.get(d, 0) or 0)  
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
# ΕΝΙΑΙΟΣ SOLVER (OR-TOOLS CP-SAT) ΜΕ ΚΑΝΟΝΑ 10ΩΡΟΥ (+2h ΜΙΑ ΦΟΡΑ)
# ---------------------------------------------------------  
def solve_full_schedule(employees, all_reqs, relax=None, time_limit=8.0):  
    model = cp_model.CpModel()  
    
    x = {}  
    works_day = {}  
    all_overtime_vars = []
    
    for e in employees:  
        eid = e["id"]  
        avail_count = sum(1 for d in DAYS if e["unavailability"][d]["status"] != "all_day")  
        emp_overtimes = []
        
        for d in DAYS:  
            works_day[(eid, d)] = model.NewBoolVar(f"w_{eid}_{d}")  
            for h in range(11, 25):  
                x[(eid, d, h)] = model.NewBoolVar(f"x_{eid}_{d}_{h}")  
                
            daily_hours = [x[(eid, d, h)] for h in range(11, 25)]  
            model.Add(sum(daily_hours) >= 1).OnlyEnforceIf(works_day[(eid, d)])  
            model.Add(sum(daily_hours) == 0).OnlyEnforceIf(works_day[(eid, d)].Not())  
            
            # --- ΚΑΝΟΝΑΣ 10ΩΡΟΥ & ΕΞΑΙΡΕΣΗ ΕΩΣ 12ΩΡΟ ΜΙΑ ΦΟΡΑ ΤΗΝ ΕΒΔΟΜΑΔΑ ---
            is_overtime = model.NewBoolVar(f"ot_{eid}_{d}")
            emp_overtimes.append(is_overtime)
            all_overtime_vars.append(is_overtime)
            
            # Κανονική μέρα: max 10 ώρες
            model.Add(sum(daily_hours) <= 10).OnlyEnforceIf(is_overtime.Not())
            # Μέρα υπερωρίας: max 12 ώρες (και τουλάχιστον 11)
            model.Add(sum(daily_hours) <= 12).OnlyEnforceIf(is_overtime)
            model.Add(sum(daily_hours) >= 11).OnlyEnforceIf(is_overtime)
            
            # Ελάχιστη βάρδια 4 ώρες συνεχόμενης εργασίας  
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
            
        # Επιτρέπεται το πολύ 1 ημέρα με >10 ώρες (11-12 ώρες) ανά υπάλληλο ανά εβδομάδα
        model.Add(sum(emp_overtimes) <= 1)
            
        # Διαθεσιμότητα / Κωλύματα
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
                            
        total_weekly_hours = sum(x[(eid, d, h)] for d in DAYS for h in range(11, 25))
        
        if e["is_marine"] and e["role"] in ["Bar", "Service"]:  
            min_sh = min(5, avail_count)
            max_sh = min(max(5, e["target_shifts"]), avail_count)
            
            if relax not in ("no_min_shifts", "compound_all"):  
                model.Add(sum(works_day[(eid, d)] for d in DAYS) >= min_sh)  
            if relax not in ("no_max_shifts", "compound_all"):  
                model.Add(sum(works_day[(eid, d)] for d in DAYS) <= max_sh)  
            
            if relax not in ("no_marine_hours", "compound_all"):  
                min_weekly_h = 40 if avail_count >= 5 else (avail_count * 8)
                model.Add(total_weekly_hours >= min_weekly_h)
        else:  
            eff_max = min(e["target_shifts"], avail_count)  
            eff_min = max(0, min(e["target_shifts"] - 1, avail_count))  
            if relax not in ("no_min_shifts", "compound_all"):  
                model.Add(sum(works_day[(eid, d)] for d in DAYS) >= eff_min)  
            if relax not in ("no_max_shifts", "compound_all"):  
                model.Add(sum(works_day[(eid, d)] for d in DAYS) <= eff_max)  
                
    # Κάλυψη Αναγκών ανά Πόστο  
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
                    
    # Κανόνας Ναυτολογημένων: 2 άτομα σύνολο από Bar & Service  
    marines_bs = [e for e in employees if e["is_marine"] and e["role"] in ["Bar", "Service"]]  
    
    if relax not in ("no_marine", "compound_all"):  
        for d in DAYS:  
            for h in range(11, 25):  
                marine_required = False  
                for rq in all_reqs:  
                    if rq["role"] in ["Bar", "Service"] and rq["day"] == d and rq["start"] <= h < rq["end"]:  
                        if rq["require_marine"]:  
                            marine_required = True  
                            break  
                if marine_required:  
                    model.Add(sum(x[(e["id"], d, h)] for e in marines_bs) >= 2)  
                    
    # Στόχος: Ελαχιστοποίηση συνολικών ωρών με ελαφρά προτίμηση αποφυγής 11-12ωρου αν δεν είναι απαραίτητο
    total_hours = sum(x[(e["id"], d, h)] for e in employees for d in DAYS for h in range(11, 25))  
    total_ot_penalty = sum(all_overtime_vars)
    model.Minimize(total_hours * 10 + total_ot_penalty * 2)  
    
    solver = cp_model.CpSolver()  
    solver.parameters.max_time_in_seconds = time_limit  
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
                        "hours": len(w),
                        "is_overtime": len(w) > 10,
                        "start_h": min(w),  
                        "end_h": max(w) + 1  
                    })  
    return status, res  

# ---------------------------------------------------------  
# ΔΙΑΓΝΩΣΤΙΚΟ ΜΕ ΧΡΟΝΙΚΟ ΠΛΑΙΣΙΟ / ΒΑΡΔΙΑ (ΧΩΡΙΣ ΠΕΡΙΤΤΕΣ ΛΕΠΤΟΜΕΡΕΙΕΣ)
# ---------------------------------------------------------  
def diagnose_schedule_failure(employees, all_reqs, status=None):  
    issues = []  
    
    if status == cp_model.UNKNOWN:  
        issues.append({
            "Πόστο": "Γενικό",
            "Ημέρα": "Όλη την εβδομάδα",
            "Τύπος Προβλήματος": "⏱️ Χρονικό Όριο (Timeout)",
            "Βάρδια / Ώρες": "11:00 - 01:00"
        })
        return issues  
        
    for r in ROLES:  
        staff_r = [e for e in employees if e["role"] == r]  
        reqs_r = [rq for rq in all_reqs if rq["role"] == r]  
        
        if not staff_r and reqs_r:  
            role_hours = [(rq["start"], rq["end"]) for rq in reqs_r]
            time_frame = f"{format_hour(min(h[0] for h in role_hours))} - {format_hour(max(h[1] for h in role_hours))}" if role_hours else "11:00 - 01:00"
            issues.append({
                "Πόστο": r,
                "Ημέρα": "Όλες",
                "Τύπος Προβλήματος": "❌ Έλλειψη Προσωπικού",
                "Βάρδια / Ώρες": time_frame
            })
            continue  
            
        for d in DAYS:  
            day_reqs = [rq for rq in reqs_r if rq["day"] == d]
            seen_slots = set()
            for rq in day_reqs:
                slot_key = (rq["start"], rq["end"])
                if slot_key in seen_slots:
                    continue
                
                slot_has_issue = False
                for h in range(rq["start"], rq["end"]):
                    needed = max([r_sub["min_staff"] for r_sub in day_reqs if r_sub["start"] <= h < r_sub["end"]], default=0)
                    if needed > 0:
                        avail_count = 0
                        for e in staff_r:
                            u = e["unavailability"].get(d, {"status": "available"})
                            if u["status"] == "all_day":
                                continue
                            elif u["status"] == "custom" and (u["start"] <= h < u["end"]):
                                continue
                            else:
                                avail_count += 1
                        if avail_count < needed:
                            slot_has_issue = True
                            break
                            
                if slot_has_issue:
                    seen_slots.add(slot_key)
                    time_frame = f"{format_hour(rq['start'])} - {format_hour(rq['end'])}"
                    issues.append({
                        "Πόστο": r,
                        "Ημέρα": d,
                        "Τύπος Προβλήματος": "🚫 Έλλειψη Προσωπικού στη Βάρδια",
                        "Βάρδια / Ώρες": time_frame
                    })
                        
    for r in ROLES:  
        staff_r = [e for e in employees if e["role"] == r]  
        reqs_r = [rq for rq in all_reqs if rq["role"] == r]  
        total_avail_shifts = sum(e["target_shifts"] for e in staff_r)  
        
        min_shifts_needed = 0  
        for d in DAYS:  
            hourly_demand = [0] * 26
            daily_hours = 0
            for row in [rq for rq in reqs_r if rq["day"] == d]:  
                daily_hours += (row["end"] - row["start"]) * row["min_staff"]  
                for h in range(row["start"], row["end"]):
                    hourly_demand[h] += row["min_staff"]
            m_peak = max(hourly_demand[11:18]) if any(hourly_demand[11:18]) else 0
            e_peak = max(hourly_demand[18:25]) if any(hourly_demand[18:25]) else 0
            d_shifts = max(m_peak + e_peak, math.ceil(daily_hours / 8.0))  
            min_shifts_needed += d_shifts  
            
        if total_avail_shifts < min_shifts_needed:  
            role_hours = [(rq["start"], rq["end"]) for rq in reqs_r]
            time_frame = f"{format_hour(min(h[0] for h in role_hours))} - {format_hour(max(h[1] for h in role_hours))}" if role_hours else "11:00 - 01:00"
            issues.append({
                "Πόστο": r,
                "Ημέρα": "Όλη την εβδομάδα",
                "Τύπος Προβλήματος": "📈 Ανεπάρκεια Μεροκάματων",
                "Βάρδια / Ώρες": time_frame
            })
            
    marines_bs = [e for e in employees if e["is_marine"] and e["role"] in ["Bar", "Service"]]  
    mar_reqs = [rq for rq in all_reqs if rq.get("require_marine")]
    if mar_reqs:
        m_s = min(rq["start"] for rq in mar_reqs)
        m_e = max(rq["end"] for rq in mar_reqs)
        mar_time_frame = f"{format_hour(m_s)} - {format_hour(m_e)}"
    else:
        mar_time_frame = "18:00 - 01:00"

    if len(marines_bs) < 2:  
        issues.append({
            "Πόστο": "Bar & Service",
            "Ημέρα": "Όλες",
            "Τύπος Προβλήματος": "⚓ Έλλειψη Ναυτολογημένων",
            "Βάρδια / Ώρες": mar_time_frame
        })
    else:  
        for d in DAYS:  
            mar_day_reqs = [rq for rq in all_reqs if rq["role"] in ["Bar", "Service"] and rq["day"] == d and rq.get("require_marine")]
            seen_mar_slots = set()
            for rq in mar_day_reqs:
                slot_key = (rq["start"], rq["end"])
                if slot_key in seen_mar_slots:
                    continue
                slot_mar_issue = False
                for h in range(rq["start"], rq["end"]):
                    avail_mar = 0
                    for e in marines_bs:
                        u = e["unavailability"].get(d, {"status": "available"})
                        if u["status"] == "all_day":
                            continue
                        elif u["status"] == "custom" and (u["start"] <= h < u["end"]):
                            continue
                        else:
                            avail_mar += 1
                    if avail_mar < 2:
                        slot_mar_issue = True
                        break
                if slot_mar_issue:
                    seen_mar_slots.add(slot_key)
                    time_frame = f"{format_hour(rq['start'])} - {format_hour(rq['end'])}"
                    issues.append({
                        "Πόστο": "Bar & Service (Κοινό)",
                        "Ημέρα": d,
                        "Τύπος Προβλήματος": "⚓ Έλλειψη Ναυτολογημένων",
                        "Βάρδια / Ώρες": time_frame
                    })

    st_no_mar, _ = solve_full_schedule(employees, all_reqs, relax="no_marine", time_limit=1.5)  
    if st_no_mar in (cp_model.OPTIMAL, cp_model.FEASIBLE) and not any("⚓" in iss["Τύπος Προβλήματος"] for iss in issues):  
        issues.append({
            "Πόστο": "Bar & Service (Κοινό)",
            "Ημέρα": "Πολλαπλές Ημέρες",
            "Τύπος Προβλήματος": "⚓ Σύγκρουση Ναυτολόγησης & Ωραρίου",
            "Βάρδια / Ώρες": mar_time_frame
        })
            
    st_no_mar_hours, _ = solve_full_schedule(employees, all_reqs, relax="no_marine_hours", time_limit=1.5)  
    if st_no_mar_hours in (cp_model.OPTIMAL, cp_model.FEASIBLE) and not any("40 Ωρών" in iss["Τύπος Προβλήματος"] for iss in issues):  
        issues.append({
            "Πόστο": "Bar & Service",
            "Ημέρα": "Όλη την εβδομάδα",
            "Τύπος Προβλήματος": "⏱️ Κανόνας 40 Ωρών Ναυτολόγησης",
            "Βάρδια / Ώρες": mar_time_frame
        })

    if not issues:  
        issues.append({
            "Πόστο": "Όλα τα Πόστα",
            "Ημέρα": "Εβδομαδιαίο",
            "Τύπος Προβλήματος": "⚠️ Σύνθετη Σύγκρουση Περιορισμών",
            "Βάρδια / Ώρες": "11:00 - 01:00"
        })
        
    return issues  

# ---------------------------------------------------------  
# EXCEL EXPORT  
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
  
tab1, tab2, tab3 = st.tabs(["👤 Καρτέλα Υπαλλήλου", "⚙️ Ρυθμίσεις Manager (Ζώνες & Έλεγχος)", "📅 Τελικό Πρόγραμμα"])  

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
                            "target_shifts": max(5, new_sh) if is_actual_marine else new_sh,  
                            "unavailability": {d: {"status": "available", "start": 11, "end": 17} for d in DAYS}  
                        })  
                        persist_current_state()  
                        st.success(f"Ο/Η {new_name} προστέθηκε επιτυχώς!")  
                        st.rerun()  
  
        with c_del:  
            st.markdown("##### 🗑️ Διαγραφή ή Επαναφορά")  
            if st.session_state.employees:  
                del_name = st.selectbox("Επιλέξτε υπάλληλο προς διαγραφή:", [e["name"] for e in st.session_state.employees], key="del_emp_select")  
                if st.button("❌ Οριστική Διαγραφή", type="secondary"):  
                    st.session_state.employees = [e for e in st.session_state.employees if e["name"] != del_name]  
                    persist_current_state()  
                    st.success(f"Ο/Η {del_name} διαγράφηκε!")  
                    st.rerun()  

            st.write("")  
            if st.button("🔄 Επαναφορά Προεπιλεγμένων Εργαζομένων (Reset All)", type="secondary"):  
                st.session_state.employees = build_default_employees()  
                persist_current_state()  
                st.success("Επανήλθαν οι προεπιλεγμένοι εργαζόμενοι!")  
                st.rerun()  
  
    st.divider()  
  
    if not st.session_state.employees:  
        st.warning("Δεν υπάρχουν καταχωρημένοι υπάλληλοι.")  
        st.stop()  
  
    emp_names = [e["name"] for e in st.session_state.employees]  
    selected_name = st.selectbox("Επιλέξτε το όνομά σας:", emp_names, key="selected_employee_dropdown")  
    emp = next((e for e in st.session_state.employees if e["name"] == selected_name), st.session_state.employees[0])  
  
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
            st.caption("ℹ️ Η υποδοχή εξαιρείται από ναυτολόγηση.")  
    with col_shifts:  
        if new_marine and new_role in ["Bar", "Service"]:  
            cur_val = max(5, emp.get("target_shifts", 5))  
            new_shifts = st.slider("Επιθυμητά μεροκάματα εβδομάδας (Ναυτολογημένος: min 5):", 5, 7, value=cur_val, key=f"ui_shifts_{emp['id']}")  
            st.caption("⚓ Τουλάχιστον 5 μεροκάματα & 40+ ώρες (επιτρέπεται 1 ημέρα 11-12h).")  
        else:  
            new_shifts = st.slider("Επιθυμητά μεροκάματα εβδομάδας:", 1, 7, value=emp["target_shifts"], key=f"ui_shifts_{emp['id']}")  
  
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
  
            persist_current_state()  
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
  
            persist_current_state()  
            st.info(f"Τα κωλύματα του/της {emp['name']} μηδενίστηκαν.")  
            st.rerun()  

# ---------------------------------------------------------  
# TAB 2: ΡΥΘΜΙΣΕΙΣ MANAGER (DASHBOARD & ΠΡΟΛΗΠΤΙΚΟΣ ΕΛΕΓΧΟΣ)  
# ---------------------------------------------------------  
with tab2:  
    st.subheader("Διαχείριση Αναγκών & Ζωνών Προσωπικού")  

    top_banner_placeholder = st.empty()

    # 1. VISUAL DASHBOARD ΔΙΑΘΕΣΙΜΟΤΗΤΑΣ ΑΝΑ ΠΟΣΤΟ
    st.markdown("### 📊 Οπτικό Dashboard Διαθεσιμότητας ανά Πόστο")
    st.caption("🔍 Επισκόπηση διαθεσιμότητας προσωπικού σε σχέση με τις ανάγκες του μαγαζιού ανά ημέρα. Τα κόκκινα κελιά υποδεικνύουν άμεσο έλλειμμα.")

    dash_tabs = st.tabs(["🍸 Bar", "🍽️ Service", "🛎️ Υποδοχή"])
    current_matrix = st.session_state.zones_matrix
    
    for idx, r in enumerate(ROLES):
        with dash_tabs[idx]:
            staff_r = [e for e in st.session_state.employees if e["role"] == r]
            role_rows = [row for row in current_matrix if row["Πόστο"] == r]
            
            daily_needed_peak = {}
            for d in DAYS:
                h_dem = [0] * 26
                for row in role_rows:
                    s_val, e_val, _ = get_slot_bounds(str(row["Ωράριο"]))
                    count = int(row.get(d, 0) or 0)
                    if count > 0:
                        for h in range(s_val, e_val):
                            h_dem[h] += count
                m_peak = max(h_dem[11:18]) if any(h_dem[11:18]) else 0
                e_peak = max(h_dem[18:25]) if any(h_dem[18:25]) else 0
                daily_needed_peak[d] = max(m_peak, e_peak, max(h_dem[11:25]) if any(h_dem[11:25]) else 0)

            dash_rows = []
            for e in staff_r:
                row_dict = {
                    "Εργαζόμενος": f"{e['name']} ⚓" if e["is_marine"] else e["name"],
                    "Μεροκάματα": f"{e['target_shifts']}/7"
                }
                for d in DAYS:
                    u = e["unavailability"].get(d, {"status": "available"})
                    if u["status"] == "all_day":
                        row_dict[d] = "🔴 ΡΕΠΟ"
                    elif u["status"] == "custom":
                        row_dict[d] = f"🟡 {format_hour(u['start'])}-{format_hour(u['end'])}"
                    else:
                        row_dict[d] = "🟢 Διαθέσιμος"
                dash_rows.append(row_dict)

            avail_row = {"Εργαζόμενος": "👥 Σύνολο Διαθέσιμων", "Μεροκάματα": f"{sum(e['target_shifts'] for e in staff_r)}"}
            for d in DAYS:
                cnt = 0
                for e in staff_r:
                    if e["unavailability"].get(d, {}).get("status") != "all_day":
                        cnt += 1
                avail_row[d] = f"{cnt} άτομα"
            dash_rows.append(avail_row)

            needed_row = {"Εργαζόμενος": "📌 Απαιτούμενο Προσωπικό (Αιχμή)", "Μεροκάματα": "-"}
            for d in DAYS:
                needed_row[d] = f"{daily_needed_peak[d]} άτομα"
            dash_rows.append(needed_row)

            balance_row = {"Εργαζόμενος": "⚖️ Έλεγχος Κάλυψης", "Μεροκάματα": "-"}
            for d in DAYS:
                avail_cnt = sum(1 for e in staff_r if e["unavailability"].get(d, {}).get("status") != "all_day")
                need_cnt = daily_needed_peak[d]
                diff = avail_cnt - need_cnt
                if diff < 0:
                    balance_row[d] = f"🔴 Έλλειμμα ({diff})"
                elif diff == 0:
                    balance_row[d] = "⚠️ Οριακό (0)"
                else:
                    balance_row[d] = f"🟢 Πλήρης (+{diff})"
            dash_rows.append(balance_row)

            if r in ["Bar", "Service"]:
                mar_row = {"Εργαζόμενος": "⚓ Διαθέσιμοι Ναυτολογημένοι", "Μεροκάματα": "-"}
                for d in DAYS:
                    m_cnt = sum(1 for e in staff_r if e["is_marine"] and e["unavailability"].get(d, {}).get("status") != "all_day")
                    mar_row[d] = f"{m_cnt} ναυτ."
                dash_rows.append(mar_row)

            df_dash = pd.DataFrame(dash_rows)
            st.dataframe(df_dash, use_container_width=True, hide_index=True)

    st.divider()

    # 2. ΠΡΟΣΘΗΚΗ & ΔΙΑΓΡΑΦΗ ΖΩΝΗΣ
    col_tools_add, col_tools_del = st.columns(2)  
    with col_tools_add:  
        with st.expander("➕ Προσθήκη Νέας Ζώνης", expanded=False):  
            with st.form("add_zone_form"):  
                z_role = st.selectbox("Πόστο:", ROLES, key="nz_role")  
                z_slot = st.text_input("Ωράριο (π.χ. 11:00 - 18:00, 18:00 - 01:00):", value="18:00 - 01:00", key="nz_slot")  
                z_marine = st.selectbox("⚓ Απαίτηση Ναυτολόγησης:", ["Όχι", "Όλες τις ημέρες", "Μόνο Παρ - Κυρ", "Μόνο Δευτ - Πεμ"], key="nz_marine")  
                z_default_count = st.number_input("Πλήθος ατόμων (όλες τις μέρες):", min_value=0, max_value=10, value=1, step=1)  
                
                if st.form_submit_button("Προσθήκη Ζώνης"):  
                    if not z_slot.strip():  
                        st.error("Συμπληρώστε το ωράριο.")  
                    else:  
                        new_zone = {  
                            "Πόστο": z_role,  
                            "Ωράριο": z_slot.strip(),  
                            "⚓ Ναυτολόγηση": z_marine,  
                        }  
                        for d in DAYS:  
                            new_zone[d] = int(z_default_count)  
                        
                        st.session_state.zones_matrix.append(new_zone)  
                        st.session_state.zones_matrix = sort_matrix(st.session_state.zones_matrix)  
                        persist_current_state()  
                        st.success(f"Η ζώνη **{z_role} ({z_slot})** προστέθηκε και αποθηκεύτηκε!")  
                        st.rerun()  

    with col_tools_del:  
        with st.expander("🗑️ Διαγραφή Ζώνης", expanded=False):  
            if st.session_state.zones_matrix:  
                zone_options = [f"{i+1}. [{row['Πόστο']}] {row['Ωράριο']}" for i, row in enumerate(st.session_state.zones_matrix)]  
                selected_del_idx_str = st.selectbox("Επιλέξτε ζώνη προς διαγραφή:", zone_options, key="del_zone_sel")  
                del_idx = int(selected_del_idx_str.split(".")[0]) - 1  
                
                if st.button("❌ Διαγραφή Αυτής της Ζώνης", type="secondary"):  
                    deleted_item = st.session_state.zones_matrix.pop(del_idx)  
                    persist_current_state()  
                    st.success(f"Η ζώνη [{deleted_item['Πόστο']}] {deleted_item['Ωράριο']} διαγράφηκε!")  
                    st.rerun()  

    # 3. ΠΛΗΡΩΣ ΕΠΕΞΕΡΓΑΣΙΜΟ ΤΑΜΠΛΟ ΖΩΝΩΝ
    st.markdown("#### 📊 Ταμπλό Ζωνών (Πλήρως Επεξεργάσιμο)")  
    st.caption("💡 Μπορείτε να κάνετε κλικ σε **οποιοδήποτε κελί** για άμεση αλλαγή (Πόστο, Ωράριο, Ναυτολόγηση, άτομα). Κάθε αλλαγή ελέγχεται προληπτικά σε πραγματικό χρόνο.")  

    marine_options = ["Όχι", "Όλες τις ημέρες", "Μόνο Παρ - Κυρ", "Μόνο Δευτ - Πεμ"]  
    st.session_state.zones_matrix = sort_matrix(st.session_state.zones_matrix)  
    df_zones = pd.DataFrame(st.session_state.zones_matrix)  

    edited_zones_df = st.data_editor(  
        df_zones,  
        use_container_width=True,  
        num_rows="dynamic",  
        column_config={  
            "Πόστο": st.column_config.SelectboxColumn("Πόστο", options=ROLES, required=True),  
            "Ωράριο": st.column_config.TextColumn("Ωράριο", required=True),  
            "⚓ Ναυτολόγηση": st.column_config.SelectboxColumn("⚓ Ναυτολόγηση", options=marine_options, required=True),  
            "Δευτέρα": st.column_config.NumberColumn("Δευτέρα", min_value=0, max_value=10, step=1, default=0, required=True),  
            "Τρίτη": st.column_config.NumberColumn("Τρίτη", min_value=0, max_value=10, step=1, default=0, required=True),  
            "Τετάρτη": st.column_config.NumberColumn("Τετάρτη", min_value=0, max_value=10, step=1, default=0, required=True),  
            "Πέμπτη": st.column_config.NumberColumn("Πέμπτη", min_value=0, max_value=10, step=1, default=0, required=True),  
            "Παρασκευή": st.column_config.NumberColumn("Παρασκευή", min_value=0, max_value=10, step=1, default=0, required=True),  
            "Σάββατο": st.column_config.NumberColumn("Σάββατο", min_value=0, max_value=10, step=1, default=0, required=True),  
            "Κυριακή": st.column_config.NumberColumn("Κυριακή", min_value=0, max_value=10, step=1, default=0, required=True),  
        },  
        key="master_zones_editor"  
    )  

    if not edited_zones_df.equals(df_zones):  
        updated_records = edited_zones_df.dropna(subset=["Πόστο", "Ωράριο"]).to_dict('records')  
        st.session_state.zones_matrix = sort_matrix(updated_records)  
        persist_current_state()  

    current_matrix = st.session_state.zones_matrix
    active_kpis = calculate_role_kpis(current_matrix, st.session_state.employees)
    current_reqs = matrix_to_requirements(current_matrix)
    
    # Πλήρης Προληπτική Επίλυση (Live Solver Pre-Check)
    pre_status, _ = solve_full_schedule(st.session_state.employees, current_reqs, time_limit=1.5)
    pre_issues = []
    if pre_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        pre_issues = diagnose_schedule_failure(st.session_state.employees, current_reqs, pre_status)

    # Απόδοση στην κορυφή του Manager Tab
    with top_banner_placeholder.container():
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

        if pre_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            st.success("🟢 **Πλήρης Ετοιμότητα Προγράμματος:** Το πρόγραμμα είναι 100% επιλύσιμο! Όλες οι βάρδιες, τα ρεπό, ο κανόνας 10ώρου (max 12h για 1 μέρα) και οι ναυτολογήσεις (2 άτομα, 5+ μεροκάματα, 40+ ώρες) καλύπτονται άψογα.")
        else:
            st.error(f"🔴 **ΠΡΟΕΙΔΟΠΟΙΗΣΗ: Το πρόγραμμα ΔΕΝ θα βγει! Εντοπίστηκαν {len(pre_issues)} σημεία εμπλοκής:**")
            df_issues = pd.DataFrame(pre_issues)
            st.dataframe(
                df_issues,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Πόστο": st.column_config.TextColumn("Πόστο", width="medium"),
                    "Ημέρα": st.column_config.TextColumn("Ημέρα", width="medium"),
                    "Τύπος Προβλήματος": st.column_config.TextColumn("Τύπος Προβλήματος", width="large"),
                    "Βάρδια / Ώρες": st.column_config.TextColumn("Βάρδια / Ώρες", width="medium"),
                }
            )
        st.divider()

# ---------------------------------------------------------  
# TAB 3: ΕΠΙΛΥΣΗ, ΕΓΧΡΩΜΟ FORMAT & EXCEL EXPORT  
# ---------------------------------------------------------  
with tab3:  
    st.subheader("Αυτόματη Δημιουργία & Επεξεργασία Προγράμματος")  
  
    if st.button("🚀 Υπολογισμός Προγράμματος (OR-Tools)", type="primary"):  
        active_reqs = matrix_to_requirements(st.session_state.zones_matrix)  
        
        status, all_shifts = solve_full_schedule(st.session_state.employees, active_reqs, time_limit=10.0)  
  
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):  
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
            persist_current_state()  
            st.success("🎉 Το πρόγραμμα υπολογίστηκε άψογα με πλήρη τήρηση όλων των κανόνων και των ναυτολογήσεων!")  
            st.rerun()  
        else:  
            st.session_state.matrix_schedule = None  
            st.session_state.last_shifts_raw = []  
            persist_current_state()  
            
            issues = diagnose_schedule_failure(st.session_state.employees, active_reqs, status)  
            st.error("❌ **Αδύνατη η εύρεση νόμιμης λύσης!** Το πρόγραμμα δεν μπορεί να δημιουργηθεί χωρίς να παραβιαστούν βασικοί κανόνες.")  
            st.markdown("### 🔍 Ακριβής Εντοπισμός Προβλημάτων ανά Πόστο & Ημέρα:")  
            st.dataframe(
                pd.DataFrame(issues), 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Πόστο": st.column_config.TextColumn("Πόστο", width="medium"),
                    "Ημέρα": st.column_config.TextColumn("Ημέρα", width="medium"),
                    "Τύπος Προβλήματος": st.column_config.TextColumn("Τύπος Προβλήματος", width="large"),
                    "Βάρδια / Ώρες": st.column_config.TextColumn("Βάρδια / Ώρες", width="medium"),
                }
            )  
            st.write("")  

    # ---------------------------------------------------------  
    # DISPLAY SCHEDULE & AUDIT  
    # ---------------------------------------------------------  
    if st.session_state.matrix_schedule is not None:  
        st.divider()  
        st.markdown("### ✏️ Επεξεργάσιμο Πρόγραμμα Βαρδιών")  
        st.caption("💡 Μπορείτε να επεξεργαστείτε οποιοδήποτε κελί (π.χ. να αλλάξετε ωράριο ή να βάλετε `ΡΕΠΟ`). Οι αλλαγές σας αποθηκεύονται αυτόματα και μόνιμα.")  
  
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
        
        if not edited_matrix.equals(st.session_state.matrix_schedule):  
            st.session_state.matrix_schedule = edited_matrix  
            persist_current_state()  
            st.rerun()  

        # Audit Ναυτολογημένων: Έλεγχος 5+ Ημερών, 40+ Ωρών & 11-12ωρου  
        with st.expander("⚓ Έλεγχος Ναυτολογημένων & Ωρών Εργασίας", expanded=True):  
            raw_shifts = st.session_state.get("last_shifts_raw", [])  
            marines_list = [e for e in st.session_state.employees if e["is_marine"] and e["role"] in ["Bar", "Service"]]  
            
            marine_stats = []  
            for m in marines_list:  
                m_shifts = [s for s in raw_shifts if s["name"] == m["name"]]  
                shifts_count = len(m_shifts)  
                tot_hours = sum(s.get("hours", 0) for s in m_shifts)  
                overtime_shifts = [f"{s['day']} ({s['hours']}h)" for s in m_shifts if s.get("hours", 0) > 10]
                ot_str = ", ".join(overtime_shifts) if overtime_shifts else "Καμία (≤10h)"
                
                marine_stats.append({  
                    "Εργαζόμενος": f"{m['name']} ⚓",  
                    "Πόστο": m["role"],  
                    "Επιθυμητά": f"{m['target_shifts']} μεροκάματα",  
                    "Πραγματικά": f"{shifts_count} / 7",  
                    "Συνολικές Ώρες": f"{tot_hours} ώρες",  
                    "Κανόνας 40+ Ωρών": "✅ Πληρούται" if tot_hours >= 40 else f"⚠️ {tot_hours}/40 ώρες",  
                    "Κανόνας 5+ Μεροκάματα": "✅ Πληρούται" if shifts_count >= 5 else f"❌ {shifts_count} (<5)",
                    "Βάρδια >10ωρο (max 1 μέρα)": f"✅ {ot_str}" if len(overtime_shifts) <= 1 else f"❌ {len(overtime_shifts)} ημέρες"
                })  
            st.dataframe(pd.DataFrame(marine_stats), use_container_width=True, hide_index=True)  
  
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