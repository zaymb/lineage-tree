# Lineage questionnaire

Fill this in once at the end of a project (or at each stage), then copy the answers into an
outline for `lineage_tree.py`. Each section of the questionnaire becomes one part of the outline.

---

## 1. Stages (cohorts)

List the stages of the project in order. These become the columns of the drawing.

| # | Stage name (short, e.g. "Brief", "Concept", "Week 1–3") | Dates |
|---|---|---|
| 1 | | |
| 2 | | |
| 3 | | |

Outline: one `@cohort NAME` line per row, in this order.

---

## 2. Names

Every thinker, work, precedent, project or named technique that shaped the project gets one row.
Do not sort yet.

| Name | Stage it first appeared | Did it last to the end? (y/n) | What did it give you, in one line |
|---|---|---|---|
| | | | |
| | | | |

"Lasted to the end" means it is still visible in the final piece. Those rows get the `keep` flag
and are drawn red.

---

## 3. Concepts under a name (optional)

If a name gave you more than one idea, list the ideas under it.

| Name | Concept | Stage it first appeared | Lasted? |
|---|---|---|---|
| | | | |

Outline: `- concept | stage | keep` under the `## name` line.
A concept cannot appear earlier than the name above it.

---

## 4. Lineages (themes)

Group the names into families. Use the test below for every name, one name at a time.

**Home test.** Ask: *what question was I asking when I picked this up?* Names picked up while
asking the same question share a lineage. Name the lineage after that question, not after a
discipline ("Archive and truth", not "History").

**Second home.** If a name was clearly picked up for one question but ended up answering another,
write the other lineage in the last column. That becomes `also=` and it is what places lineages
next to each other on the page.

| Name | Home lineage | Also answers (another lineage, optional) |
|---|---|---|
| | | |

Aim for 5–9 lineages. A lineage with one name is probably a concept of another lineage.

---

## 5. Order of the lineages

The drawing reads top to bottom as a continuous spectrum: each lineage should sit next to the
ones it shares names with. You can either

- write the order yourself, or
- leave it to `python3 lineage_tree.py outline.md --order auto`, which puts lineages that share
  `also=` names next to each other. Lineages with no shared names keep the order you wrote them
  in, so the more "also answers" you fill in above, the more of the spectrum it can work out.

| Order | Lineage | Shares names with |
|---|---|---|
| 1 | | |
| 2 | | |
