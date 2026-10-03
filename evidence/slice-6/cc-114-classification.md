# CC-114 classification

Rule: `evidence/slice-6/cc-114-rule.md`. Command: `uv run python scripts/classify_geo_levels.py`.
Trials: `evidence/latest.json` generated 2026-10-02T02:25:10+00:00, --repeat 3, n=186.

## Golden audit (all goldens, outcome-blind)

| id | golden | rule | expected by rule | note |
| --- | --- | --- | --- | --- |
| q01 | county | 1 | county | names 'county' |
| q02 | county | 1 | county | names 'county' |
| q03 | county | 1 | county | names 'county' |
| q04 | tract | 1 | tract | names 'tract' |
| q05 | place | 2 | place | Portland city, AR / Ashley County: 0.0012; Portland CDP, CO / Ouray County: 0.0059; Portland CDP, CT / Middlesex County: 0.0162; Portland city, IN / Jay County: 0.0127; Portland CDP, IA / Cerro Gordo County: 0.0017; Portland city, ME / Cumberland County: 0.0258; Portland city, MI / Ionia County: 0.0046; Portland city, ND / Traill County: 0.0010; Portland city, OR: 3 counties; Portland borough, PA / Northampton County: 0.0013; Portland city, TN: 2 counties; Portland city, TX: 2 counties |
| q06 | county | 1 | county | names 'county' |
| q07 | county | 1 | county | names 'county' |
| q08 | county | 1 | county | names 'county' |
| q09 | county | 1 | county | names 'county' |
| q10 | county | 2 | county | no same-name place in the Gazetteer |
| q11 | metropolitan statistical area/micropolitan statistical area | 1 | metropolitan statistical area/micropolitan statistical area | names 'metropolitan statistical area/micropolitan statistical area' |
| q12 | state | 2 | state | bare state name |
| q13 | place | 2 | place | Providence town, AL / Marengo County: 0.0018; Providence city, KY / Webster County: 0.0182; Providence city, RI / Providence County: 0.0449; Providence Village town, TX / Denton County: 0.0021; Providence city, UT / Cache County: 0.0033 |
| q14 | county | 2 | county | Baltimore city, MD / Baltimore city: 1.0000 |
| q15 | county | 1 | county | names 'county' |
| q16 | place | 2 | place | Ithaca city, MI / Gratiot County: 0.0101; Ithaca village, NE / Saunders County: 0.0003; Ithaca city, NY / Tompkins County: 0.0114; Ithaca village, OH / Darke County: 0.0001 |
| q17 | county | 1 | county | names 'county' |
| q18 | place | 2 | place | Milwaukee CDP, NC / Northampton County: 0.0032; Milwaukee city, WI: 3 counties |
| q19 | county | 1 | county | names 'county' |
| q20 | place | 2 | place | Boise City city, ID / Ada County: 0.0799; Boise City city, OK / Cimarron County: 0.0008 |
| q21 | county | 6 | - | informal region, no entity to test |
| q22 | place | 2 | place | Somerville city, MA / Middlesex County: 0.0050 |
| q25 | county | 1 | county | names 'county' |
| q26 | county | 2 | county | Anchorage municipality, AK / Anchorage Municipality: 1.0000; Anchorage city, KY / Jefferson County: 0.0078 |
| q27 | county | 1 | county | names 'county' |
| q28 | state | 2 | state | bare state name |
| q29 | state | 2 | state | bare state name |
| q30 | place | 2 | place | Hialeah city, FL / Miami-Dade County: 0.0114 |
| q31 | county | 1 | county | names 'county' |
| q32 | state | 2 | state | bare state name |
| q33 | place | 2 | place | Santa Ana city, CA / Orange County: 0.0345 |
| q34 | place | 2 | place | Bozeman city, MT / Gallatin County: 0.0079 |
| q35 | county | 2 | county | no same-name place in the Gazetteer |
| q36 | county | 1 | county | names 'county' |
| q37 | county | 1 | county | names 'county' |
| q38 | place | 2 | place | Fremont city, CA / Alameda County: 0.1062; Fremont town, IN / Steuben County: 0.0101; Fremont city, IA / Mahaska County: 0.0019; Fremont city, MI / Newaygo County: 0.0043; Fremont CDP, MO / Carter County: 0.0004; Fremont city, NE / Dodge County: 0.0202; Fremont town, NC / Wayne County: 0.0024; Fremont city, OH / Sandusky County: 0.0209; Fremont CDP, UT / Wayne County: 0.0007; Fremont village, WI / Waupaca County: 0.0014 |
| q39 | place | 2 | place | Detroit town, AL / Lamar County: 0.0022; Detroit village, IL / Pike County: 0.0003; Detroit CDP, KS / Dickinson County: 0.0006; Detroit city, MI / Wayne County: 0.2267; Detroit city, OR / Marion County: 0.0005; Detroit town, TX / Red River County: 0.0015 |
| q40 | place | 2 | place | Cambridge city, ID / Washington County: 0.0003; Cambridge village, IL / Henry County: 0.0024; Cambridge City town, IN / Wayne County: 0.0025; Cambridge city, IA / Story County: 0.0023; Cambridge city, KS / Cowley County: 0.0002; Cambridge city, KY / Jefferson County: 0.0001; Cambridge city, MD / Dorchester County: 0.0197; Cambridge city, MA / Middlesex County: 0.0078; Cambridge city, MN / Isanti County: 0.0172; Cambridge city, NE / Furnas County: 0.0019; Cambridge village, NY / Washington County: 0.0021; Cambridge city, OH / Guernsey County: 0.0122; Cambridge village, VT / Lamoille County: 0.0027; Cambridge village, WI: 2 counties |
| q41 | place | 2 | place | Ann Arbor city, MI / Washtenaw County: 0.0399 |
| q42 | place | 2 | place | Fayetteville CDP, AL / Talladega County: 0.0237; Fayetteville city, AR / Washington County: 0.0575; Fayetteville city, GA / Fayette County: 0.0666; Fayetteville village, IL / St. Clair County: 0.0004; Fayetteville village, NY / Onondaga County: 0.0022; Fayetteville city, NC / Cumberland County: 0.2272; Fayetteville village, OH / Brown County: 0.0010; Fayetteville CDP, PA / Franklin County: 0.0042; Fayetteville city, TN / Lincoln County: 0.0169; Fayetteville city, TX / Fayette County: 0.0005; Fayetteville town, WV / Fayette County: 0.0084 |
| q43 | county | 1 | county | names 'county' |
| q44 | county | 1 | county | names 'county' |
| t09 | place | 2 | place | Denver city, CO / Denver County: 1.0000; Denver town, IN / Miami County: 0.0006; Denver city, IA / Bremer County: 0.0039; Denver village, MO / Worth County: 0.0014; Denver CDP, NC / Lincoln County: 0.0200; Denver borough, PA / Lancaster County: 0.0014; Denver City town, TX: 2 counties |
| t10 | county | 1 | county | names 'county' |
| t11 | place | 2 | place | Middlebury CDP, VT / Addison County: 0.0185 |
| t12 | county | 1 | county | names 'county' |
| t13 | tract | 1 | tract | names 'tract' |
| t15 | zip code tabulation area | 1 | zip code tabulation area | names 'zip code tabulation area' |
| t17 | tract | 1 | tract | names 'tract' |
| t18 | tract | 1 | tract | names 'tract' |
| q23 | place | 4 | - | legs ['place', 'state']; golden has one level |
| q24 | zip code tabulation area | 1 | zip code tabulation area | names 'zip code tabulation area' |
| h01 | place | 2 | place | Tucson city, AZ / Pima County: 0.0262 |
| h02 | place | 2 | place | Dearborn city, MI / Wayne County: 0.0396; Dearborn city, MO: 2 counties |
| h03 | place | 2 | place | Cleveland town, AL / Blount County: 0.0122; Cleveland CDP, FL / Charlotte County: 0.0077; Cleveland city, GA / White County: 0.0161; Cleveland village, IL / Henry County: 0.0004; Cleveland city, MN / Le Sueur County: 0.0012; Cleveland city, MS / Bolivar County: 0.0086; Cleveland city, MO / Cass County: 0.0021; Cleveland village, NY / Oswego County: 0.0012; Cleveland town, NC / Rowan County: 0.0030; Cleveland city, ND / Stutsman County: 0.0001; Cleveland city, OH / Cuyahoga County: 0.1700; Cleveland city, OK / Pawnee County: 0.0047; Cleveland city, TN / Bradley County: 0.0824; Cleveland city, TX: 3 counties; Cleveland town, UT / Emery County: 0.0002; Cleveland town, VA / Russell County: 0.0003; Cleveland village, WI / Manitowoc County: 0.0034 |
| h04 | place | 2 | place | Buffalo City CDP, AR / Baxter County: 0.0003; Buffalo village, IL / Sangamon County: 0.0004; Buffalo CDP, IN / White County: 0.0047; Buffalo city, IA / Scott County: 0.0148; Buffalo city, KS / Wilson County: 0.0006; Buffalo CDP, KY / Larue County: 0.0045; Buffalo city, MN / Wright County: 0.0117; Buffalo city, MO / Dallas County: 0.0053; Buffalo city, NY / Erie County: 0.0387; Buffalo city, ND / Cass County: 0.0003; Buffalo CDP, OH / Guernsey County: 0.0009; Buffalo town, OK / Harper County: 0.0011; Buffalo CDP, SC / Union County: 0.0078; Buffalo town, SD / Harding County: 0.0002; Buffalo city, TX / Leon County: 0.0044; Buffalo town, WV / Putnam County: 0.0040; Buffalo City city, WI / Buffalo County: 0.0024; Buffalo city, WY / Johnson County: 0.0011 |
| h05 | state | 2 | state | bare state name |
| h06 | county | 1 | county | names 'county' |
| h07 | county | 1 | county | names 'county' |
| h08 | place | 2 | place | Portland city, ME / Cumberland County: 0.0258 |

## Mismatched trials

| id | repeat | bucket | detail | url |
| --- | --- | --- | --- | --- |
| q04 | 1 | pipeline_wrong | expected 'tract', fetched ['place'] | `https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B17001_001E,B17001_001M&for=place:22000&in=state:26` |
| q11 | 1 | pipeline_wrong | expected 'metropolitan statistical area/micropolitan statistical area', fetched ['place'] | `https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B08303_001E,B08303_001M&for=place:04000&in=state:13` |
| q14 | 1 | golden_arguable | coterminous: Baltimore city, MD / Baltimore city: 1.0000 (warnings: ambiguous_place) | `https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B08201_001E,B08201_001M&for=place:04000&in=state:24` |
| q26 | 1 | pipeline_wrong | expected 'county', fetched ['place'] [any-coterminous reading: golden_arguable] | `https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B23020_001E,B23020_001M&for=place:03000&in=state:02` |
| t15 | 1 | table_cannot_serve | acs1 lacks 'zip code tabulation area' (warnings: vintage_gap_2020, zcta_not_zip) | `https://api.census.gov/data/2018/acs/acs1?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=state:36 https://api.census.gov/data/2019/acs/acs1?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=state:36 https://api.census.gov/data/2021/acs/acs1?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=state:36 https://api.census.gov/data/2022/acs/acs1?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=state:36 https://api.census.gov/data/2023/acs/acs1?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=state:36 https://api.census.gov/data/2024/acs/acs1?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=state:36` |
| q23 | 1 | golden_misspecified | fetched ['place', 'state']; legs ['place', 'state'] (warnings: shared_sample, ambiguous_place) | `https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B25064_001E,B25064_001M&for=place:05000&in=state:48 https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B25064_001E,B25064_001M&for=state:48` |
| q04 | 2 | pipeline_wrong | expected 'tract', fetched ['place'] | `https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B17001_001E,B17001_001M&for=place:22000&in=state:26` |
| q08 | 2 | pipeline_wrong | expected 'county', fetched ['state'] | `https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B18101_001E,B18101_001M&for=state:50` |
| q11 | 2 | pipeline_wrong | expected 'metropolitan statistical area/micropolitan statistical area', fetched ['place'] | `https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B08303_001E,B08303_001M&for=place:04000&in=state:13` |
| q14 | 2 | golden_arguable | coterminous: Baltimore city, MD / Baltimore city: 1.0000 (warnings: ambiguous_place) | `https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B08201_001E,B08201_001M&for=place:04000&in=state:24` |
| q26 | 2 | pipeline_wrong | expected 'county', fetched ['place'] [any-coterminous reading: golden_arguable] | `https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B23020_001E,B23020_001M&for=place:03000&in=state:02` |
| t15 | 2 | table_cannot_serve | acs1 lacks 'zip code tabulation area' (warnings: vintage_gap_2020, zcta_not_zip) | `https://api.census.gov/data/2018/acs/acs1?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=county:061&in=state:36 https://api.census.gov/data/2019/acs/acs1?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=county:061&in=state:36 https://api.census.gov/data/2021/acs/acs1?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=county:061&in=state:36 https://api.census.gov/data/2022/acs/acs1?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=county:061&in=state:36 https://api.census.gov/data/2023/acs/acs1?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=county:061&in=state:36 https://api.census.gov/data/2024/acs/acs1?get=NAME,GEO_ID,B19013_001E,B19013_001M&for=county:061&in=state:36` |
| q23 | 2 | golden_misspecified | fetched ['place', 'state']; legs ['place', 'state'] (warnings: shared_sample, ambiguous_place) | `https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B25064_001E,B25064_001M&for=place:05000&in=state:48 https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B25064_001E,B25064_001M&for=state:48` |
| q04 | 3 | pipeline_wrong | expected 'tract', fetched ['place'] | `https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B17001_001E,B17001_001M&for=place:22000&in=state:26` |
| q14 | 3 | golden_arguable | coterminous: Baltimore city, MD / Baltimore city: 1.0000 (warnings: ambiguous_place) | `https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B08201_001E,B08201_001M&for=place:04000&in=state:24` |
| q26 | 3 | pipeline_wrong | expected 'county', fetched ['place'] [any-coterminous reading: golden_arguable] | `https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B23020_001E,B23020_001M&for=place:03000&in=state:02` |
| t09 | 3 | pipeline_wrong | expected 'place', fetched ['county'] [any-coterminous reading: golden_arguable] (warnings: measure_unavailable, vintage_gap_2020) | `https://api.census.gov/data/2017/acs/acs1?get=NAME,GEO_ID,B28001_001E,B28001_001M&for=county:031&in=state:08 https://api.census.gov/data/2018/acs/acs1?get=NAME,GEO_ID,B28001_001E,B28001_001M&for=county:031&in=state:08 https://api.census.gov/data/2019/acs/acs1?get=NAME,GEO_ID,B28001_001E,B28001_001M&for=county:031&in=state:08 https://api.census.gov/data/2021/acs/acs1?get=NAME,GEO_ID,B28001_001E,B28001_001M&for=county:031&in=state:08 https://api.census.gov/data/2022/acs/acs1?get=NAME,GEO_ID,B28001_001E,B28001_001M&for=county:031&in=state:08 https://api.census.gov/data/2023/acs/acs1?get=NAME,GEO_ID,B28001_001E,B28001_001M&for=county:031&in=state:08 https://api.census.gov/data/2024/acs/acs1?get=NAME,GEO_ID,B28001_001E,B28001_001M&for=county:031&in=state:08` |
| q23 | 3 | golden_misspecified | fetched ['place', 'state']; legs ['place', 'state'] (warnings: shared_sample, ambiguous_place) | `https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B25064_001E,B25064_001M&for=place:05000&in=state:48 https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B25064_001E,B25064_001M&for=state:48` |

## Totals

- golden_arguable: 3
- golden_misspecified: 3
- pipeline_wrong: 10
- table_cannot_serve: 2
- total mismatched trials: 18

Any-coterminous reading (not a verdict; rule amendment 2):

- golden_arguable: 7
- golden_misspecified: 3
- pipeline_wrong: 6
- table_cannot_serve: 2
