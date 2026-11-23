"""CLI Claude Code uses to read and update the queue.

  python scripts/task.py list [status]          # JSON of tasks (optionally filtered)
  python scripts/task.py show <id>
  python scripts/task.py set <id> key=value ... [--msg "history note"]
        keys: status company role portal contact_email reason question
        output.<name>=<path relative to data/>   e.g. output.resume=outputs/ab12cd34/resume.pdf
  python scripts/task.py settings               # account email/password for sign-ups
  python scripts/task.py synced                 # mark master resume as re-synced with uploaded PDF
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jobbot import store  # noqa: E402


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd, args = argv[0], argv[1:]
    if cmd == "list":
        print(json.dumps(store.list_tasks(args[0] if args else None), indent=2, ensure_ascii=False))
    elif cmd == "show":
        print(json.dumps(store.get_task(args[0]), indent=2, ensure_ascii=False))
    elif cmd == "set":
        task_id, rest = args[0], args[1:]
        msg = None
        if "--msg" in rest:
            i = rest.index("--msg")
            msg = rest[i + 1]
            rest = rest[:i] + rest[i + 2:]
        fields, outputs = {}, {}
        for kv in rest:
            k, _, v = kv.partition("=")
            if k.startswith("output."):
                outputs[k[7:]] = v.replace("\\", "/")
            else:
                fields[k] = v
        if outputs:
            fields["outputs"] = outputs
        print(json.dumps(store.update_task(task_id, history_msg=msg, **fields), indent=2, ensure_ascii=False))
    elif cmd == "settings":
        s = store.get_settings()
        print(json.dumps({k: s[k] for k in ("account_email", "account_password", "resume_needs_sync")}, indent=2))
    elif cmd == "synced":
        store.update_settings(resume_needs_sync=False)
        print("master resume marked as synced")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
