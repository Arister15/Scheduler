import io
import math
import copy
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from ortools.sat.python import cp_model
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

app = FastAPI(title="Shift Scheduler Solver API")

# Επιτρέπουμε κλήσεις από το GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DAYS = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]
ROLES = ["Bar", "Service", "Υποδοχή"]
HOURS = list(range(11, 26))

STANDARD_SLOTS = [
    {"label": "11:00 - 18:00", "start": 11, "end": 18, "duration": 7},
    {"label": "18:00 - 22:00", "start": 18, "end": 22, "duration": 4},
    {"label": "22:00 - 01:00", "start": 22, "end": 25, "duration": 3}
]

def format_hour(h: int) -> str:
    if h < 24:
        return f"{h:02d}:00"
    elif h == 24:
        return "00:00"
    else:
        return "01:00"

def get_slot_bounds(slot_str: str):
    slot_clean = str(slot_str).strip()
    for s in STANDARD_SLOTS:
        if s["label"] == slot_clean:
            return s["start"], s["end"], s["duration"]
    try:
        parts = slot_clean.split(" - ") if " - " in slot_clean else slot_clean.split("-")
        s_val = int(parts[0].strip().split(":")[0])
        e_raw = parts[1].strip().split(":")[0]
        e_val = 25 if e_raw in ["01", "1"] else (24 if e_raw in ["00", "0"] else int(e_raw))
        if e_val < s_val and e_val <= 3:
            e_val += 24
        return s_val, e_val, max(0, e_val - s_val)
    except Exception:
        return 11, 18, 7

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
        avail_count = sum(1 for d in DAYS if e["unavailability"].get(d, {}).get("status") != "all_day")
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
            for d in DAYS:
                u = e["unavailability"].get(d, {"status": "available"})
                if u["status"] == "all_day":
                    model.Add(works_day[(eid, d)] == 0)
                    for h in range(11, 25):
                        model.Add(x[(eid, d, h)] == 0)
                elif u["status"] == "custom":
                    for h in range(u.get("start", 11), u.get("end", 17)):
                        if h in range(11, 25):
                            model.Add(x[(eid, d, h)] == 0)

        total_weekly_hours = sum(x[(eid, d, h)] for d in DAYS for h in range(11, 25))

        if e.get("is_marine") and e.get("role") in ["Bar", "Service"]:
            min_sh = min(5, avail_count)
            max_sh = min(max(5, e.get("target_shifts", 5)), avail_count)
            if relax not in ("no_min_shifts", "compound_all"):
                model.Add(sum(works_day[(eid, d)] for d in DAYS) >= min_sh)
            if relax not in ("no_max_shifts", "compound_all"):
                model.Add(sum(works_day[(eid, d)] for d in DAYS) <= max_sh)
            if relax not in ("no_marine_hours", "compound_all"):
                min_weekly_h = 40 if avail_count >= 5 else (avail_count * 8)
                model.Add(total_weekly_hours >= min_weekly_h)
        else:
            eff_max = min(e.get("target_shifts", 5), avail_count)
            eff_min = max(0, min(e.get("target_shifts", 5) - 1, avail_count))
            if relax not in ("no_min_shifts", "compound_all"):
                model.Add(sum(works_day[(eid, d)] for d in DAYS) >= eff_min)
            if relax not in ("no_max_shifts", "compound_all"):
                model.Add(sum(works_day[(eid, d)] for d in DAYS) <= eff_max)

    for r in ROLES:
        staff_r = [e for e in employees if e.get("role") == r]
        reqs_r = [rq for rq in all_reqs if rq["role"] == r]
        for d in DAYS:
            for h in range(11, 25):
                needed_staff = 0
                for rq in reqs_r:
                    if rq["day"] == d and rq["start"] <= h < rq["end"]:
                        needed_staff = max(needed_staff, rq["min_staff"])
                if needed_staff > 0:
                    model.Add(sum(x[(e["id"], d, h)] for e in staff_r) >= needed_staff)

    marines_bs = [e for e in employees if e.get("is_marine") and e.get("role") in ["Bar", "Service"]]
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
                        "is_marine": e.get("is_marine", False),
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
        return [{"Πόστο": "Γενικό", "Ημέρα": "Όλη την εβδομάδα", "Πρόβλημα": "⏱️ Timeout Solver", "Ώρες": "11:00 - 01:00"}]

    for r in ROLES:
        staff_r = [e for e in employees if e.get("role") == r]
        reqs_r = [rq for rq in all_reqs if rq["role"] == r]
        if not staff_r and reqs_r:
            issues.append({"Πόστο": r, "Ημέρα": "Όλες", "Πρόβλημα": "❌ Έλλειψη Προσωπικού", "Ώρες": "11:00 - 01:00"})
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
                        avail = sum(1 for e in staff_r if e["unavailability"].get(d, {}).get("status") != "all_day" and not (e["unavailability"].get(d, {}).get("status") == "custom" and e["unavailability"][d]["start"] <= h < e["unavailability"][d]["end"]))
                        if avail < needed:
                            slot_has_issue = True
                            break
                if slot_has_issue:
                    seen_slots.add(slot_key)
                    issues.append({"Πόστο": r, "Ημέρα": d, "Πρόβλημα": "🚫 Έλλειψη στη Βάρδια", "Ώρες": f"{format_hour(rq['start'])} - {format_hour(rq['end'])}"})

    if not issues:
        issues.append({"Πόστο": "Όλα", "Ημέρα": "Εβδομαδιαίο", "Πρόβλημα": "⚠️ Σύνθετη Σύγκρουση Περιορισμών / Ναυτολόγησης", "Ώρες": "11:00 - 01:00"})
    return issues

def create_styled_excel(schedule_matrix):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Πρόγραμμα Βαρδιών"

    role_hex = {"Service": "FCE5CD", "Bar": "CFE2F3", "Υποδοχή": "FFF2CC"}
    border = Border(left=Side(style='thin', color='A6A6A6'), right=Side(style='thin', color='A6A6A6'),
                    top=Side(style='thin', color='A6A6A6'), bottom=Side(style='thin', color='A6A6A6'))
    h_font = Font(name='Arial', size=11, bold=True, color='000000')
    h_fill = PatternFill(start_color='F3F3F3', end_color='F3F3F3', fill_type='solid')

    headers = ["Πόστο", "Εργαζόμενος"] + DAYS
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = h_font
        cell.fill = h_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border

    for r_idx, row in enumerate(schedule_matrix, start=2):
        row_vals = [row.get(h, "") for h in headers]
        ws.append(row_vals)
        bg = role_hex.get(row.get("Πόστο"), "FFFFFF")
        fill_color = PatternFill(start_color=bg, end_color=bg, fill_type='solid')

        for c_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=r_idx, column=c_idx)
            cell.fill = fill_color
            cell.border = border
            val_str = str(cell.value)
            if h in ["Εργαζόμενος", "Πόστο"]:
                cell.font = Font(name='Arial', size=10, bold=True)
                cell.alignment = Alignment(horizontal='left', vertical='center', indent=1)
            else:
                cell.alignment = Alignment(horizontal='center', vertical='center')
                cell.font = Font(name='Arial', size=10, bold=(val_str == "ΡΕΠΟ"), color='C00000' if val_str == "ΡΕΠΟ" else '000000')

    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 18

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out

# API REQUEST MODELS
class SolveRequest(BaseModel):
    employees: List[Dict[str, Any]]
    zones_matrix: List[Dict[str, Any]]

class ExcelRequest(BaseModel):
    schedule_matrix: List[Dict[str, Any]]

@app.get("/api/health")
def health():
    return {"status": "ok", "message": "Solver API is running"}

@app.post("/api/solve")
def solve_api(req: SolveRequest):
    reqs = matrix_to_requirements(req.zones_matrix)
    status, raw_shifts = solve_full_schedule(req.employees, reqs, time_limit=9.0)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        shift_map = {(s["day"], s["name"]): s["shift"] for s in raw_shifts}
        role_order = {r: i for i, r in enumerate(ROLES)}
        sorted_emps = sorted(req.employees, key=lambda e: (role_order.get(e.get("role"), 99), e.get("name", "")))

        schedule_rows = []
        for e in sorted_emps:
            emp_disp = f"{e['name']} ⚓" if e.get("is_marine") else e["name"]
            row = {"Πόστο": e.get("role", ""), "Εργαζόμενος": emp_disp}
            for d in DAYS:
                row[d] = shift_map.get((d, e["name"]), "ΡΕΠΟ")
            schedule_rows.append(row)

        return {"success": True, "schedule_matrix": schedule_rows, "raw_shifts": raw_shifts}
    else:
        issues = diagnose_schedule_failure(req.employees, reqs, status)
        return {"success": False, "issues": issues}

@app.post("/api/export-excel")
def export_excel(req: ExcelRequest):
    excel_stream = create_styled_excel(req.schedule_matrix)
    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=programma_vardion.xlsx"}
    )