# CC-89 live proofs (E2E pre-PR)

Slice 4 / `feat/cc-89-plan-overrides`. Short raw output only. Demo transcript is `evidence/slice-4/cc-89-e2e-pre.txt`.

## A — invalid geography override (HTTP 422, loop not entered)

TestClient `POST /ask` with `run_ask` monkeypatched to append to a list.

```
status=422
body={"detail":[{"type":"value_error","loc":["body"],"msg":"Value error, geography override requires an executable GEOID","input":{"question":"population of Harris County","plan":{"geographies":[{"level":"county","for_spec":"county:201","in_spec":"state:48"}]}},"ctx":{"error":{}}}]}
GEOID_in_body=True
run_ask_called=[]
loop_not_entered=True
```

**Summary A:** 422. Body mentions GEOID. `run_ask` list empty (Census loop not entered).

## B — t10 default vs consecutive-ACS5 override

Question: `Plot median household income for Cuyahoga County every year from 2017 to 2023`  
GEOID `0500000US39035`. Two live `run_ask` calls.

```
=== B t10 default ===
default
  table_id=B19013
  attempted_years=[2017, 2018, 2019, 2021, 2022, 2023]
  requested_years=[2017, 2018, 2019, 2020, 2021, 2022, 2023]
  overlapping_vintage=True
  warning_codes=['overlapping_vintage', 'vintage_gap_2020']
  n_urls=6
  first_url_dataset='acs1'
  first_url=https://api.census.gov/data/2017/acs/acs1?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=county:035&in=state:39
  urls_contain_B19013_001M=True
  urls_for_county_035=True
  geoid=0500000US39035
=== B t10 consecutive-ACS5 override ===
override
  table_id=B19013
  attempted_years=[2017, 2018, 2019, 2020, 2021, 2022, 2023]
  requested_years=[2017, 2018, 2019, 2020, 2021, 2022, 2023]
  overlapping_vintage=True
  warning_codes=['overlapping_vintage']
  n_urls=7
  first_url_dataset='acs5'
  first_url=https://api.census.gov/data/2017/acs/acs5?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=county:035&in=state:39
  urls_contain_B19013_001M=True
  urls_for_county_035=True
  geoid=0500000US39035
override_consecutive_not_destaggered=True
override_attempted_equals_2017_2022_destagger=False
```

**Summary B:** Default used ACS1 (`acs1` first URL), `overlapping_vintage` present, destaggered 2020 (`attempted_years=[2017, 2018, 2019, 2021, 2022, 2023]`). Override kept consecutive ACS5 years `[2017, 2018, 2019, 2020, 2021, 2022, 2023]` (not destaggered to `[2017, 2022]`), `overlapping_vintage` still present, URLs contain `B19013_001M` and `for=county:035`.
