# CC-88 live proofs (browser)

Slice 4 / `feat/cc-88-two-pane`. Playwright against `npm run dev` + `POST /ask`
on `:8000`. Demo transcript is separate (`evidence/slice-4/cc-88-e2e-pre.txt`
when captured). This file is the owned q01 browser proof, not that transcript.

Favicon 404 only. Form stayed in chat. Canvas is the Working dataset region.

## A — q01 visible

Question: `What's the population of Harris County, Texas?`

```
chat_answer: present
active_question: What's the population of Harris County, Texas?
table_id: B01003
universe: Total population
geoid: 0500000US48201
dataset: acs5
estimate: 4,838,303
url: https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=county:201&in=state:48
url_has_M: True
alternatives: present (B03003 …)
form_in_chat: True
```

## B — q01 inspectable while a later question is loading

Second question submitted: `median household income in Houston`. Snapshot
taken while Ask was disabled and canvas showed `Looking up tables…`.

```
canvas_status: Looking up tables…
ask_disabled: True
active_question: What's the population of Harris County, Texas?
table_id: B01003
geoid: 0500000US48201
estimate: 4,838,303
universe: Total population
url_still_B01003: True
chat_answer_still_q01: True
```

Second request then succeeded and replaced the canvas (`B19013`, GEOID
`1600000US4835000`, estimate `64,813` ± `822`).

## C — failed later request keeps the active dataset

API process killed. Third question: `population of Travis County, Texas`.

```
alert: ask failed (500)
alert_in_chat: True
active_question: median household income in Houston
table_id: B19013
universe: Households
geoid: 1600000US4835000
estimate: 64,813
moe: 822
url: https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=place:35000&in=state:48
```

**Summary:** q01 stayed inspectable (URL, GEOID, universe, alternatives, table)
during the next lookup. A later HTTP failure left the then-active dataset on
the canvas and showed the failure as a chat alert.
