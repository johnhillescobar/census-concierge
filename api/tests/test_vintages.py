"""Vintage policy: ACS1 where published, else non-overlapping ACS5."""

from __future__ import annotations

from src.vintages import (
    HEALTH_TABLE,
    POVERTY_TABLE,
    REASON_GAP_2020,
    REASON_MAX,
    REASON_OVERLAP,
    REASON_UNPUBLISHED,
    consecutive,
    is_series,
    nonoverlapping_acs5,
    period_for,
    pinned_table,
    plan_years,
    question_years,
    requested_years,
    span_years,
    stamp_provenance,
    year_span,
)

ACS1 = {2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024}
ACS5 = set(range(2016, 2025))
PUBLISHED = {"acs1": ACS1, "acs5": ACS5}


def test_consecutive_requires_a_dense_span() -> None:
    assert consecutive([2018, 2019, 2020, 2021, 2022]) is True
    assert consecutive([2019, 2022]) is False
    assert consecutive([2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024]) is False
    assert consecutive([2022]) is False
    assert consecutive([]) is False
    assert is_series([2018, 2019, 2021, 2022], PUBLISHED) is True
    assert is_series([2018, 2019, 2021, 2022]) is False
    assert is_series([2019, 2022], PUBLISHED) is False


def test_poverty_and_uninsured_wording_pin_tables() -> None:
    assert pinned_table("poverty in Fresno County") == POVERTY_TABLE
    assert pinned_table("Total population without health insurance") == HEALTH_TABLE


def test_from_to_is_a_year_span_hyphen_range_is_not() -> None:
    assert year_span("every year from 2017 to 2023") == list(range(2017, 2024))
    assert year_span("2018 through 2022") == list(range(2018, 2023))
    assert year_span("between 2015-2019 and 2018-2022") == []
    assert question_years("since 2017") == [2017]
    assert requested_years("since 2017", 2024) == list(range(2017, 2025))
    assert requested_years("from 2017 to 2023", 2024) == list(range(2017, 2024))
    assert question_years("population of Harris County, Texas in 2022") == [2022]
    assert requested_years("population of Harris County, Texas in 2022", 2024) == [2022]
    assert question_years("median income for 2022") == [2022]
    assert question_years("population of Austin compared to 2017") == []
    assert requested_years("since 2022", 2024) == [2022, 2023, 2024]


def test_nonoverlapping_acs5_keeps_2017_and_2022() -> None:
    years = list(range(2017, 2024))
    assert nonoverlapping_acs5(years) == [2017, 2022]


def test_gapped_acs5_years_are_fetched_as_requested() -> None:
    plan = plan_years(dataset="acs5", years=[2019, 2022], published=PUBLISHED)
    assert plan.dataset == "acs5"
    assert plan.attempted == [2019, 2022]
    assert plan.omitted == []
    assert plan.acs1_ineligible is False


def test_known_ineligible_acs5_fallback_year_sets_the_flag() -> None:
    plan = plan_years(dataset="acs5", years=[2024], published=PUBLISHED, acs1_ok=False)
    assert plan.dataset == "acs5"
    assert plan.attempted == [2024]
    assert plan.omitted == []
    assert plan.acs1_ineligible is True


def test_consecutive_acs5_without_acs1_destaggers() -> None:
    years = list(range(2017, 2024))
    plan = plan_years(dataset="acs5", years=years, published=PUBLISHED, acs1_ok=False)
    assert plan.dataset == "acs5"
    assert plan.attempted == [2017, 2022]
    assert plan.omitted == [2018, 2019, 2020, 2021, 2023]
    assert plan.reasons == [REASON_OVERLAP] * 5
    assert plan.acs1_ineligible is True


def test_consecutive_acs1_eligible_omits_2020() -> None:
    years = list(range(2018, 2023))
    plan = plan_years(dataset="acs5", years=years, published=PUBLISHED, acs1_ok=True)
    assert plan.dataset == "acs1"
    assert plan.attempted == [2018, 2019, 2021, 2022]
    assert plan.omitted == [2020]
    assert plan.reasons == [REASON_GAP_2020]
    assert plan.acs1_ineligible is False


def test_acs1_unpublished_hole_is_filled_as_a_gap() -> None:
    years = [2018, 2019, 2021, 2022]
    plan = plan_years(dataset="acs5", years=years, published=PUBLISHED, acs1_ok=True)
    assert plan.dataset == "acs1"
    assert plan.attempted == [2018, 2019, 2021, 2022]
    assert plan.omitted == [2020]
    assert plan.reasons == [REASON_GAP_2020]


def test_span_years_is_the_inclusive_range() -> None:
    assert span_years([2018, 2019, 2021, 2022]) == [2018, 2019, 2020, 2021, 2022]
    assert span_years([2022, 2018]) == [2018, 2019, 2020, 2021, 2022]
    assert span_years([]) == []


def test_destagger_omitted_years_follow_requested_order() -> None:
    published = {"acs1": ACS1, "acs5": ACS5 - {2020}}
    years = list(range(2016, 2024))
    plan = plan_years(dataset="acs5", years=years, published=published, acs1_ok=False)
    assert plan.attempted == [2016, 2021]
    assert plan.omitted == [2017, 2018, 2019, 2020, 2022, 2023]
    assert plan.reasons == [
        REASON_OVERLAP,
        REASON_OVERLAP,
        REASON_OVERLAP,
        REASON_UNPUBLISHED,
        REASON_OVERLAP,
        REASON_OVERLAP,
    ]


def test_destagger_omits_unpublished_acs5_years() -> None:
    years = list(range(2012, 2024))
    plan = plan_years(dataset="acs5", years=years, published=PUBLISHED, acs1_ok=False)
    assert 2012 not in plan.attempted
    assert plan.attempted == nonoverlapping_acs5([year for year in years if year in ACS5])
    assert REASON_UNPUBLISHED in plan.reasons
    assert plan.acs1_ineligible is True


def test_unknown_acs1_eligibility_destaggers_without_the_ineligible_warning() -> None:
    years = list(range(2017, 2024))
    plan = plan_years(dataset="acs5", years=years, published=PUBLISHED, acs1_ok=None)
    assert plan.attempted == [2017, 2022]
    assert plan.acs1_ineligible is False


def test_acs1_template_omits_2020_even_without_a_probe() -> None:
    years = list(range(2018, 2023))
    plan = plan_years(dataset="acs1", years=years, published=PUBLISHED, acs1_ok=False)
    assert plan.dataset == "acs1"
    assert 2020 not in plan.attempted
    assert plan.omitted == [2020]
    assert plan.reasons == [REASON_GAP_2020]


def test_overlapping_override_keeps_consecutive_acs5() -> None:
    years = list(range(2017, 2024))
    plan = plan_years(
        dataset="acs5",
        years=years,
        published=PUBLISHED,
        acs1_ok=False,
        allow_overlapping_acs5=True,
    )
    assert plan.dataset == "acs5"
    assert plan.attempted == years
    assert plan.omitted == []
    assert plan.acs1_ineligible is False


def test_unpublished_year_outside_2020_is_flagged() -> None:
    plan = plan_years(dataset="acs1", years=[2015, 2019], published=PUBLISHED)
    assert plan.attempted == [2019]
    assert plan.omitted == [2015]
    assert plan.reasons == [REASON_UNPUBLISHED]


def test_cap_omits_with_max_years_after_policy() -> None:
    years = list(range(2016, 2025))
    plan = plan_years(
        dataset="acs5",
        years=years,
        published=PUBLISHED,
        allow_overlapping_acs5=True,
        cap=3,
    )
    assert plan.attempted == [2016, 2017, 2018]
    assert plan.omitted == [2019, 2020, 2021, 2022, 2023, 2024]
    assert plan.reasons == [REASON_MAX] * 6


def test_cap_keeps_omitted_years_in_requested_order() -> None:
    years = list(range(2018, 2023))
    plan = plan_years(dataset="acs5", years=years, published=PUBLISHED, acs1_ok=True, cap=1)
    assert plan.attempted == [2018]
    assert plan.omitted == [2019, 2020, 2021, 2022]
    assert plan.reasons == [REASON_MAX, REASON_GAP_2020, REASON_MAX, REASON_MAX]


def test_period_for_acs1_is_the_end_year() -> None:
    assert period_for("acs1", 2019) == "2019"
    assert period_for("acs5", 2022) == "2018-2022"
    assert period_for("acs5", 2018) == "2014-2018"


def test_stamp_provenance_fills_dataset_vintage_period_and_table() -> None:
    rows = stamp_provenance(
        [{"GEO_ID": "1400000US26163500100", "year": "2022", "B28002_004E": "1"}],
        dataset="acs5",
        table_id="B28002",
    )
    assert rows[0]["dataset"] == "acs5"
    assert rows[0]["vintage"] == "2022"
    assert rows[0]["period"] == "2018-2022"
    assert rows[0]["table_id"] == "B28002"
