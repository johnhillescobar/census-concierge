# Census Data API geography grammar: what the documentation says (ACS 5-year 2023)

Researched 2026-10-24. Read-only. No API key used, no data query made.

## Sources actually read

| # | Source | Result |
|---|--------|--------|
| 1 | https://api.census.gov/data/2023/acs/acs5/geography.html | Loaded. Three columns only: Reference Date, Geography Level, Geography Hierarchy. "65 items". No wildcard or optionalWithWCFor column, no prose. |
| 2 | https://api.census.gov/data/2023/acs/acs5/examples.html | Loaded. "144 examples". Prose is only the API-key notice. Its only outbound link is `/data/key_signup.html`. |
| 3 | https://api.census.gov/data/2023/acs/acs5/geography.json | Loaded. 65 entries in `fips`, matching the HTML "65 items". 13 entries carry `wildcard`. Only this file has `requires`, `wildcard`, `optionalWithWCFor`. |
| 4 | `C:\Users\johnh\Dropbox\Python\census_tool\app_description\CENSUS_DISCUSSION.md` | Read in full. Used as mechanics only. Discrepancies listed below. |
| 5 | https://www.census.gov/data/developers/guidance/api-user-guide/query-components.html | Supplementary. Neither page in (1) or (2) links to a summary-level or wildcard document, so there was no link to follow. A web search found no Census document that defines `optionalWithWCFor` (it appeared only in third-party R-package output). I fetched this one Census page for the wildcard rules. |

Verification note: the three api.census.gov pages were fetched twice, once through the WebFetch summarizer and once as raw bytes (public static files, no key, saved outside the repo under `scratchpad\cc102\raw\`). The tables below were checked against the raw bytes. The summarizer's transcription of geography.json matched the raw file.

## Definitions: nothing in the documentation defines the JSON fields

No fetched page defines `requires`, `wildcard` or `optionalWithWCFor`. Everything about their meaning below is read off the data and the examples and is marked INFERRED where it goes beyond a verbatim fact.

The only Census prose about wildcards is the User Guide, https://www.census.gov/data/developers/guidance/api-user-guide/query-components.html:

- "A wildcard (:*) can be included to search for all the values of a variable."
- "Wildcards work for geographies and string variables only."
- "You can include wildcards (:*) along with &for and &in."
- "&in and + restricts to geographic areas smaller than state level."

That page, by the fetch's own report, says nothing about required parents, hierarchy, tract or block group, or omitting a parent when a wildcard is used.

## Table: the 16 requested levels (2023 ACS 5-year)

"requires" is in the order given in geography.json. It matches the HTML hierarchy with the level itself appended last. "wc" is the `wildcard` array. "optWC" is `optionalWithWCFor`. A dash means the key is absent from geography.json.

Examples are verbatim `for`/`in` portions from examples.html (the `get=` and `&key=` parts are omitted). `%20` is a space.

| Level (API token) | Summary level | requires | wc (may be `*`) | optWC | Documented examples (examples.html) |
|---|---|---|---|---|---|
| `state` | 040 | none | none | none | `for=state:*` ; `for=state:06` |
| `county` | 050 | state | state | state | `for=county:*` ; `for=county:*&in=state:*` ; `for=county:037&in=state:06` |
| `place` | 160 | state | state | state | `for=place:*` ; `for=place:*&in=state:*` ; `for=place:51000&in=state:36` |
| `county subdivision` | 060 | state, county | county | county | `for=county%20subdivision:*&in=state:48` ; `for=county%20subdivision:*&in=state:48&in=county:*` ; `for=county%20subdivision:91835&in=state:48%20county:201` |
| `tract` | 140 | state, county | county | county | `for=tract:*&in=state:06` ; `for=tract:*&in=state:06&in=county:*` ; `for=tract:018700&in=state:06%20county:073` |
| `block group` | 150 | state, county, tract | county, tract | tract | `for=block%20group:*&in=state:06%20county:073` ; `for=block%20group:*&in=state:06&in=county:*&in=tract:*` ; `for=block%20group:*&in=state:06&in=county:073&in=tract:*` ; `for=block%20group:1&in=state:06%20county:073%20tract:018700` |
| `zip code tabulation area` | 860 | none | none | none | `for=zip%20code%20tabulation%20area:*` ; `for=zip%20code%20tabulation%20area:77494` |
| `congressional district` | 500 | state | state | state | `for=congressional%20district:*` ; `for=congressional%20district:*&in=state:*` ; `for=congressional%20district:98&in=state:72` |
| `state legislative district (upper chamber)` | 610 | state | none | none | `for=state%20legislative%20district%20(upper%20chamber):*&in=state:06` ; `for=state%20legislative%20district%20(upper%20chamber):039&in=state:06` |
| `state legislative district (lower chamber)` | 620 | state | none | none | `for=state%20legislative%20district%20(lower%20chamber):*&in=state:06` ; `for=state%20legislative%20district%20(lower%20chamber):027&in=state:06` |
| `school district (unified)` | 970 | state | state | state | `for=school%20district%20(unified):*` ; `for=school%20district%20(unified):*&in=state:*` ; `for=school%20district%20(unified):99999&in=state:06` |
| `public use microdata area` | 795 | state | state | state | `for=public%20use%20microdata%20area:*` ; `for=public%20use%20microdata%20area:*&in=state:*` ; `for=public%20use%20microdata%20area:04412&in=state:36` |
| `urban area` | 400 | none | none | none | `for=urban%20area:*` ; `for=urban%20area:63217` |
| `metropolitan statistical area/micropolitan statistical area` | 310 | none | none | none | `for=metropolitan%20statistical%20area/micropolitan%20statistical%20area:*` ; `for=metropolitan%20statistical%20area/micropolitan%20statistical%20area:35620` |
| `metropolitan division` | 314 (the only plain row; 323 is the "(or part)" variant under state) | metropolitan statistical area/micropolitan statistical area | none | none | `for=metropolitan%20division:*&in=metropolitan%20statistical%20area/micropolitan%20statistical%20area:35620` ; `for=metropolitan%20division:35614&in=metropolitan%20statistical%20area/micropolitan%20statistical%20area:35620` |
| `combined statistical area` | 330 | none | none | none | `for=combined%20statistical%20area:*` ; `for=combined%20statistical%20area:408` |

Raw JSON for the two rows that matter most (https://api.census.gov/data/2023/acs/acs5/geography.json):

```json
{"name": "tract", "geoLevelDisplay": "140", "requires": ["state","county"], "wildcard": ["county"], "optionalWithWCFor": "county"}
{"name": "block group", "geoLevelDisplay": "150", "requires": ["state","county","tract"], "wildcard": ["county","tract"], "optionalWithWCFor": "tract"}
```

### Same `name`, different rows

Several `name` values occur on more than one summary level, with different `requires`. A static table keyed only by the `for=` token is ambiguous. Key it by (token, requires), or by summary level.

- `county`: 050 (requires state); 313 (requires MSA/µSA, state (or part)); 316 (MSA/µSA, metropolitan division, state (or part)); 322 (state, MSA/µSA (or part)); 324 (state, MSA/µSA (or part), metropolitan division (or part)).
- `county (or part)`: 155, 270, 430, 510, 612, 622.
- `state (or part)`: 260, 290, 311, 315, 331, 333, 410.
- `metropolitan statistical area/micropolitan statistical area`: 310 (no parent) and 332 (requires combined statistical area).
- `place/remainder (or part)`: 070 and 269.

Levels with a plain top-level row are not the same as levels reachable under a parent. Example: there is no top-level `metropolitan division` row without an MSA/µSA parent (see discrepancy 2).

### Two spellings of `in=` appear in the documented examples

- One `in` with space-joined (`%20`) pairs: `in=state:06%20county:073`.
- Repeated `in` parameters: `in=state:06&in=county:*`.

Both are documented. Single-unit examples use the space-joined form. The wildcard-in-parent examples (county:*, tract:*, state:*) use the repeated form.

## Answers for tract and block group

### Tract

(a) Every tract inside a state. Documented verbatim, https://api.census.gov/data/2023/acs/acs5/examples.html:

```
for=tract:*&in=state:06
```

This omits county. The same page also gives the explicit-wildcard spelling `for=tract:*&in=state:06&in=county:*`. geography.json agrees: `wildcard: ["county"]`, `optionalWithWCFor: "county"`.

(b) One tract by its code. Documented verbatim:

```
for=tract:018700&in=state:06%20county:073
```

Both required parents (state, county) are given as concrete codes. No example gives a single tract code with county omitted or wildcarded. INFERRED: a 6-digit tract code is only unique within a county, so county is needed. This is an inference from the examples, not a stated rule.

### Block group

(a) Every block group inside a state. The page gives two shapes that hold for a state, and one that holds for a county:

- State-wide, verbatim: `for=block%20group:*&in=state:06&in=county:*&in=tract:*`. This is the only documented form that covers a whole state. It wildcards both county and tract explicitly.
- One county, tract omitted, verbatim: `for=block%20group:*&in=state:06%20county:073`.
- One county, tract explicit wildcard, verbatim: `for=block%20group:*&in=state:06&in=county:073&in=tract:*`.

No example gives `for=block group:*&in=state:06` alone (county and tract both omitted). The documentation is silent on whether that form is accepted. The JSON points toward "no": `optionalWithWCFor` is `"tract"` only, while `county` appears under `wildcard` (INFERRED reading: tract may be omitted, county may be `*` but is not listed as omittable). Treat state-wide block groups as the three-part form above unless a live call proves otherwise.

(b) One block group by its code. Documented verbatim:

```
for=block%20group:1&in=state:06%20county:073%20tract:018700
```

All three required parents (state, county, tract) are concrete.

### Rule that fits every documented example (INFERRED)

Every example that omits a required parent has `for=<level>:*` (an all-units request). Every example that names one unit by code supplies every `requires` parent as a concrete code. No example mixes a single-unit `for` with an omitted or wildcarded parent. The documentation does not state this as a rule. Treat it as the safe subset: the documented grammar covers "all of a level" (parents may be omitted or `*` where `wildcard` / `optionalWithWCFor` allow) and "one unit" (all parents concrete).

### Minimums for other requested levels, from the table

- All units of the level inside a state: `county`, `place`, `congressional district`, `public use microdata area`, `school district (unified)` take `in=state:<fips>`. State legislative districts (upper and lower) also need `in=state:<fips>`, and the JSON gives them no wildcard, so the documented examples never use `in=state:*` or omit `in` for them.
- `county subdivision` and `tract`: `in=state:<fips>` is enough for "all"; county may be omitted.
- `zip code tabulation area`, `urban area`, `metropolitan statistical area/micropolitan statistical area`, `combined statistical area`: no parent in the 2023 ACS 5-year list. `for=<level>:*` is the whole request.
- `metropolitan division`: needs `in=metropolitan statistical area/micropolitan statistical area:<code>`. No wildcard is listed for that parent. (The "(or part)" variant, row 323, needs `in=state:<fips>%20metropolitan statistical area/micropolitan statistical area (or part):<code>`.)
- One unit by code: `for=<level>:<code>` plus every `requires` parent as a concrete code (and none for the four parentless levels).

## Where the documentation is silent

1. No Census page fetched defines `requires`, `wildcard` or `optionalWithWCFor`. The meaning of `optionalWithWCFor` is read from the data only (it is always the last element of `requires`, and every example that omits a parent uses a `*` for value).
2. Whether a parent that is not in `wildcard` can be `*` (for example `in=state:*` on a state legislative district): not stated. The examples never do it.
3. Whether an omitted parent is allowed together with a concrete `for` code (`for=tract:018700&in=state:06`): not stated; no example.
4. Whether `for=block group:*&in=state:06` is accepted: not stated; no example.
5. The User Guide page fetched says nothing about required parents, hierarchy, or tract and block group.
6. These are the 2023 ACS 5-year lists only. Other datasets and vintages publish their own geography.json; this was not checked.

Not done here, and worth a live check by the caller (the task forbade keys and data calls): items 2 to 4 above.

## Discrepancies

### Between geography.html and geography.json

None found in the facts both carry. The 65 rows, summary-level codes and hierarchies match. The JSON strictly adds information the HTML omits: `requires`, `wildcard`, `optionalWithWCFor`. The HTML hierarchy is `requires` plus the level's own name.

### Between the examples and geography.json

None found. Every example that omits a parent or uses `in=<parent>:*` is for a level whose `wildcard` / `optionalWithWCFor` allows it, and no example wildcard-spells a parent that has no `wildcard` entry (610, 620, 314 and every other row without `wildcard`; 52 of the 65 rows have none).

### Between CENSUS_DISCUSSION.md and the 2023 ACS 5-year documentation

1. Its Notes section says "There is no official JSON for 'all valid geography levels' per dataset." geography.json exists for this dataset and carries the hierarchy and wildcard data.
2. Lines 206 and 258: `for=metropolitan division:*` with no `in`. geography.json has no top-level metropolitan division row. Row 314 requires MSA/µSA and has no `wildcard`, and every documented example supplies `in=...:35620`. Not backed by the docs.
3. Lines 214 and 308: `for=county:*&in=metropolitan statistical area/micropolitan statistical area:35620`. Row 313 requires `state (or part)` as well, with no `wildcard`; the documented example is `for=county:*&in=metropolitan statistical area/micropolitan statistical area:31080%20state%20(or%20part):06`. Not backed by the docs as written.
4. Lines 215 and 312: `for=county:*&in=metropolitan division:35614`. Row 316 requires MSA/µSA, metropolitan division, and `state (or part)`. Not backed by the docs as written.
5. Lines 208-209 and 266-270: `new england city and town area` and `new england city and town area division`. Neither string appears anywhere in the 2023 ACS 5-year geography.json, geography.html or examples.html. They are not listed levels in this dataset.
6. Consistent with the docs: lines 156 and 283-295 (county, place, tract, block group with all parents given), 213 and 316 (`state (or part)` under an MSA), and 187 (the row 315 shape).

Items 2 to 4 may still work on the live API (the documentation neither confirms nor rules that out). They are simply not documented, and the documented forms differ.
