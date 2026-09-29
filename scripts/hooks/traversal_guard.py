#!/usr/bin/env python3
"""
traversal_guard.py — ADR-045 §8.3 traversal-verb hook (Claude Code PreToolUse, Bash).

Purpose
-------
DATA_BOUNDARIES.md §2.2: listing and traversing a prohibited path is itself a
breach — a glob is a directory read, a `du` is a directory read. This hook
inspects each Bash command before it runs. If the command uses a traversal
verb (du, find, tree, ls -R, grep -r, rg, mdfind, locate) and the guard
cannot show that every path it reaches is inside ~/openclaw, it returns
permissionDecision "ask", so the operator is prompted instead of the command
running silently.

What it is NOT
--------------
A speed bump, not a boundary (ADR-045). Shell is unbounded by construction:
a Python one-liner that walks directories, `cat` with a glob, or deliberate
obfuscation will pass. It exists to catch the accidental, habitual
`cd ~ && du -sh */` shape that produced the three recorded §2 breaches.

Protocol
--------
Reads the PreToolUse JSON on stdin (tool_name, tool_input.command, cwd).
Allowed: exit 0, no output. Flagged: exit 0 with a hookSpecificOutput JSON
carrying permissionDecision "ask" and a reason. Any internal error on a
command that mentions a traversal verb also yields "ask" (fail toward the
prompt, never toward silence).
"""

import json
import os
import re
import shlex
import sys

HOME = os.path.expanduser("~")
ROOT = os.path.realpath(os.path.join(HOME, "openclaw"))

# ls is included because listing is a read (§2.2) even without -R.
TRAVERSAL = {"du", "find", "tree", "ls", "grep", "egrep", "fgrep", "rgrep", "rg", "mdfind", "locate", "glocate"}
PREFIXES = {"sudo", "env", "time", "nice", "nohup", "command", "exec", "xargs", "builtin"}
SHELLS = {"bash", "sh", "zsh"}
SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")", ";;", "|&", "\n"}
VERB_RE = re.compile(r"(?<![\w./-])(" + "|".join(sorted(TRAVERSAL, key=len, reverse=True)) + r")(?![\w-])")
GLOB_CHARS = set("*?[")


class Flag(Exception):
    """Raised to request an 'ask' decision with a reason."""


def inside_root(path):
    real = os.path.realpath(path).casefold()  # APFS default is case-insensitive
    root = ROOT.casefold()
    return real == root or real.startswith(root + "/")


def expand(token, cwd):
    """Resolve a path token to an absolute path, or raise Flag if it can't be known."""
    if "$(" in token or "`" in token:
        raise Flag(f"command substitution in path '{token}'")
    t = token.replace("${HOME}", HOME).replace("$HOME", HOME)
    if "$" in t:
        raise Flag(f"unexpanded variable in path '{token}'")
    if t == "~" or t.startswith("~/"):
        t = HOME + t[1:]
    elif t.startswith("~"):
        raise Flag(f"other user's home in path '{token}'")
    if any(c in t for c in GLOB_CHARS):
        # The glob is resolved by reading the directory above the first wildcard.
        t = t[: min(t.index(c) for c in GLOB_CHARS if c in t)]
        t = t.rsplit("/", 1)[0] if "/" in t else "."
        t = t or "/"
    if not os.path.isabs(t):
        if cwd is None:
            raise Flag(f"relative path '{token}' after a cd the guard could not follow")
        t = os.path.join(cwd, t)
    return os.path.normpath(t)


def check_globs(words, cwd):
    """Any command: a wildcard is resolved by reading its parent directory (§2.2 — a glob is a directory read)."""
    for w in words:
        if not any(c in w for c in GLOB_CHARS):
            continue
        if "$" in w.replace("${HOME}", "").replace("$HOME", "") or "`" in w:
            continue  # regex/pattern text, not a resolvable path; traversal verbs are checked separately
        if not (w.startswith(("/", "~", "$HOME", "${HOME}", "..")) or cwd is None or not inside_root(cwd)):
            continue  # relative glob resolved inside the project
        p = expand(w, cwd)
        if not inside_root(p):
            raise Flag(f"wildcard '{w}' reads directory {p}, outside ~/openclaw")


def split_segments(command):
    lex = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    segments, cur = [], []
    for tok in lex:
        if tok in SEPARATORS or set(tok) <= set("&|;()"):
            if cur:
                segments.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        segments.append(cur)
    return segments


def strip_prefixes(words):
    while words:
        w = words[0]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):  # VAR=value prefix
            words = words[1:]
        elif os.path.basename(w) in PREFIXES:
            words = words[1:]
            while words and words[0].startswith("-"):  # e.g. xargs -0, sudo -n
                words = words[1:]
        else:
            break
    return words


def path_args(verb, args):
    """Return (is_traversal, path_tokens) for one traversal-verb invocation."""
    flags = [a for a in args if a.startswith("-")]
    if verb == "ls":  # listing a directory is a read (§2.2), recursive or not
        return True, [a for a in args if not a.startswith("-")]
    if verb in ("grep", "egrep", "fgrep", "rgrep"):
        recursive = (verb == "rgrep"
                     or "--recursive" in flags or "--dereference-recursive" in flags
                     or any(re.match(r"^-[A-Za-z]*[rR]", f) for f in flags if not f.startswith("--")))
        rest = [a for a in args if not a.startswith("-")]
        pattern_given = any(f in ("-e", "-f") or f.startswith(("--regexp", "--file")) for f in flags)
        return recursive, rest if pattern_given else rest[1:]
    if verb == "rg":
        rest = [a for a in args if not a.startswith("-")]
        pattern_given = any(f in ("-e", "-f") or f.startswith(("--regexp", "--file")) for f in flags)
        return True, rest if pattern_given else rest[1:]
    if verb == "find":
        paths = []
        for a in args:
            if a.startswith(("-", "(", "!")) or a in ("(", "!"):
                break
            paths.append(a)
        return True, paths
    if verb == "mdfind":
        if "-onlyin" in args:
            i = args.index("-onlyin")
            if i + 1 < len(args):
                return True, [args[i + 1]]
        raise Flag("mdfind searches the whole Spotlight index unless given -onlyin ~/openclaw")
    if verb in ("locate", "glocate"):
        raise Flag("locate searches the whole filesystem database")
    # du, tree
    return True, [a for a in args if not a.startswith("-")]


def check(command, cwd, depth=0):
    """Raise Flag if the command traverses anything not provably inside ROOT."""
    if depth > 3:
        raise Flag("nested shell invocations too deep to inspect")
    for seg in split_segments(command):
        words = strip_prefixes(seg)
        if not words:
            continue
        verb = os.path.basename(words[0])
        args = words[1:]
        if verb in ("cd", "pushd"):
            target = next((a for a in args if not a.startswith("-") or a == "-"), None)
            if target is None:
                cwd = HOME
            elif target == "-" or "$(" in target or "`" in target or (
                    "$" in target.replace("${HOME}", "").replace("$HOME", "")):
                cwd = None
            else:
                t = target.replace("${HOME}", HOME).replace("$HOME", HOME)
                t = HOME + t[1:] if (t == "~" or t.startswith("~/")) else t
                if os.path.isabs(t):
                    cwd = os.path.normpath(t)
                elif cwd is not None:
                    cwd = os.path.normpath(os.path.join(cwd, t))
            continue
        if verb in SHELLS and "-c" in args:
            i = args.index("-c")
            if i + 1 < len(args):
                check(args[i + 1], cwd, depth + 1)
            continue
        if verb == "eval":
            if VERB_RE.search(" ".join(args)):
                raise Flag("eval of a command containing a traversal verb")
            continue
        check_globs(words, cwd)
        if verb not in TRAVERSAL:
            continue
        traversal, paths = path_args(verb, args)
        if not traversal:
            continue
        if not paths:
            if cwd is None:
                raise Flag(f"{verb} with no path after a cd the guard could not follow")
            paths_abs = [cwd]
        else:
            paths_abs = [expand(p, cwd) for p in paths]
        for p in paths_abs:
            if not inside_root(p):
                raise Flag(f"{verb} reaches {p}, outside ~/openclaw")


def decide(payload):
    """Return None to allow, or a reason string to ask."""
    if payload.get("tool_name") != "Bash":
        return None
    command = (payload.get("tool_input") or {}).get("command") or ""
    cwd = payload.get("cwd") or os.getcwd()
    try:
        check(command, cwd)
        return None
    except Flag as e:
        return str(e)
    except Exception as e:  # unparseable: fail toward the prompt only if a verb is present
        return f"could not parse command ({e.__class__.__name__})" if VERB_RE.search(command) else None


LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "traversal_guard.log")


def log_run(payload, reason):
    """One line per invocation, so a live run is provable from disk (Entry #048).

    Records time, permission mode, the command's first word and the verdict --
    never the full command, which could carry a secret. Never raises: a log
    failure must not change the hook's decision.
    """
    try:
        import datetime
        command = (payload.get("tool_input") or {}).get("command") or ""
        first = command.split(None, 1)[0] if command.strip() else "-"
        line = "%s\tmode=%s\tverb=%s\t%s\n" % (
            datetime.datetime.now().isoformat(timespec="seconds"),
            payload.get("permission_mode", "?"),
            first[:40],
            "ask" if reason else "allow",
        )
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    reason = decide(payload)
    log_run(payload, reason)
    if reason:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason":
                    f"ADR-045 §8.3 traversal guard: {reason}. DATA_BOUNDARIES §2.2 — listing is a read. "
                    "Approve only if this is intended.",
            }
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
