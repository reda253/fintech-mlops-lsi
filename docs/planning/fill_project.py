"""Fill the Projects board fields (Owner role, Start, END, Handoff, Status) from the task list.

Uses the same TASKS as create_issues.py. Safe to re-run; it only overwrites these fields.
Status is set only for items still in "Todo" (the auto-add default), so manual moves are kept.

    gh auth refresh -s project      # once
    python docs/planning/fill_project.py
"""
import json
import subprocess

from create_issues import TASKS, year

OWNER, PROJECT_NUMBER = "reda253", 3
PROJECT_ID = "PVT_kwHOBpLm8s4Bl2YJ"
F_OWNER = "PVTSSF_lAHOBpLm8s4Bl2YJzhkhpAc"
F_START = "PVTF_lAHOBpLm8s4Bl2YJzhkhpNI"
F_END = "PVTF_lAHOBpLm8s4Bl2YJzhkhpQc"
F_HANDOFF = "PVTF_lAHOBpLm8s4Bl2YJzhkhpUg"
F_STATUS = "PVTSSF_lAHOBpLm8s4Bl2YJzhkhl1c"
OWNER_OPT = {"P1": "500c1391", "P2": "ff770ab1", "P3": "fc33836f", "P4": "d498e9a7", "P5": "a14ff29d", "ALL": "4453067e"}
STATUS_OPT = {"Backlog": "5704ac22", "Todo": "f75ad846", "In Progress": "47fc9ee4", "Review": "bd5a690a", "Done": "98236657"}
# where things really are on 2026-10-09
STATUS_OVERRIDE = {
    "Architecture, OpenAPI contracts v1, DB schemas": "Review",            # waiting for the team's contract review
    "Repo setup: ruleset on main, CODEOWNERS handles, Projects board, Discord": "In Progress",
}


def gh(*args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout


def iso(d):  # dd/mm -> yyyy-mm-dd
    day, month, yr = year(d).split("/")
    return f"{yr}-{month}-{day}"


def update(alias, item, field, value):
    return (f'{alias}: updateProjectV2ItemFieldValue(input: {{projectId: "{PROJECT_ID}", itemId: "{item}", '
            f'fieldId: "{field}", value: {value}}}) {{ clientMutationId }}')


items = json.loads(gh("project", "item-list", str(PROJECT_NUMBER), "--owner", OWNER, "--limit", "200", "--format", "json"))["items"]
by_title = {i["content"]["title"]: i for i in items if i.get("content")}

done = 0
for role, title, start, end, ms, handoff, _labels, _ref in TASKS:
    item = by_title.get(title)
    if not item:
        print(f"not on board: {title}")
        continue
    iid = item["id"]
    parts = [
        update("o", iid, F_OWNER, f'{{singleSelectOptionId: "{OWNER_OPT[role]}"}}'),
        update("s", iid, F_START, f'{{date: "{iso(start)}"}}'),
        update("e", iid, F_END, f'{{date: "{iso(end)}"}}'),
    ]
    if handoff:
        parts.append(update("h", iid, F_HANDOFF, '{text: ' + json.dumps(handoff) + '}'))
    if item.get("status") in (None, "Todo"):
        status = STATUS_OVERRIDE.get(title, "Todo" if ms <= 2 else "Backlog")
        parts.append(update("st", iid, F_STATUS, f'{{singleSelectOptionId: "{STATUS_OPT[status]}"}}'))
    gh("api", "graphql", "-f", "query=mutation { " + " ".join(parts) + " }")
    done += 1

print(f"updated {done} items")
