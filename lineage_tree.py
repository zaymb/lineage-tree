#!/usr/bin/env python3
"""lineage_tree.py: draw a cohort-column tree from a Markdown outline.

    python3 lineage_tree.py lineage_names.md            -> lineage_names.svg
    python3 lineage_tree.py lineage_names.md -o out.svg
    python3 lineage_tree.py lineage_names.md --order auto   # reorder lineages into a spectrum

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
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path
from xml.sax.saxutils import escape

STYLE = dict(
    # type (rule 2). Label widths are measured from font_file (needs Pillow: pip install pillow).
    font_family="'D-DIN', 'DIN Alternate', 'Helvetica Neue', Arial, sans-serif",
    font_file=None,        # e.g. "D-DIN.otf"; path to the font, absolute or relative to this script; None = estimate
    font_size=10,          # px
    char_advance=0.45,     # only used when font_file is missing: average glyph width / font size
                           # (0.6 for a monospace face, about 0.45 for D-DIN)
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
    """Return (cohorts, roots). cohorts = [name], roots = [Node]."""
    cohorts, roots, stack = [], [], []

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
                raise ValueError("line is not a heading, a bullet, a @cohort or a > note")
        except ValueError as e:
            sys.exit(f"{path}:{n}: {e}\n    {raw}")
    if not cohorts:
        sys.exit(f"{path}: no @cohort lines")
    return cohorts, roots


# ---------------------------------------------------------------- lineage order

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


def spectrum_order(roots):
    """Order lineages so that neighbours share as many `also=` links as possible.

    Score of an order = links between adjacent lineages. Among equally good orders, the one
    closest to the file order wins (fewest swapped pairs), so lineages with no links stay put.
    Exhaustive up to 9 lineages; above that, a greedy chain from the best-linked pair.
    """
    n = len(roots)
    links = links_between(roots)
    w = lambda a, b: links.get((min(a, b), max(a, b)), 0)
    score = lambda p: sum(w(a, b) for a, b in zip(p, p[1:]))
    swaps = lambda p: sum(1 for x in range(n) for y in range(x + 1, n) if p[x] > p[y])
    if n <= 9:
        from itertools import permutations
        best = max(permutations(range(n)), key=lambda p: (score(p), -swaps(p)))
    else:
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
    if list(best) == sorted(best, reverse=True):
        best = list(reversed(best))                  # same spectrum, keep the file's direction
    return [roots[i] for i in best], score(best), score(list(range(n)))


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
    ap.add_argument("--order", choices=["file", "auto"], default="file",
                    help="lineage order top to bottom: as written (default), or a spectrum "
                         "computed from the also= links")
    args = ap.parse_args()

    cohorts, roots = parse_outline(args.outline)
    if args.order == "auto":
        roots, got, had = spectrum_order(roots)
        print(f"order (also= links between neighbours: {had} -> {got}):")
        for r in roots:
            print(f"    # {r.label}")
    svg, width, height = render(roots, cohorts, STYLE)
    out = Path(args.output) if args.output else Path(args.outline).with_suffix(".svg")
    out.write_text(svg, encoding="utf-8")

    nodes = [n for r in roots for n in walk(r.children)]
    per = ", ".join(f"{name}: {sum(n.cohort == i for n in nodes)}" for i, name in enumerate(cohorts))
    print(f"{out}  {width:.0f} x {height:.0f} px  |  {len(roots)} lineages, {len(nodes)} nodes, "
          f"{sum(n.keep for n in nodes)} kept  ({per})")


if __name__ == "__main__":
    main()
