import re
import subprocess
import sys

path = ".file-size-baseline.json"
with open(path, encoding="utf-8") as f:
    content = f.read()

pattern = re.compile(r"<<<<<<< HEAD\n(.*?)\n=======\n(.*?)\n>>>>>>> [^\n]*\n", re.DOTALL)


def wc(fname: str) -> int:
    try:
        with open(fname, encoding="utf-8") as fh:
            return sum(1 for _ in fh)
    except FileNotFoundError:
        return -1


def resolve(m: re.Match) -> str:
    ours, theirs = m.group(1), m.group(2)
    out_lines = []
    ours_entries = dict(re.findall(r'"([^"]+)":\s*(\d+)', ours))
    theirs_entries = dict(re.findall(r'"([^"]+)":\s*(\d+)', theirs))
    keys = list(ours_entries.keys()) if len(ours_entries) >= len(theirs_entries) else list(theirs_entries.keys())
    # preserve order: use whichever side has more keys as the base ordering
    base_side = ours if len(ours_entries) >= len(theirs_entries) else theirs
    for line in base_side.split("\n"):
        km = re.match(r'\s*"([^"]+)":\s*(\d+),?', line)
        if not km:
            out_lines.append(line)
            continue
        key, _ = km.group(1), km.group(2)
        actual = wc(key)
        ours_v = ours_entries.get(key)
        theirs_v = theirs_entries.get(key)
        if actual >= 0 and ours_v is not None and int(ours_v) == actual:
            val = ours_v
        elif actual >= 0 and theirs_v is not None and int(theirs_v) == actual:
            val = theirs_v
        else:
            candidates = [v for v in (ours_v, theirs_v) if v is not None]
            val = str(max(int(v) for v in candidates)) if candidates else "0"
        out_lines.append(f'  "{key}": {val},')
    return "\n".join(out_lines) + "\n"


new_content, n = pattern.subn(resolve, content)
with open(path, "w", encoding="utf-8", newline="\n") as f:
    f.write(new_content)
print(f"resolved {n} conflict blocks")
