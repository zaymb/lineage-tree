#!/usr/bin/env python3
"""lineage_tree.py: draw a cohort-column tree from a Markdown outline.

    python3 lineage_tree.py lineage_names.md            -> lineage_names.svg
    python3 lineage_tree.py lineage_names.md -o out.svg
    python3 lineage_tree.py lineage_names.md --order auto   # reorder lineages into a spectrum
    python3 lineage_tree.py lineage_names.md --order semantic   # also= links, then meaning (Ollama)
    python3 lineage_tree.py lineage_names.md --order axis --axis axes/ddc.txt   # by class= tags

Reading the drawing
    Across a dashed line is time: a label sits in the cohort where it first appears.
    Inside a cohort, left to right is hierarchy (lineage > name > concept).
    A branch that crosses a dashed line is something that picked up a new part later.
    Top to bottom is the order of the lineages in the outline (a spectrum of kinship).
    Red labels lasted to the end. A dashed link marks a name that also belongs to
    a neighbouring lineage.

Layout rules
    1. Every leaf gets its own row; a parent sits on the row of its first child.
       Total height is therefore the number of leaves, fully laid out.
    2. One font, one size.
    3. One padding value (STYLE["pad"]) between any text and any line end.
    4. No boxes around text.
    Each level inside a cohort is as wide as its longest label, so a deep
    branch never spills over the dashed line into the next cohort.

Outline format (see the top of lineage_names.md)
    @cohort NAME                      one line per cohort, in order
    # lineage
    ## name | cohort | flags          a name; may have concepts under it or stand alone
    - concept | cohort | flags
    > note                            ignored
    flags:  keep                      lasted to the end
            also=Other lineage        also belongs to that lineage (dashed link)
            class=720                 position on an ordering axis (--order axis --axis FILE)
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path
from xml.sax.saxutils import escape

STYLE = dict(
    # type (rule 2). Label widths are measured from font_file (needs Pillow: pip install pillow).
    font_family="'Helvetica Neue', Helvetica, Arial, sans-serif",
    font_file=None,        # path to the font to measure with, absolute or relative to this script; None = estimate
    font_size=10,          # px
    char_advance=0.5,      # only used when font_file is missing: average glyph width / font size
                           # (about 0.6 for a monospace face, 0.45-0.5 for a narrow sans)
    # spacing
    row_pitch=16,          # px between rows
    pad=6,                 # px between text and a line end (rule 3)
    level_gap=30,          # px between two levels inside a cohort; the vertical line runs in its middle
    cohort_gap=60,         # px between two cohorts; the dashed line runs in its middle
    root_gap_rows=1,       # empty rows between two lineages
    header_rows=2,         # rows reserved above the first row for the cohort names
    margin=40,             # px around the drawing
    # ink
    stroke=0.8,
    ink="#111111",
    keep_ink="#d4161c",    # labels flagged `keep`
    paper="#ffffff",       # set to None for a transparent background
    dash="1 5",            # dash pattern of the cohort lines
    also_dash="3 3",       # dash pattern of an `also=` guide line
    also_offset=5,         # px between the vertical line and the guide line beside it
    # behaviour
    sort_by_cohort=True,   # order names and concepts by cohort inside their parent (file order breaks ties)
    show_also=False,       # draw `also=` guide lines and move those names to the touching edge
    lineages_at_left=True, # lineage labels always sit at the far left, whenever their first name appears
)


# ---------------------------------------------------------------- data

class Node:
    def __init__(self, label, cohort=None, keep=False, also=None):
        self.cls = None           # class= value: a key on the ordering axis (see --axis)
        self.label = label
        self.cohort = cohort      # index into cohorts; None on a heading = earliest child
        self.keep = keep
        self.also = also          # label of another lineage
        self.children = []
        self.level = None         # depth inside its cohort (resets at each dashed line)
        self.row = None

    @property
    def is_leaf(self):
        return not self.children


def parse_outline(path):
    """Return (cohorts, roots, anchors). cohorts = [name], roots = [Node], anchors = {top, bottom}."""
    cohorts, roots, stack, anchors = [], [], [], {}

    def make(text):
        fields = [f.strip() for f in text.split("|")]
        node = Node(fields[0])
        if not node.label:
            raise ValueError("empty label")
        for f in fields[1:]:
            if f == "keep":
                node.keep = True
            elif f.startswith("also="):
                node.also = f[5:].strip()
            elif f.startswith("class="):
                node.cls = f[6:].strip()
            elif f in cohorts:
                node.cohort = cohorts.index(f)
            elif f:
                raise ValueError(f"'{f}' is not a cohort ({', '.join(cohorts)}) or a flag (keep, also=...)")
        return node

    for n, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(">"):
            continue
        try:
            if line.startswith("@cohort"):
                cohorts.append(line[len("@cohort"):].strip())
            elif line.startswith(("@top", "@bottom")):
                key, _, text = line[1:].partition(" ")
                anchors[key] = text.strip()
            elif line.startswith("#"):
                hashes, text = re.fullmatch(r"(#+)\s*(.+)", line).groups()
                depth = len(hashes) - 1
                if depth > len(stack):
                    raise ValueError("heading skips a level")
                node = make(text)
                del stack[depth:]
                (stack[-1].children if stack else roots).append(node)
                stack.append(node)
            elif line.startswith("- "):
                if not stack:
                    raise ValueError("bullet appears before any heading")
                stack[-1].children.append(make(line[2:]))
            else:
                raise ValueError("line is not a heading, a bullet, a @cohort, @top, @bottom or a > note")
        except ValueError as e:
            sys.exit(f"{path}:{n}: {e}\n    {raw}")
    if not cohorts:
        sys.exit(f"{path}: no @cohort lines")
    return cohorts, roots, anchors


# ---------------------------------------------------------------- lineage order

def load_axis(path):
    """An ordering axis: a text file, one class per line, in order; # starts a comment.

    A line may start with a number ("720 Architecture"); then numeric class= codes are placed
    by value between the numbered lines, so subdivisions keep their order.
    """
    keys = [l.split("#", 1)[0].strip() for l in Path(path).read_text(encoding="utf-8").splitlines()]
    keys = [k for k in keys if k]
    if not keys:
        sys.exit(f"{path}: empty axis")
    return keys


def axis_position(cls, keys, where):
    """Position of a class= value on the axis: a label, a leading code, or a number between codes."""
    low = cls.lower()
    for i, k in enumerate(keys):
        if low == k.lower() or low == k.split(" ", 1)[0].lower() or low == k.split(" ", 1)[-1].lower():
            return float(i)
    nums = [(float(k.split(" ", 1)[0]), i) for i, k in enumerate(keys)
            if re.match(r"\d+(\.\d+)?$", k.split(" ", 1)[0])]
    if nums and re.match(r"\d+(\.\d+)?$", cls):
        v = float(cls)
        below = [(n, i) for n, i in nums if n <= v]
        if below:
            n, i = max(below)
            nxt = [m for m, _ in nums if m > n]
            return i + ((v - n) / (min(nxt) - n) if nxt else 0)
    sys.exit(f"'{where}': class={cls} is not on the axis ({', '.join(keys)})")


def axis_order(roots, keys):
    """Order lineages by where their names sit on the axis.

    A lineage's position is the median of the class= positions found on it and everything under
    it (a class on the lineage heading counts like any other). Lineages with no class keep their
    place relative to the file order, after the classified ones. Ties break by file order.
    """
    keyed = []
    for i, root in enumerate(roots):
        pos = sorted(axis_position(n.cls, keys, n.label) for n in walk([root]) if n.cls)
        mid = (pos[(len(pos) - 1) // 2] + pos[len(pos) // 2]) / 2 if pos else None
        keyed.append((mid is None, mid if mid is not None else 0, i, root))
    keyed.sort(key=lambda k: k[:3])
    return [k[3] for k in keyed], [(k[3].label, k[1] if not k[0] else None) for k in keyed]


def links_between(roots):
    """Count `also=` links between every pair of lineages: {(i, j): n} with i < j."""
    order = {r.label: i for i, r in enumerate(roots)}
    links = {}
    for i, root in enumerate(roots):
        for n in walk(root.children):
            if n.also:
                if n.also not in order:
                    sys.exit(f"'{n.label}': also={n.also} is not a lineage")
                j = order[n.also]
                if j != i:
                    key = (min(i, j), max(i, j))
                    links[key] = links.get(key, 0) + 1
    return links


def spectrum_order(roots, sim=None, toward=None):
    """Order lineages so that neighbours share as many `also=` links as possible.

    Score of an order = links between adjacent lineages. With `sim` (a similarity matrix, see
    semantic_similarity), equally linked orders are then ranked by the similarity of adjacent
    lineages, so linked lineages stay together and the rest are placed by meaning. Among orders
    that are still equal, the one closest to the file order wins (fewest swapped pairs), so
    lineages with nothing to go on stay put.
    Exhaustive up to 9 lineages; above that, a greedy chain from the best-linked pair.

    Links and similarity have no direction. With `toward` (each lineage's similarity to the
    @top anchor minus its similarity to the @bottom anchor), the end closer to @top goes on top;
    otherwise the end holding the file's first lineage does. Returns the order, its link score,
    the file order's link score, its similarity score, and the runners-up as (order, gap).
    """
    n = len(roots)
    links = links_between(roots)
    s = sim or [[0.0] * n for _ in range(n)]
    w = lambda a, b: (links.get((min(a, b), max(a, b)), 0), s[a][b])
    score = lambda p: sum(w(a, b)[0] for a, b in zip(p, p[1:]))
    near = lambda p: sum(s[a][b] for a, b in zip(p, p[1:]))
    swaps = lambda p: sum(1 for x in range(n) for y in range(x + 1, n) if p[x] > p[y])
    if n <= 9:
        from itertools import permutations
        ranked = sorted(permutations(range(n)), key=lambda p: (score(p), near(p), -swaps(p)),
                        reverse=True)
        best, seen, runners = ranked[0], {min(ranked[0], ranked[0][::-1])}, []
        for p in ranked[1:]:
            if len(runners) == 2 or sim is None:
                break
            if min(p, p[::-1]) not in seen:
                seen.add(min(p, p[::-1]))
                runners.append(p)
    else:
        runners = []
        left = set(range(n))
        a, b = max(((a, b) for a in left for b in left if a < b), key=lambda e: (w(*e), -e[0]))
        best, left = [a, b], left - {a, b}
        while left:
            head = max(left, key=lambda c: (w(c, best[0]), -c))
            tail = max(left, key=lambda c: (w(c, best[-1]), -c))
            if w(head, best[0]) > w(tail, best[-1]):
                best.insert(0, head); left.remove(head)
            else:
                best.append(tail); left.remove(tail)
    def orient(p):
        p = list(p)
        if toward is not None:
            if toward[p[0]] < toward[p[-1]]:
                p.reverse()
        elif sim is not None:
            if p.index(0) > n - 1 - p.index(0):
                p.reverse()
        elif p == sorted(p, reverse=True):
            p.reverse()                              # same spectrum, keep the file's direction
        return p

    best = orient(best)
    runners = [([roots[i] for i in orient(p)], near(best) - near(p)) for p in runners]
    return [roots[i] for i in best], score(best), score(list(range(n))), near(best), runners


def semantic_similarity(roots, model, url, anchors=None):
    """Cosine similarity between lineages, from a local Ollama embedding model.

    Each lineage is embedded as its label followed by every name and concept under it. Returns
    the matrix, and with @top/@bottom anchors also each lineage's pull toward the top (else None).
    """
    import json
    import math
    import urllib.request
    texts = [r.label + ": " + ", ".join(n.label for n in walk(r.children)) for r in roots]
    ends = [k for k in ("top", "bottom") if (anchors or {}).get(k)]
    texts += [anchors[k] for k in ends]
    req = urllib.request.Request(url.rstrip("/") + "/api/embed",
                                 json.dumps({"model": model, "input": texts}).encode(),
                                 {"Content-Type": "application/json"})
    try:
        vecs = json.load(urllib.request.urlopen(req, timeout=300))["embeddings"]
    except Exception as e:
        sys.exit(f"--order semantic needs an Ollama server with {model} at {url} ({e})")
    norm = [math.sqrt(sum(x * x for x in v)) for v in vecs]
    sim = [[sum(x * y for x, y in zip(a, b)) / (na * nb) for b, nb in zip(vecs, norm)]
           for a, na in zip(vecs, norm)]
    n = len(roots)
    if not ends:
        return [row[:n] for row in sim[:n]], None
    sign = {"top": 1, "bottom": -1}
    toward = [sum(sign[k] * sim[i][n + e] for e, k in enumerate(ends)) for i in range(n)]
    return [row[:n] for row in sim[:n]], toward


# ---------------------------------------------------------------- layout

_FONT = None


def measuring_font(st):
    """The font used to measure labels, or False when it cannot be loaded."""
    global _FONT
    if _FONT is None:
        _FONT = False
        if st["font_file"]:
            path = Path(st["font_file"])
            if not path.is_absolute():
                path = Path(__file__).resolve().parent / path
            try:
                from PIL import ImageFont
                _FONT = ImageFont.truetype(str(path), 1000)
            except Exception as e:
                print(f"warning: cannot measure labels with {path} ({e}); "
                      f"estimating widths from char_advance instead", file=sys.stderr)
    return _FONT


def text_width(s, st):
    """Width in px of a label: measured from the font file, else estimated per character."""
    font = measuring_font(st)
    if font:
        return font.getlength(s) / 1000 * st["font_size"]
    em = sum(1.0 if unicodedata.east_asian_width(ch) in "WF" else st["char_advance"] for ch in s)
    return em * st["font_size"]


def assign(roots, cohorts, st):
    """Fill in cohort / level / row on every node. Returns the number of rows used."""

    def settle(node, is_root):              # cohorts, bottom up
        for c in node.children:
            settle(c, False)
        if node.is_leaf:
            if node.cohort is None:
                sys.exit(f"'{node.label}' has no cohort and nothing under it")
            return
        if st["sort_by_cohort"]:
            node.children.sort(key=lambda c: c.cohort)    # stable: file order breaks ties
        first = min(c.cohort for c in node.children)
        if node.cohort is None:
            node.cohort = first
        elif first < node.cohort and not is_root:
            early = next(c for c in node.children if c.cohort == first)
            sys.exit(f"'{early.label}' ({cohorts[first]}) is earlier than its parent "
                     f"'{node.label}' ({cohorts[node.cohort]})")

    next_row = 0

    def place(node, parent):                # levels and rows, top down
        nonlocal next_row
        if parent is None:
            node.level = 0
        else:
            node.level = parent.level + 1 if node.cohort == parent.cohort else 0
        if node.is_leaf:
            node.row = next_row
            next_row += 1
        else:
            for c in node.children:
                place(c, node)
            node.row = node.children[0].row

    order = {r.label: i for i, r in enumerate(roots)}
    for i, root in enumerate(roots):
        settle(root, True)
        if st["show_also"]:
            # a name that also belongs to another lineage sits on the edge that touches it
            up = [c for c in root.children if order.get(c.also, i) < i]
            down = [c for c in root.children if order.get(c.also, i) > i]
            root.children = up + [c for c in root.children if c not in up and c not in down] + down
        if st["lineages_at_left"]:
            root.cohort = 0
        if i:
            next_row += st["root_gap_rows"]
        place(root, None)
    return next_row


def walk(nodes):
    for n in nodes:
        yield n
        yield from walk(n.children)


def column_geometry(roots, cohorts, st):
    """x of every (cohort, level), plus the x of each dashed line and the total width."""
    widths = {}                                           # (cohort, level) -> widest label
    for n in walk(roots):
        key = (n.cohort, n.level)
        widths[key] = max(widths.get(key, 0), text_width(n.label, st))
    for i, name in enumerate(cohorts):                    # a cohort name must fit its column too
        widths[(i, 0)] = max(widths.get((i, 0), 0), text_width(name, st))

    x, right, dividers = {}, {}, []
    cursor = st["margin"]
    for c in range(len(cohorts)):
        levels = sorted(l for (cc, l) in widths if cc == c)
        for l in levels:
            x[(c, l)] = cursor
            right[(c, l)] = cursor + widths[(c, l)]
            cursor = right[(c, l)] + st["level_gap"]
        cursor -= st["level_gap"]
        if c < len(cohorts) - 1:
            dividers.append(cursor + st["cohort_gap"] / 2)
            cursor += st["cohort_gap"]
    return x, right, dividers, cursor + st["margin"]


# ---------------------------------------------------------------- drawing

def render(roots, cohorts, st):
    rows = assign(roots, cohorts, st)
    x, right, dividers, width = column_geometry(roots, cohorts, st)

    top = st["margin"] + st["header_rows"] * st["row_pitch"]
    height = top + rows * st["row_pitch"] + st["margin"]
    baseline = st["font_size"] * 0.35                     # centre a line of text on its row

    def y(row):
        return top + (row + 0.5) * st["row_pitch"]

    f = lambda v: f"{v:.2f}".rstrip("0").rstrip(".")
    bus = lambda n: right[(n.cohort, n.level)] + st["level_gap"] / 2
    end = lambda n: x[(n.cohort, n.level)] - st["pad"]
    texts, paths, links = [], [], []

    def label(px, py, s, keep=False):
        fill = f' fill="{st["keep_ink"]}"' if keep else ""
        texts.append(f'<text x="{f(px)}" y="{f(py + baseline)}"{fill}>{escape(s)}</text>')

    # cohort names and dashed lines
    for i, name in enumerate(cohorts):
        label(x[(i, 0)], st["margin"] + st["row_pitch"] / 2, name)
    rules = [f'<path d="M{f(dx)} {f(st["margin"])}V{f(height - st["margin"])}"/>' for dx in dividers]

    # guide lines for names that also belong to a neighbouring lineage: a dashed line beside the
    # vertical line, from the neighbour's nearest row to the farthest such name, touching each one
    order = {r.label: i for i, r in enumerate(roots)}
    for i, root in enumerate(roots):
        groups = {}
        for c in root.children:
            if c.also and st["show_also"]:
                if c.also not in order:
                    sys.exit(f"'{c.label}': also={c.also} is not a lineage")
                groups.setdefault(c.also, []).append(c)
        for name, members in groups.items():
            j, other = order[name], roots[order[name]]
            if abs(i - j) != 1:
                print(f"warning: '{root.label}' and '{name}' are not neighbours; guide line for "
                      f"{', '.join(c.label for c in members)} not drawn", file=sys.stderr)
                continue
            gx = bus(root) + st["also_offset"]
            if j < i:
                y0, y1 = y(other.children[-1].row), y(max(c.row for c in members))
            else:
                y0, y1 = y(other.row), y(min(c.row for c in members))
            links.append(f'<path d="M{f(gx)} {f(y0)}V{f(y1)}"/>')

    # labels and connectors
    for n in walk(roots):
        nx = x[(n.cohort, n.level)]
        label(nx, y(n.row), n.label, n.keep)
        if n.is_leaf:
            continue
        first, rest = n.children[0], n.children[1:]
        d = f"M{f(nx + text_width(n.label, st) + st['pad'])} {f(y(n.row))}H{f(end(first))}"
        for c in rest[:-1]:
            d += f"M{f(bus(n))} {f(y(c.row))}H{f(end(c))}"
        if rest:
            last = rest[-1]
            d += f"M{f(bus(n))} {f(y(n.row))}V{f(y(last.row))}H{f(end(last))}"
        paths.append(f'<path d="{d}"/>')

    paper = f'<rect width="100%" height="100%" fill="{st["paper"]}"/>\n' if st["paper"] else ""
    nl = chr(10)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{f(width)}" height="{f(height)}" viewBox="0 0 {f(width)} {f(height)}">
{paper}<g fill="none" stroke="{st['ink']}" stroke-width="{st['stroke']}" stroke-dasharray="{st['dash']}" stroke-linecap="round">
{nl.join(rules)}
</g>
<g fill="none" stroke="{st['ink']}" stroke-width="{st['stroke']}" stroke-dasharray="{st['also_dash']}">
{nl.join(links)}
</g>
<g fill="none" stroke="{st['ink']}" stroke-width="{st['stroke']}" stroke-linejoin="miter">
{nl.join(paths)}
</g>
<g fill="{st['ink']}" font-family="{st['font_family']}" font-size="{st['font_size']}">
{nl.join(texts)}
</g>
</svg>
"""
    return svg, width, height


def main():
    ap = argparse.ArgumentParser(description="Draw a cohort-column tree from a Markdown outline.")
    ap.add_argument("outline")
    ap.add_argument("-o", "--output")
    ap.add_argument("--order", choices=["file", "auto", "semantic", "axis"], default="file",
                    help="lineage order top to bottom: as written (default); auto = by shared "
                         "also= names; semantic = also= links first, then similarity of meaning; "
                         "axis = by the class= tags on the --axis file")
    ap.add_argument("--axis", help="ordering axis for --order axis: a text file, one class per line")
    ap.add_argument("--model", default="qwen3-embedding:4b",
                    help="Ollama embedding model for --order semantic")
    ap.add_argument("--ollama", default="http://localhost:11434", help="Ollama server URL")
    args = ap.parse_args()

    cohorts, roots, anchors = parse_outline(args.outline)
    if args.order in ("auto", "semantic"):
        sim, toward = (semantic_similarity(roots, args.model, args.ollama, anchors)
                       if args.order == "semantic" else (None, None))
        roots, got, had, near, runners = spectrum_order(roots, sim, toward)
        extra = f"; similarity of neighbours {near:.3f} ({args.model})" if sim else ""
        print(f"order (also= links between neighbours: {had} -> {got}{extra}):")
        for r in roots:
            print(f"    # {r.label}")
        if sim:
            ends = " / ".join(f"@{k} {anchors[k]}" for k in ("top", "bottom") if anchors.get(k))
            print(f"direction: {ends or 'first lineage in the file stays on top'}")
        for k, (alt, gap) in enumerate(runners, 2):
            print(f"runner-up {k} (similarity {gap:.3f} lower): " + " > ".join(r.label for r in alt))
    elif args.order == "axis":
        if not args.axis:
            ap.error("--order axis needs --axis FILE (see axes/ for examples)")
        roots, report = axis_order(roots, load_axis(args.axis))
        print(f"order on {args.axis} (median class position):")
        for label, pos in report:
            print(f"    {'unclassified' if pos is None else f'{pos:6.2f}'}  # {label}")
    svg, width, height = render(roots, cohorts, STYLE)
    out = Path(args.output) if args.output else Path(args.outline).with_suffix(".svg")
    out.write_text(svg, encoding="utf-8")

    nodes = [n for r in roots for n in walk(r.children)]
    per = ", ".join(f"{name}: {sum(n.cohort == i for n in nodes)}" for i, name in enumerate(cohorts))
    print(f"{out}  {width:.0f} x {height:.0f} px  |  {len(roots)} lineages, {len(nodes)} nodes, "
          f"{sum(n.keep for n in nodes)} kept  ({per})")


if __name__ == "__main__":
    main()
