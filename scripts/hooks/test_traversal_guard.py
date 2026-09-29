#!/usr/bin/env python3
"""
Tests for traversal_guard.py (ADR-045 §8.3, Entry #042).

Run:  python3 scripts/hooks/test_traversal_guard.py
Pure function tests -- nothing is executed, no filesystem is traversed.
Exits non-zero on the first failure.

The first block is the three recorded DATA_BOUNDARIES §2 breaches, verbatim.
Test the shape that actually happened, not the shape imagined.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import traversal_guard as t

OC = t.ROOT
HOME = t.HOME


def decide(cmd, cwd=OC):
    return t.decide({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd})


def check(name, cmd, should_ask, cwd=OC):
    reason = decide(cmd, cwd)
    if bool(reason) != should_ask:
        raise SystemExit(f"FAIL {name}\n  cmd:  {cmd!r}\n  cwd:  {cwd}\n"
                         f"  got:  {'ASK: ' + reason if reason else 'allow'}\n"
                         f"  want: {'ask' if should_ask else 'allow'}")
    print(f"ok   {name}{'  -> ' + reason if reason else ''}")


# ---- the three recorded breaches (must ASK) ----
check("Entry #029: glob in iCloud root (plain ls -d)",
      "ls -d ~/Library/Mobile\\ Documents/com~apple~CloudDocs/*ackup*", True)
check("Entry #029: same, quoted path",
      'ls -d "$HOME/Library/Mobile Documents/com~apple~CloudDocs/"*ackup*', True)
check("Entry #030: cd home then du glob", "cd ~ && du -sh */", True)
check("Entry #030: dotfile glob in home", "cd ~ && du -sh .[a-zA-Z]*/", True)
check("Entry #030: system-wide du",
      "du -sh /Applications /Library /private/var /Users/*", True)
check("du run with home as cwd", "du -sh */", True, cwd=HOME)

# ---- other outside-traversal shapes (must ASK) ----
check("ls of a §2 path", "ls ~/Documents", True)
check("ls with no path, cwd = home", "ls -la", True, cwd=HOME)
check("find from home", "find ~ -name '*.pdf'", True)
check("find absolute outside", "find /Users/sheldonwheeler/Desktop -type f", True)
check("grep -r outside", "grep -rn password ~/Library", True)
check("grep -R combined flags", "grep -inR token /etc", True)
check("rg defaults to recursive over cwd", "rg secret", True, cwd=HOME)
check("tree outside", "tree ~/Desktop", True)
check("mdfind without -onlyin", "mdfind 'kind:pdf'", True)
check("mdfind -onlyin outside", "mdfind -onlyin ~/Documents tax", True)
check("locate always asks", "locate backup.sql", True)
check("escape via ..", "du -sh ../", True)
check("escape via ../ glob", "ls ../*", True)
check("sudo prefix does not hide du", "sudo du -sh /Users", True)
check("xargs prefix does not hide grep -r", "echo x | xargs grep -rl foo /private", True)
check("bash -c is inspected", "bash -c 'cd ~ && du -sh */'", True)
check("eval with a verb asks", "eval du -sh $DIR", True)
check("unknown variable path", "du -sh $TARGET", True)
check("command substitution path", "ls $(dirname ~/openclaw)", True)
check("cd - loses track, then relative du", "cd - && du -sh .", True)
check("cd outside then back is followed",
      "cd /tmp && ls && cd ~/openclaw", True)
check("glob in a non-traversal command", "cat ~/Documents/*.txt", True)
check("pushd outside", "pushd ~/Desktop && ls", True)

# ---- normal project work (must ALLOW) ----
check("du on the project", "du -sh ~/openclaw", False)
check("du absolute project path", f"du -sh {OC}/backups", False)
check("ls in project", "ls -la", False)
check("ls project subdir glob", "ls scripts/*.sh", False)
check("find in project", "find . -name '*.py' -newer changelog.md", False)
check("grep -rn in project", "grep -rn verify_counts app/", False)
check("grep -r with -e pattern", "grep -r -e 'TODO' .", False)
check("non-recursive grep of an outside path is not traversal",
      "grep -c openclaw /etc/hosts", False)
check("rg in project", "rg HARD_FAIL", False)
check("tree project dir", "tree -L 2 app", False)
check("mdfind -onlyin project", "mdfind -onlyin ~/openclaw ADR", False)
check("cd into project then du", "cd ~/openclaw && du -sh *", False, cwd=HOME)
check("git commands untouched", "git status -sb && git log -1 --oneline", False)
check("docker exec query untouched",
      "docker exec openclaw_postgres psql -U openclaw -d openclaw -c "
      "\"SELECT count(*) FROM scraped_content WHERE project = 'x';\"", False)
check("regex pattern with glob chars", "grep -n 'v[0-9]*' changelog.md", False)
check("grep pattern containing $HOME text",
      "grep -nE '^[^#]*\\(\\$HOME/Documents|Mobile Documents\\)' scripts/backup.sh", False)
check("commit message with an asterisk", "git commit -m 'fix * handling'", False)
check("python run", "python3 generate_brief_review.py", False)
check("find path is last arg of pipeline", "git ls-files | grep '\\.py$'", False)
check("non-Bash tool is ignored", "", False)

# ---- robustness ----
check("unparseable command with a verb asks", "du -sh 'unterminated", True)
check("unparseable command without a verb allows", "echo 'unterminated", False)
if t.decide({"tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}}) is not None:
    raise SystemExit("FAIL non-Bash tool should be ignored")
print("ok   non-Bash tool payload ignored")

print("\nall traversal-guard tests passed")
