# CC-37 live proofs (browser)

Slice 4 / `feat/cc-37-plan-strip`. Playwright against `npm run dev` (`:5173`) +
`POST /ask` on `:8000` with `.env` keys. Demo transcript is separate
(`evidence/slice-4/cc-37-e2e-pre.txt` when captured). This file is the owned
t05 browser proof, not that transcript.

Favicon 404 only. Question form stayed in chat. Plan strip is on the canvas.

## A — t05 usable result plus candidates

Question: `Population of Springfield`

```
chat_answer: present
active_question: Population of Springfield
plan.dataset: acs5
plan.years: requested 2024; fetched 2024
plan.table_id: B01003
plan.geography: Springfield city, Missouri (1600000US2970000) first among returned GeoSpecs
table_id: B01003
universe: Total population
geoid: 1600000US2970000
estimate: 169,954 ± 92
url: https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=place:70000&in=state:29
url_has_M: True
warning: ambiguous_place (28 matching geographies)
alternatives: present (B02001 Race, …)
edit_plan: visible
```

## B — pick a different Springfield without retyping

Unchecked `Springfield city, Missouri`. Apply. Chat input still
`Population of Springfield`. Prior MO row stayed visible until success.

```
ask_body_question: Population of Springfield
plan.geography: Springfield city, Massachusetts (1600000US2567000); Springfield city, Illinois (1600000US1772000)
geoid_ma: 1600000US2567000  estimate 154,749 ± 56
geoid_il: 1600000US1772000  estimate 113,330 ± 437
url_ma: …/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=place:67000&in=state:25
url_il: …/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=place:72000&in=state:17
missouri_row: gone
warning: ambiguous_place still visible (27 remaining)
```

## C — related table click

Clicked `B02001 — Race — Total population`. Question input unchanged.

```
plan.table_id: B02001
table cells: B02001_001E for MA and IL
url_ma: …/B02001_001E,B02001_001M&for=place:67000&in=state:25
url_il: …/B02001_001E,B02001_001M&for=place:72000&in=state:17
```

## D — invalid table keeps the prior dataset

Edit plan, table `NOPE`, Apply. HTTP 422. Editor stayed open.

```
alert: invalid table_id override
table_aria_invalid: True
canvas_table: B02001
urls: still B02001_001E/M for MA and IL
```

**Summary:** t05 kept the usable Missouri result plus `ambiguous_place`.
Unchecking Missouri reran the original question and replaced the dataset with
other returned Springfields (URLs, GEOID, MOE). A related-table click switched
to B02001 without rewriting the prompt. An invalid table left that dataset in
place and showed the field error on the strip.
