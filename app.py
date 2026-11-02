import streamlit as st  
import pandas as pd  
import json  
import os  
import io  
import math  
import copy  
from datetime import datetime
from ortools.sat.python import cp_model  
import openpyxl  
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side  

# ---------------------------------------------------------  
# STREAMLIT CONFIG & PWA / MOBILE INJECTION  
# ---------------------------------------------------------  
st.set_page_config(
    page_title="Shift Scheduler Pro", 
    page_icon="📋", 
    layout="wide",
    initial_sidebar_state="collapsed"
)  

st.markdown("""
<!-- PWA & Mobile Optimization Scripts / Styles -->
<script>
(function() {
    try {
        const topDoc = window.top.document;
        const head = topDoc.head || document.head;

        // Meta tags for mobile webapp
        const metas = [
            { name: "apple-mobile-web-app-capable", content: "yes" },
            { name: "apple-mobile-web-app-status-bar-style", content: "black-translucent" },
            { name: "apple-mobile-web-app-title", content: "ShiftPro" },
            { name: "mobile-web-app-capable", content: "yes" },
            { name: "theme-color", content: "#0f172a" },
            { name: "viewport", content: "width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover" }
        ];

        metas.forEach(m => {
            if (!head.querySelector(`meta[name="${m.name}"]`)) {
                const el = topDoc.createElement('meta');
                el.name = m.name;
                el.content = m.content;
                head.appendChild(el);
            }
        });

        // Web Manifest Data URI
        if (!head.querySelector('link[rel="manifest"]')) {
            const manifest = {
                name: "Shift Scheduler Pro",
                short_name: "ShiftPro",
                start_url: window.top.location.href,
                display: "standalone",
                orientation: "portrait",
                background_color: "#0f172a",
                theme_color: "#2563eb",
                icons: [
                    {
                        src: "https://api.iconify.design/lucide:calendar-clock.svg?color=%232563eb&width=192&height=192",
                        sizes: "192x192",
                        type: "image/svg+xml"
                    },
                    {
                        src: "https://api.iconify.design/lucide:calendar-clock.svg?color=%232563eb&width=512&height=512",
                        sizes: "512x512",
                        type: "image/svg+xml"
                    }
                ]
            };
            const blob = new Blob([JSON.stringify(manifest)], { type: "application/json" });
            const link = topDoc.createElement('link');
            link.rel = 'manifest';
            link.href = URL.createObjectURL(blob);
            head.appendChild(link);
        }

        // Apple Touch Icon
        if (!head.querySelector('link[rel="apple-touch-icon"]')) {
            const appleLink = topDoc.createElement('link');
            appleLink.rel = 'apple-touch-icon';
            appleLink.href = 'https://api.iconify.design/lucide:calendar-clock.svg?color=%232563eb&width=180&height=180';
            head.appendChild(appleLink);
        }
    } catch(e) {
        console.warn("PWA headers injection:", e);
    }
})();
</script>

<style>
/* ---------------- APP WRAPPER & SAFE AREAS ---------------- */
.stApp {
    padding-top: env(safe-area-inset-top, 0px) !important;
    padding-bottom: env(safe-area-inset-bottom, 12px) !important;
    padding-left: env(safe-area-inset-left, 0px) !important;
    padding-right: env(safe-area-inset-right, 0px) !important;
    touch-action: manipulation;
    -webkit-tap-highlight-color: transparent;
}

.block-container {
    padding-top: 0.8rem !important;
    padding-bottom: 2.5rem !important;
    padding-left: 0.85rem !important;
    padding-right: 0.85rem !important;
    max-width: 100% !important;
}

/* Hide Streamlit Chrome clutter for native look */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header[data-testid="stHeader"] {
    background: transparent !important;
}
header[data-testid="stHeader"] button[title="View fullscreen"] {
    display: none;
}

/* ---------------- TABS STYLING (TOUCH FRIENDLY) ---------------- */
div[data-baseweb="tab-list"] {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    padding-bottom: 4px;
    border-bottom: 2px solid rgba(148, 163, 184, 0.25);
}
div[data-baseweb="tab-list"]::-webkit-scrollbar {
    display: none;
}
button[data-baseweb="tab"] {
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    border-radius: 12px 12px 0 0 !important;
    padding: 10px 14px !important;
    min-height: 46px !important;
    white-space: nowrap !important;
}

/* ---------------- BUTTONS & TOUCH TARGETS ---------------- */
button[kind="primary"], button[kind="secondary"] {
    border-radius: 12px !important;
    font-weight: 600 !important;
    min-height: 48px !important;
    font-size: 0.95rem !important;
    transition: transform 0.1s ease, background-color 0.2s ease !important;
}
button[kind="primary"]:active, button[kind="secondary"]:active {
    transform: scale(0.98) !important;
}

/* ---------------- METRIC CARDS ---------------- */
div[data-testid="stMetric"] {
    background: rgba(148, 163, 184, 0.08);
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 14px;
    padding: 12px 16px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
}

/* ---------------- EXPANDERS & CARDS ---------------- */
div[data-testid="stExpander"] {
    border: 1px solid rgba(148, 163, 184, 0.22) !important;
    border-radius: 14px !important;
    background: rgba(148, 163, 184, 0.04);
    margin-bottom: 12px;
}

/* ---------------- MOBILE ADAPTATION ---------------- */
@media (max-width: 768px) {
    .block-container {
        padding-left: 0.6rem !important;
        padding-right: 0.6rem !important;
    }
    
    div[data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        gap: 10px !important;
    }
    
    div[data-testid="column"] {
        min-width: 100% !important;
        flex: 1 1 100% !important;
    }

    .stSelectbox, .stTextInput, .stSlider {
        margin-bottom: 0.4rem;
    }
}

/* Card UI components */
.pwa-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
    background: rgba(37, 99, 235, 0.12);
    color: #2563eb;
    margin-bottom: 8px;
}
.mobile-shift-card {
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 12px;
    padding: 12px 14px;
    margin-bottom: 10px;
    background: rgba(255, 255, 255, 0.04);
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.mobile-shift-time {
    font-weight: 700;
    padding: 4px 10px;
    border-radius: 8px;
    font-size: 0.88rem;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------  
# PWA INSTALL BANNER / INSTRUCTIONS  
# ---------------------------------------------------------  
with st.expander("📲 Εγκατάσταση στο κινητό σας (iPhone / Android WebApp)", expanded=False):
    st.markdown("""
    **Για να λειτουργεί σαν κανονική εφαρμογή χωρίς μπάρες browser:**
    * **iPhone / iPad (Safari):** Πατήστε το κουμπί **Κοινοποίηση (Share ⎋)** στο κάτω μέρος και επιλέξτε **«Προσθήκη στην οθόνη αφετηρίας» (Add to Home Screen ➕)**.
    * **Android (Chrome):** Πατήστε τις **3 τελείες (⋮)** επάνω δεξιά και επιλέξτε **«Εγκατάσταση εφαρμογής»** ή **«Προσθήκη στην αρχική οθόνη»**.
    """)

# ---------------------------------------------------------  
# ΣΤΑΘΕΡΕΣ & ΑΡΧΙΚΑ ΔΕΔΟΜΕΝΑ  
# ---------------------------------------------------------  
DAYS = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]  
ROLES = ["Bar", "Service", "Υποδοχή"]  
HOURS = list(range(11, 26))  # 11:00 έως 25 (01:00)  
DATA_FILE = "scheduler_data.json"  

DEFAULT_STAFF_CONFIG = [
    {"name": "Άρης", "role": "Bar", "is_marine": False, "target_shifts": 5},
    {"name": "Βαγγέλης", "role": "Bar", "is_marine": False, "target_shifts": 5},
    {"name": "Γιάννης", "role": "Bar", "is_marine": True, "target_shifts": 5},
    {"name": "Κώστας", "role": "Bar", "is_marine": True, "target_shifts": 6},
    {"name": "Φωτεινή", "role": "Service", "is_marine": True, "target_shifts": 5},
    {"name": "Μαρία", "role": "Service", "is_marine": False, "target_shifts": 5},
    {"name": "Θεόφιλος", "role": "Service", "is_marine": True, "target_shifts": 6},
    {"name": "Σαλώμη", "role": "Service", "is_marine": False, "target_shifts": 5},
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
        {"Πόστο": "Bar", "Ωράριο": "11:00 - 18:00", "⚓ Ναυτολόγηση": "Όχι", "Δευτέρα": 1, "Τρίτη": 1, "Τετάρτη": 1, "Πέμπτη": 1, "Παρασκευή": 1, "Σάββατο": 1, "Κυριακή": 1},  
        {"Πόστο": "Bar", "Ωράριο": "18:00 - 22:00", "⚓ Ναυτολόγηση": "Όλες τις ημέρες", "Δευτέρα": 2, "Τρίτη": 2, "Τετάρτη": 2, "Πέμπτη": 2, "Παρασκευή": 2, "Σάββατο": 2, "Κυριακή": 2},  
        {"Πόστο": "Bar", "Ωράριο": "22:00 - 01:00", "⚓ Ναυτολόγηση": "Όλες τις ημέρες", "Δευτέρα": 1, "Τρίτη": 1, "Τετάρτη": 1, "Πέμπτη": 1, "Παρασκευή": 1, "Σάββατο": 1, "Κυριακή": 1},  
        {"Πόστο": "Service", "Ωράριο": "11:00 - 18:00", "⚓ Ναυτολόγηση": "Όχι", "Δευτέρα": 1, "Τρίτη": 1, "Τετάρτη": 1, "Πέμπτη": 1, "Παρασκευή": 1, "Σάββατο": 1, "Κυριακή": 1},  
        {"Πόστο": "Service", "Ωράριο": "18:00 - 22:00", "⚓ Ναυτολόγηση": "Όλες τις ημέρες", "Δευτέρα": 2, "Τρίτη": 2, "Τετάρτη": 2, "Πέμπτη": 2, "Παρασκευή": 2, "Σάββατο": 2, "Κυριακή": 2},  
        {"Πόστο": "Service", "Ωράριο": "22:00 - 01:00", "⚓ Ναυτολόγηση": "Όλες τις ημέρες", "Δευτέρα": 1, "Τρίτη": 1, "Τετάρτη": 1, "Πέμπτη": 1, "Παρασκευή": 1, "Σάββατο": 1, "Κυριακή": 1},  
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
        "matrix": sanitize_for_json(matrix),
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

if "zones_editor_ver" not in st.session_state:
    st.session_state.zones_editor_ver = 0

# ---------------------------------------------------------  
# KPIs & SOLVER LOGIC (OR-TOOLS CP-SAT)  
# ---------------------------------------------------------  
def calculate_role_kpis(matrix, employees):  
    kpis = {}  
    for r in ROLES:  
        staff_r = [e for e in employees if e["role"] == r]  
        marines_r = [e for e in staff_r if e["is_marine"]]  
        role_rows = [row for row in matrix if row["Πόστο"] == r]  
  
        total_hours = 0  
        for d in DAYS:  
            daily_hours = 0  
            for row in role_rows:  
                _, _, dur = get_slot_bounds(str(row["Ωράριο"]))  
                needed = int(row.get(d, 0) or 0)  
                daily_hours += (needed * dur)  
            total_hours += daily_hours  
  
        avail_shifts = sum(e["target_shifts"] for e in staff_r)  
        avail_mar_shifts = sum(e["target_shifts"] for e in marines_r)  
        avail_hours = avail_shifts * 8  
  
        if avail_hours < total_hours:  
            status = "🔴 Έλλειψη Ωρών"  
        elif avail_hours == total_hours:  
            status = "⚠️ Οριακό (0 Slack)"  
        else:  
            status = "🟢 Πλήρης Κάλυψη"  
  
        kpis[r] = {  
            "staff_count": len(staff_r),  
            "marine_count": len(marines_r),  
            "hours": total_hours,  
            "avail_hours": avail_hours,
            "avail_shifts": avail_shifts,  
            "avail_mar_shifts": avail_mar_shifts,  
            "status": status  
        }  
    return kpis  

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

def solve_full_schedule(employees, all_reqs, relax=None, time_limit=8.0):  
    model = cp_model.CpModel()  
    
    x = {}  
    works_day = {}  
    all_overtime_vars = []
    all_5h_vars = []
    all_6h_vars = []
    
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
            
            is_overtime = model.NewBoolVar(f"ot_{eid}_{d}")
            emp_overtimes.append(is_overtime)
            all_overtime_vars.append(is_overtime)
            
            model.Add(sum(daily_hours) <= 10).OnlyEnforceIf(is_overtime.Not())
            model.Add(sum(daily_hours) <= 12).OnlyEnforceIf(is_overtime)
            model.Add(sum(daily_hours) >= 11).OnlyEnforceIf(is_overtime)
            
            is_5h = model.NewBoolVar(f"is_5h_{eid}_{d}")
            is_6h = model.NewBoolVar(f"is_6h_{eid}_{d}")
            all_5h_vars.append(is_5h)
            all_6h_vars.append(is_6h)
            
            model.Add(is_5h == 0).OnlyEnforceIf(works_day[(eid, d)].Not())
            model.Add(is_6h == 0).OnlyEnforceIf(works_day[(eid, d)].Not())

            if relax != "no_min_hours":  
                model.Add(sum(daily_hours) >= 5).OnlyEnforceIf(works_day[(eid, d)])  
                model.Add(sum(daily_hours) >= 6).OnlyEnforceIf([works_day[(eid, d)], is_5h.Not()])
                model.Add(sum(daily_hours) >= 7).OnlyEnforceIf([works_day[(eid, d)], is_5h.Not(), is_6h.Not()])
                
            starts = []  
            for i, h in enumerate(range(11, 25)):  
                st_var = model.NewBoolVar(f"st_{eid}_{d}_{h}")  
                if i == 0:  
                    model.Add(st_var == x[(eid, d, h)])  
                else:  
                    model.Add(st_var >= x[(eid, d, h)] - x[(eid, d, h - 1)])  
                starts.append(st_var)  
            model.Add(sum(starts) <= 1)  
            
        model.Add(sum(emp_overtimes) <= 1)
            
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
                    
    total_hours = sum(x[(e["id"], d, h)] for e in employees for d in DAYS for h in range(11, 25))  
    total_ot_penalty = sum(all_overtime_vars)
    penalty_5h = sum(all_5h_vars)
    penalty_6h = sum(all_6h_vars)
    
    model.Minimize(total_hours * 10 + total_ot_penalty * 20 + penalty_5h * 300 + penalty_6h * 60)  
    
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
        total_avail_hours = total_avail_shifts * 10  
        total_needed_hours = sum((rq["end"] - rq["start"]) * rq["min_staff"] for rq in reqs_r)
            
        if total_avail_hours < total_needed_hours:  
            role_hours = [(rq["start"], rq["end"]) for rq in reqs_r]
            time_frame = f"{format_hour(min(h[0] for h in role_hours))} - {format_hour(max(h[1] for h in role_hours))}" if role_hours else "11:00 - 01:00"
            issues.append({
                "Πόστο": r,
                "Ημέρα": "Όλη την εβδομάδα",
                "Τύπος Προβλήματος": "📈 Ανεπάρκεια Ώρων Εργασίας",
                "Βάρδια / Ώρες": time_frame
            })
            
    marines_bs = [e for e in employees if e["is_marine"] and e["role"] in ["Bar", "Service"]]  
    mar_reqs = [rq for rq in all_reqs if rq.get("require_marine")]
    mar_time_frame = f"{format_hour(min(rq['start'] for rq in mar_reqs))} - {format_hour(max(rq['end'] for rq in mar_reqs))}" if mar_reqs else "18:00 - 01:00"

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
                    avail_mar = sum(1 for e in marines_bs if e["unavailability"].get(d, {}).get("status") != "all_day" and not (e["unavailability"].get(d, {}).get("status") == "custom" and e["unavailability"][d]["start"] <= h < e["unavailability"][d]["end"]))
                    if avail_mar < 2:
                        slot_mar_issue = True
                        break
                if slot_mar_issue:
                    seen_mar_slots.add(slot_key)
                    issues.append({
                        "Πόστο": "Bar & Service (Κοινό)",
                        "Ημέρα": d,
                        "Τύπος Προβλήματος": "⚓ Έλλειψη Ναυτολογημένων",
                        "Βάρδια / Ώρες": f"{format_hour(rq['start'])} - {format_hour(rq['end'])}"
                    })

    if not issues:  
        issues.append({
            "Πόστο": "Όλα τα Πόστα",
            "Ημέρα": "Εβδομαδιαίο",
            "Τύπος Προβλήματος": "⚠️ Σύνθετη Σύγκρουση Περιορισμών",
            "Βάρδια / Ώρες": "11:00 - 01:00"
        })
    return issues  

def apply_editor_changes(matrix, changes):
    mat = copy.deepcopy(matrix)
    edited_rows = changes.get("edited_rows", {})
    added_rows = changes.get("added_rows", [])
    deleted_rows = changes.get("deleted_rows", [])
    
    for idx_raw, row_changes in edited_rows.items():
        row_idx = int(idx_raw)
        if 0 <= row_idx < len(mat):
            for col_k, col_v in row_changes.items():
                if col_k in DAYS:
                    try:
                        mat[row_idx][col_k] = int(col_v or 0)
                    except (ValueError, TypeError):
                        mat[row_idx][col_k] = 0
                else:
                    mat[row_idx][col_k] = col_v
                    
    if deleted_rows:
        for idx_raw in sorted([int(i) for i in deleted_rows], reverse=True):
            if 0 <= idx_raw < len(mat):
                mat.pop(idx_raw)

    if added_rows:
        for new_row in added_rows:
            clean_row = {
                "Πόστο": new_row.get("Πόστο", "Bar"),
                "Ωράριο": new_row.get("Ωράριο", "18:00 - 01:00"),
                "⚓ Ναυτολόγηση": new_row.get("⚓ Ναυτολόγηση", "Όχι"),
            }
            for d in DAYS:
                try:
                    clean_row[d] = int(new_row.get(d, 0) or 0)
                except (ValueError, TypeError):
                    clean_row[d] = 0
            mat.append(clean_row)
    return mat

def create_styled_excel(df):  
    wb = openpyxl.Workbook()  
    ws = wb.active  
    ws.title = "Πρόγραμμα Βαρδιών"  
  
    role_hex_colors = {"Service": "FCE5CD", "Bar": "CFE2F3", "Υποδοχή": "FFF2CC"}  
    thin_border = Border(
        left=Side(style='thin', color='A6A6A6'),
        right=Side(style='thin', color='A6A6A6'),
        top=Side(style='thin', color='A6A6A6'),
        bottom=Side(style='thin', color='A6A6A6')
    )  
    header_font = Font(name='Arial', size=11, bold=True, color='000000')  
    header_fill = PatternFill(start_color='F3F3F3', end_color='F3F3F3', fill_type='solid')  
    bold_repo_font = Font(name='Arial', size=10, bold=True, color='C00000')  
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
                cell.font = bold_repo_font if val_str == "ΡΕΠΟ" else regular_font  
  
    for col in ws.columns:  
        col_letter = col[0].column_letter  
        ws.column_dimensions[col_letter].width = 18  
  
    output = io.BytesIO()  
    wb.save(output)  
    output.seek(0)  
    return output  

# ---------------------------------------------------------  
# APP HEADER  
# ---------------------------------------------------------  
st.title("📋 Shift Scheduler Pro")

tab1, tab2, tab3 = st.tabs([
    "👤 Καρτέλα Υπαλλήλου", 
    "⚙️ Ρυθμίσεις Manager", 
    "📅 Τελικό Πρόγραμμα"
])  

# ---------------------------------------------------------  
# TAB 1: ΚΑΡΤΕΛΑ ΥΠΑΛΛΗΛΟΥ  
# ---------------------------------------------------------  
with tab1:  
    st.markdown("### Δήλωση Στοιχείων & Διαθεσιμότητας")  
  
    with st.expander("👥 Διαχείριση Προσωπικού (Προσθήκη / Διαγραφή / Επαναφορά)", expanded=False):  
        c_add, c_del = st.columns(2)  
        with c_add:  
            st.markdown("##### ➕ Προσθήκη Νέου Υπαλλήλου")  
            with st.form("add_new_emp_form"):  
                new_name = st.text_input("Ονοματεπώνυμο:")  
                new_r = st.selectbox("Πόστο:", ROLES, key="add_emp_role")  
                new_mar = st.checkbox("Ναυτολογημένος/η (μόνο Bar/Service)", key="add_emp_marine")  
                new_sh = st.slider("Επιθυμητά μεροκάματα:", 1, 7, 5, key="add_emp_shifts")  
                  
                if st.form_submit_button("Αποθήκευση Υπαλλήλου", use_container_width=True):  
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
                if st.button("❌ Οριστική Διαγραφή", type="secondary", use_container_width=True):  
                    st.session_state.employees = [e for e in st.session_state.employees if e["name"] != del_name]  
                    persist_current_state()  
                    st.success(f"Ο/Η {del_name} διαγράφηκε!")  
                    st.rerun()  

            st.write("")  
            if st.button("🔄 Επαναφορά Προεπιλεγμένων (Reset)", type="secondary", use_container_width=True):  
                st.session_state.employees = build_default_employees()  
                persist_current_state()  
                st.success("Επανήλθαν οι προεπιλεγμένοι εργαζόμενοι!")  
                st.rerun()  
  
    if not st.session_state.employees:  
        st.warning("Δεν υπάρχουν καταχωρημένοι υπάλληλοι.")  
        st.stop()  
  
    emp_names = [e["name"] for e in st.session_state.employees]  
    selected_name = st.selectbox("👉 Επιλέξτε το όνομά σας:", emp_names, key="selected_employee_dropdown")  
    emp = next((e for e in st.session_state.employees if e["name"] == selected_name), st.session_state.employees[0])  
  
    # Quick weekly summary badge row
    st.markdown("#### ⚡ Σύντομη Επισκόπηση Εβδομάδας")  
    quick_dict = {}  
    for d in DAYS:  
        u = emp["unavailability"][d]  
        if u["status"] == "all_day":  
            quick_dict[d] = "🔴 ΡΕΠΟ"  
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
            new_shifts = st.slider("Επιθυμητά μεροκάματα (Ναυτολογημένος: min 5):", 5, 7, value=cur_val, key=f"ui_shifts_{emp['id']}")  
        else:  
            new_shifts = st.slider("Επιθυμητά μεροκάματα εβδομάδας:", 1, 7, value=emp["target_shifts"], key=f"ui_shifts_{emp['id']}")  
  
    st.markdown("---")  
    st.markdown("#### 📅 Αναλυτική Ρύθμιση ανά Ημέρα")  
  
    STATUS_OPTS = ["🟢 Διαθέσιμος/η", "🔴 Όλη μέρα ρεπό", "🟡 Κώλυμα συγκεκριμένες ώρες"]  
    status_to_code = {STATUS_OPTS[0]: "available", STATUS_OPTS[1]: "all_day", STATUS_OPTS[2]: "custom"}  
    code_to_status = {v: k for k, v in status_to_code.items()}  
  
    for d in DAYS:  
        cur_day_data = emp["unavailability"][d]  
        cur_status = code_to_status.get(cur_day_data["status"], STATUS_OPTS[0])  
  
        with st.container():  
            c_label, c_ctrl = st.columns([1.2, 2.8])  
            with c_label:
                st.markdown(f"**🗓️ {d}**")
                chosen_opt = st.radio(
                    f"Κατάσταση {d}", 
                    STATUS_OPTS, 
                    index=STATUS_OPTS.index(cur_status), 
                    key=f"ui_status_{emp['id']}_{d}",
                    label_visibility="collapsed"
                )
            with c_ctrl:
                if chosen_opt == "🟡 Κώλυμα συγκεκριμένες ώρες":  
                    st.select_slider(  
                        f"Ώρες κωλύματος ({d}):",  
                        options=HOURS,  
                        value=(cur_day_data.get("start", 11), cur_day_data.get("end", 17)),  
                        format_func=format_hour,  
                        key=f"ui_slider_{emp['id']}_{d}"  
                    )  
                elif chosen_opt == "🔴 Όλη μέρα ρεπό":  
                    st.info(f"🚫 Δηλωμένο Ρεπό για την {d}")  
                else:  
                    st.success(f"✅ Πλήρης διαθεσιμότητα για την {d}")  
            st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px dashed rgba(148,163,184,0.3);'/>", unsafe_allow_html=True)  
  
    col_submit, col_reset = st.columns([2, 1])  
    with col_submit:  
        if st.button("💾 Αποθήκευση Όλων (Save Changes)", type="primary", use_container_width=True):  
            emp["role"] = new_role  
            emp["is_marine"] = (new_marine and new_role in ["Bar", "Service"])  
            emp["target_shifts"] = new_shifts  
  
            for d in DAYS:  
                chosen_st = st.session_state.get(f"ui_status_{emp['id']}_{d}", STATUS_OPTS[0])  
                code = status_to_code[chosen_st]  
                slider_val = st.session_state.get(f"ui_slider_{emp['id']}_{d}", (11, 17))  
                emp["unavailability"][d] = {"status": code, "start": slider_val[0], "end": slider_val[1]}  
  
            persist_current_state()  
            st.success(f"🎉 Οι αλλαγές για τον/την **{emp['name']}** αποθηκεύτηκαν!")  
            st.rerun()  
  
    with col_reset:  
        if st.button("🗑️ Καθαρισμός Κωλυμάτων", use_container_width=True):  
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
    st.markdown("### Διαχείριση Αναγκών & Ζωνών Προσωπικού")  

    current_matrix = st.session_state.zones_matrix
    active_kpis = calculate_role_kpis(current_matrix, st.session_state.employees)
    current_reqs = matrix_to_requirements(current_matrix)
    
    pre_status, _ = solve_full_schedule(st.session_state.employees, current_reqs, time_limit=1.5)
    pre_issues = []
    if pre_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        pre_issues = diagnose_schedule_failure(st.session_state.employees, current_reqs, pre_status)

    # KPI CARDS
    k1, k2, k3 = st.columns(3)  
    cols_k = [k1, k2, k3]  
    for idx, r in enumerate(ROLES):  
        kpi = active_kpis[r]  
        is_covered = (pre_status in (cp_model.OPTIMAL, cp_model.FEASIBLE)) or (kpi["avail_hours"] >= kpi["hours"])
        metric_status = "🟢 Πλήρης Κάλυψη" if is_covered else "🔴 Έλλειψη Ωρών"
        with cols_k[idx]:  
            st.metric(  
                label=f"{r} | {kpi['staff_count']} άτομα ({kpi['marine_count']} ⚓)",  
                value=f"{kpi['avail_hours']} / {kpi['hours']} h",  
                delta=metric_status,  
                delta_color="normal" if is_covered else "inverse"  
            )  

    if pre_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        st.success("🟢 **Πλήρης Ετοιμότητα Προγράμματος:** Το πρόγραμμα είναι 100% επιλύσιμο! Όλες οι απαιτήσεις, το 10ωρο, το όριο 12ώρου και οι ναυτολογήσεις καλύπτονται.")
    else:
        st.error(f"🔴 **ΠΡΟΕΙΔΟΠΟΙΗΣΗ: Το πρόγραμμα ΔΕΝ θα βγει! Εντοπίστηκαν {len(pre_issues)} προβλήματα:**")
        df_issues = pd.DataFrame(pre_issues)
        st.dataframe(df_issues, use_container_width=True, hide_index=True)

    st.markdown("---")  
    st.markdown("#### 📊 Οπτικό Dashboard Διαθεσιμότητας")  
    dash_tabs = st.tabs(["🍸 Bar", "🍽️ Service", "🛎️ Υποδοχή"])
    
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
                daily_needed_peak[d] = max(h_dem[11:25]) if any(h_dem[11:25]) else 0

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
                cnt = sum(1 for e in staff_r if e["unavailability"].get(d, {}).get("status") != "all_day")
                avail_row[d] = f"{cnt} άτομα"
            dash_rows.append(avail_row)

            needed_row = {"Εργαζόμενος": "📌 Απαιτούμενο (Αιχμή)", "Μεροκάματα": "-"}
            for d in DAYS:
                needed_row[d] = f"{daily_needed_peak[d]} άτομα"
            dash_rows.append(needed_row)

            balance_row = {"Εργαζόμενος": "⚖️ Ισοζύγιο", "Μεροκάματα": "-"}
            for d in DAYS:
                avail_cnt = sum(1 for e in staff_r if e["unavailability"].get(d, {}).get("status") != "all_day")
                diff = avail_cnt - daily_needed_peak[d]
                balance_row[d] = f"🔴 {diff}" if diff < 0 else (f"⚠️ 0" if diff == 0 else f"🟢 +{diff}")
            dash_rows.append(balance_row)

            st.dataframe(pd.DataFrame(dash_rows), use_container_width=True, hide_index=True)

    st.markdown("---")  
    col_tools_add, col_tools_del = st.columns(2)  
    with col_tools_add:  
        with st.expander("➕ Προσθήκη Νέας Ζώνης", expanded=False):  
            with st.form("add_zone_form"):  
                z_role = st.selectbox("Πόστο:", ROLES, key="nz_role")  
                z_slot = st.text_input("Ωράριο (π.χ. 18:00 - 01:00):", value="18:00 - 01:00", key="nz_slot")  
                z_marine = st.selectbox("⚓ Απαίτηση Ναυτολόγησης:", ["Όχι", "Όλες τις ημέρες", "Μόνο Παρ - Κυρ", "Μόνο Δευτ - Πεμ"], key="nz_marine")  
                z_default_count = st.number_input("Πλήθος ατόμων (όλες τις μέρες):", min_value=0, max_value=10, value=1, step=1)  
                
                if st.form_submit_button("Προσθήκη Ζώνης", use_container_width=True):  
                    if not z_slot.strip():  
                        st.error("Συμπληρώστε το ωράριο.")  
                    else:  
                        new_zone = {"Πόστο": z_role, "Ωράριο": z_slot.strip(), "⚓ Ναυτολόγηση": z_marine}  
                        for d in DAYS:  
                            new_zone[d] = int(z_default_count)  
                        
                        st.session_state.zones_matrix.append(new_zone)  
                        st.session_state.zones_matrix = sort_matrix(st.session_state.zones_matrix)  
                        persist_current_state()  
                        st.session_state.zones_editor_ver = st.session_state.get("zones_editor_ver", 0) + 1
                        st.success(f"Η ζώνη {z_role} ({z_slot}) αποθηκεύτηκε!")  
                        st.rerun()  

    with col_tools_del:  
        with st.expander("🗑️ Διαγραφή Ζώνης", expanded=False):  
            if st.session_state.zones_matrix:  
                zone_options = [f"{i+1}. [{row['Πόστο']}] {row['Ωράριο']}" for i, row in enumerate(st.session_state.zones_matrix)]  
                selected_del_idx_str = st.selectbox("Επιλέξτε ζώνη προς διαγραφή:", zone_options, key="del_zone_sel")  
                del_idx = int(selected_del_idx_str.split(".")[0]) - 1  
                
                if st.button("❌ Διαγραφή Αυτής της Ζώνης", type="secondary", use_container_width=True):  
                    deleted_item = st.session_state.zones_matrix.pop(del_idx)  
                    persist_current_state()  
                    st.session_state.zones_editor_ver = st.session_state.get("zones_editor_ver", 0) + 1
                    st.success(f"Η ζώνη [{deleted_item['Πόστο']}] {deleted_item['Ωράριο']} διαγράφηκε!")  
                    st.rerun()  

    editor_ver = st.session_state.get("zones_editor_ver", 0)
    editor_key = f"master_zones_editor_{editor_ver}"
    changes = st.session_state.get(editor_key, {})
    has_changes = bool(changes.get("edited_rows") or changes.get("added_rows") or changes.get("deleted_rows"))

    c_z_head, c_z_save = st.columns([3, 1])
    with c_z_head:
        st.markdown("#### 📝 Ταμπλό Ζωνών (Πλήρως Επεξεργάσιμο)")  
    with c_z_save:
        if has_changes:
            if st.button("💾 Αποθήκευση Ζωνών", type="primary", use_container_width=True):
                updated_matrix = apply_editor_changes(st.session_state.zones_matrix, changes)
                st.session_state.zones_matrix = sort_matrix(updated_matrix)
                persist_current_state()
                st.session_state.zones_editor_ver = editor_ver + 1
                st.success("Οι ζώνες αποθηκεύτηκαν!")
                st.rerun()

    df_zones = pd.DataFrame(st.session_state.zones_matrix)  
    st.data_editor(  
        df_zones,  
        use_container_width=True,  
        num_rows="dynamic",  
        column_config={  
            "Πόστο": st.column_config.SelectboxColumn("Πόστο", options=ROLES, required=True),  
            "Ωράριο": st.column_config.TextColumn("Ωράριο", required=True),  
            "⚓ Ναυτολόγηση": st.column_config.SelectboxColumn("⚓ Ναυτολόγηση", options=["Όχι", "Όλες τις ημέρες", "Μόνο Παρ - Κυρ", "Μόνο Δευτ - Πεμ"], required=True),  
            "Δευτέρα": st.column_config.NumberColumn("Δευτέρα", min_value=0, max_value=10, step=1, default=0),  
            "Τρίτη": st.column_config.NumberColumn("Τρίτη", min_value=0, max_value=10, step=1, default=0),  
            "Τετάρτη": st.column_config.NumberColumn("Τετάρτη", min_value=0, max_value=10, step=1, default=0),  
            "Πέμπτη": st.column_config.NumberColumn("Πέμπτη", min_value=0, max_value=10, step=1, default=0),  
            "Παρασκευή": st.column_config.NumberColumn("Παρασκευή", min_value=0, max_value=10, step=1, default=0),  
            "Σάββατο": st.column_config.NumberColumn("Σάββατο", min_value=0, max_value=10, step=1, default=0),  
            "Κυριακή": st.column_config.NumberColumn("Κυριακή", min_value=0, max_value=10, step=1, default=0),  
        },  
        key=editor_key
    )  

# ---------------------------------------------------------  
# TAB 3: ΕΠΙΛΥΣΗ, ΕΓΧΡΩΜΟ FORMAT & EXCEL EXPORT  
# ---------------------------------------------------------  
with tab3:  
    st.markdown("### Αυτόματη Δημιουργία & Προβολή Προγράμματος")  
  
    if st.button("🚀 Υπολογισμός Προγράμματος (OR-Tools Solver)", type="primary", use_container_width=True):  
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
            st.success("🎉 Το πρόγραμμα υπολογίστηκε άψογα!")  
            st.rerun()  
        else:  
            st.session_state.matrix_schedule = None  
            st.session_state.last_shifts_raw = []  
            persist_current_state()  
            issues = diagnose_schedule_failure(st.session_state.employees, active_reqs, status)  
            st.error("❌ **Αδύνατη η εύρεση νόμιμης λύσης!** Εντοπίστηκαν ασυμβατότητες:")  
            st.dataframe(pd.DataFrame(issues), use_container_width=True, hide_index=True)  

    if st.session_state.matrix_schedule is not None:  
        st.markdown("---")  

        # VIEW SWITCHER: TABLE VS MOBILE CARDS
        c_mode, c_export = st.columns([2, 1.2])
        with c_mode:
            view_mode = st.radio(
                "Τρόπος Προβολής:", 
                ["📱 Ημερήσια Προβολή (Mobile Cards)", "📋 Πλήρης Πίνακας Εβδομάδας"], 
                horizontal=True
            )
        with c_export:
            excel_data = create_styled_excel(st.session_state.matrix_schedule)  
            st.download_button(  
                label="📥 Λήψη σε Excel (.xlsx)",  
                data=excel_data,  
                file_name="programma_vardion.xlsx",  
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  
                type="primary",
                use_container_width=True
            )  

        # 1. MOBILE DAY CARDS VIEW (Φιλική για κινητά)
        if "Mobile Cards" in view_mode:
            st.markdown("##### 🗓️ Επιλέξτε Ημέρα:")
            selected_day = st.selectbox("Ημέρα", DAYS, index=0, label_visibility="collapsed")
            
            raw_shifts = st.session_state.get("last_shifts_raw", [])
            day_shifts = [s for s in raw_shifts if s["day"] == selected_day]

            for role_name in ROLES:
                st.markdown(f"**🏷️ {role_name}**")
                role_shifts = [s for s in day_shifts if s["role"] == role_name]
                if role_shifts:
                    for s in sorted(role_shifts, key=lambda x: x["start_h"]):
                        marine_icon = "⚓ " if s["is_marine"] else ""
                        overtime_badge = " 🔥 (>10h)" if s["is_overtime"] else ""
                        bg_color = "rgba(59, 130, 246, 0.12)" if role_name == "Bar" else ("rgba(245, 158, 11, 0.12)" if role_name == "Service" else "rgba(16, 185, 129, 0.12)")
                        st.markdown(f"""
                        <div class="mobile-shift-card" style="background: {bg_color};">
                            <div>
                                <span style="font-weight: 700; font-size: 1.05rem;">{marine_icon}{s['name']}</span>
                                <span style="font-size: 0.8rem; opacity: 0.8; margin-left: 6px;">({s['hours']} ώρες{overtime_badge})</span>
                            </div>
                            <span class="mobile-shift-time" style="background: rgba(0,0,0,0.25); color: white;">
                                ⏰ {s['shift']}
                            </span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.caption("Κανένας προγραμματισμένος εργαζόμενος.")

            # Ρεπό ημέρας
            working_names = {s["name"] for s in day_shifts}
            off_names = [e["name"] for e in st.session_state.employees if e["name"] not in working_names]
            if off_names:
                st.markdown(f"**🏖️ Ρεπό ({len(off_names)} άτομα):**")
                st.markdown(f"<div style='padding: 8px 12px; border-radius: 10px; background: rgba(239, 68, 68, 0.08); color: #ef4444; font-weight: 600;'>{', '.join(off_names)}</div>", unsafe_allow_html=True)

        # 2. FULL EDITABLE TABLE VIEW (Desktop / Management)
        else:
            st.caption("💡 Κάντε κλικ σε οποιοδήποτε κελί για αλλαγή (οι αλλαγές αποθηκεύονται αυτόματα).")
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

        # Audit Ναυτολογημένων
        with st.expander("⚓ Έλεγχος Ναυτολογημένων & 40ώρου", expanded=False):  
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