"""Shared task-state reconstruction for Claude Code transcript-walking hooks.

Real harness ids come from each TaskCreate's tool_result ("Task #N created
successfully"), matched by tool_use_id. Blocked creates (is_error result, or no
"Task #N" marker) never became tasks and are skipped. Positional fallback is
used only for transcripts that carry no TaskCreate results at all (older /
synthetic records). Streamed in binary so one invalid-UTF-8 byte poisons only
its own line, never the whole scan.
"""
import json
import re
import sys

CREATE_RE = re.compile(r"Task #(\d+) created successfully")
FENCE_RE = re.compile(r"```json:metadata\s*\n(.*?)\n```", re.DOTALL)


def iter_records(path, prefilter=None):
    """Yield parsed JSON dict records from a JSONL transcript, binary-safe.

    Streamed in binary so one invalid-UTF-8 byte poisons only its own line,
    never the whole walk. prefilter: optional non-empty sequence of byte-substrings; a line
    containing none is skipped before json.loads (speed). None or empty = parse
    every line. Only dict records are yielded -- a bare JSON scalar is
    off-contract, so skipping it lets every caller .get() safely.
    """
    try:
        f = open(path, "rb")
    except FileNotFoundError:
        return
    with f:
        for line in f:
            if prefilter and not any(p in line for p in prefilter):
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if isinstance(rec, dict):
                yield rec


def reconstruct(transcript_path):
    """Return (tasks, inprogress).

    tasks:      { real_id: {"subject","description","status","blockedBy":[ids]} }
    inprogress: [real_id, ...]  most-recent LAST
    """
    creates = []   # ordered: {"tuid","subject","description"}
    results = {}   # tuid -> (is_error, realid or None)
    updates = []   # ordered: {"tid","status","description","add_bb","set_bb"}

    # Pre-filter substrings MUST stay in sync with CREATE_RE: a drift would
    # silently fall back to positional ids and reintroduce the id desync.
    PREFILTER = (b"TaskCreate", b"TaskUpdate", b"created successfully")
    for e in iter_records(transcript_path, PREFILTER):
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            ctype = c.get("type")
            if ctype == "tool_use":
                name = c.get("name", "")
                inp = c.get("input") or {}
                if name == "TaskCreate":
                    creates.append({
                        "tuid": c.get("id", "") or "",
                        "subject": inp.get("subject", "") or "",
                        "description": inp.get("description", "") or "",
                    })
                elif name == "TaskUpdate":
                    updates.append({
                        "tid": str(inp.get("taskId", "")),
                        "status": inp.get("status"),
                        "description": inp.get("description") or "",
                        "add_bb": inp.get("addBlockedBy") or [],
                        "set_bb": inp.get("blockedBy"),
                    })
            elif ctype == "tool_result":
                tuid = c.get("tool_use_id", "")
                if not tuid:
                    continue
                rc = c.get("content")
                if isinstance(rc, list):
                    txt = " ".join(x.get("text", "") for x in rc if isinstance(x, dict))
                else:
                    txt = str(rc or "")
                m = CREATE_RE.search(txt)
                results[tuid] = (bool(c.get("is_error")), m.group(1) if m else None)

    # Real ids come from TaskCreate tool_results. Positional fallback applies
    # ONLY to transcripts with no TaskCreate results at all (older / synthetic
    # records). When results exist, a create lacking a successful result is
    # pending or blocked and is skipped -- never positionally numbered, which
    # could collide with a real id and silently overwrite a task.
    tasks = {}
    if not results:
        for i, cr in enumerate(creates):
            tasks[str(i + 1)] = {"subject": cr["subject"], "description": cr["description"],
                                 "status": "pending", "blockedBy": []}
    else:
        for cr in creates:
            res = results.get(cr["tuid"]) if cr["tuid"] else None
            if not res:
                continue
            is_err, realid = res
            if is_err or realid is None:
                continue
            tasks[str(realid)] = {"subject": cr["subject"], "description": cr["description"],
                                  "status": "pending", "blockedBy": []}

    inprogress = []
    for up in updates:
        tid = up["tid"]
        if not tid:
            continue
        if tid not in tasks:
            tasks[tid] = {"subject": "", "description": "", "status": "pending", "blockedBy": []}
        if up["description"]:
            tasks[tid]["description"] = up["description"]
        for b in up["add_bb"]:
            b = str(b)
            if b not in tasks[tid]["blockedBy"]:
                tasks[tid]["blockedBy"].append(b)
        if isinstance(up["set_bb"], list):
            tasks[tid]["blockedBy"] = [str(b) for b in up["set_bb"]]
        status = up["status"]
        if status:
            tasks[tid]["status"] = status
        if status == "in_progress":
            if tid in inprogress:
                inprogress.remove(tid)
            inprogress.append(tid)
        elif status in ("completed", "cancelled", "deleted"):
            if tid in inprogress:
                inprogress.remove(tid)

    return tasks, inprogress


def fence_meta(description):
    """Parse the json:metadata fence from a description; {} if absent/invalid."""
    m = FENCE_RE.search(description or "")
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: task_model.py <transcript>")
    t, ip = reconstruct(sys.argv[1])
    print(json.dumps({"tasks": t, "inprogress": ip}))
