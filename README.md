# lineage-tree

Draw the intellectual lineage of a design project as a single SVG: which thinkers, works and
precedents came in at which stage, which ones branched, and which ones lasted to the end.

![Example lineage](example/sample.svg)

The example ([`example/sample.md`](example/sample.md)) is a made-up research project, ordered
with `--order axis --axis axes/ddc.txt`.

## Reading the drawing

- **Left to right is time.** Each dashed column is a stage of the project (a *cohort*). A label
  sits in the stage where it first appeared.
- **Inside a stage, left to right is hierarchy:** lineage › name › concept. A branch that crosses
  a dashed line is something that picked up a new part later.
- **Top to bottom is a spectrum.** Lineages are ordered so that each one sits next to the
  lineages it shares names with; the page reads as one continuous gradient of kinship rather
  than a stack of separate boxes.
- **Red** labels lasted to the end of the project.

The layout follows four rules: every leaf gets its own row, one font at one size, one padding
value between any text and any line end, and no boxes around text.

## Usage

Needs Python 3.8+. No other dependency; install Pillow only if you want exact label widths from a
font file.

```
python3 lineage_tree.py outline.md                 # writes outline.svg
python3 lineage_tree.py outline.md -o lineage.svg
python3 lineage_tree.py outline.md --order axis --axis axes/ddc.txt     # order lineages by class= on an axis
python3 lineage_tree.py outline.md --order auto    # order lineages by shared also= names
```

For exact widths, set `font_file` in `STYLE` at the top of the script to the font you will
typeset with (and `pip install pillow`). Without it, widths are estimated per character, CJK
counted as full width.

## Outline format

```
> one @cohort line per stage, in order; one # line per lineage
@cohort Start
@cohort Concept

# Archive and truth
## Sekula | Start | also=Photography
- The Body and the Archive | Start | keep
## Foucault | Concept
> notes start with > and are ignored

# Photography
## Barthes | Concept | keep
```

- `## name | stage | flags` is a name; it may have concepts under it or stand alone.
- `### name | stage | flags` is a name that continues from the `##` name above it.
- `- concept | stage | flags` is a concept under the nearest name.
- Flags: `keep` (lasted to the end, drawn red), `also=Other lineage` (also belongs to that
  lineage), `class=CODE` (position on an ordering axis, see below).
- A child cannot be earlier than its parent. Inside a lineage, names are ordered by stage, then
  by their order in the file.

All spacing, colours and dash patterns are in the `STYLE` dict at the top of the script.
`show_also=True` draws a dashed guide line for each `also=` name between neighbouring lineages.

## Making an outline: the questionnaire

[`questionnaire.md`](questionnaire.md) is a fill-in template that walks through stages, names,
concepts, lineages and order, one table each, and maps every answer to an outline line.

## Ordering the lineages

Top to bottom is meant to read as one continuous spectrum, and the order should come from a rule,
not from re-arranging by hand each time. Three orders are built in:

- `--order file` (default): as written.
- `--order axis --axis axes/ddc.txt` / `--order warburg`: by a standard classification read as a line. Tag any line
  with `class=`; a lineage sits at the median position of the classes on it and under it, and
  lineages without any class go last. `ddc` takes Dewey Decimal numbers (`class=720.9`; the
  subdivision keeps its place inside the main class) or main-class labels; `warburg` takes the
  four categories of the Warburg Institute Library (`class=Image`, `Word`, `Orientation`,
  `Action`). More axes are a list in `AXES` at the top of the script.
- `--order auto`: by shared names. Lineages whose names carry `also=` tags pointing at each other
  are put next to each other; among equally good orders the one closest to the file order wins,
  so lineages with no shared names stay where they are.

Which lineage a name belongs to stays a judgement. The questionnaire gives one test for it:
*what question was I asking when I picked this up?*

## License

MIT
