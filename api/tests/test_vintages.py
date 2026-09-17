"""Vintage policy: ACS1 where published, else non-overlapping ACS5."""

from __future__ import annotations

from src.vintages import (
    REASON_GAP_2020,
    REASON_MAX,
    REASON_OVERLAP,
    REASON_UNPUBLISHED,
    consecutive,
    is_series,
    nonoverlapping_acs5,
    plan_years,
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


def test_nonoverlapping_acs5_keeps_2017_and_2022() -> None:
    years = list(range(2017, 2024))
    assert nonoverlapping_acs5(years) == [2017, 2022]


def test_gapped_acs5_years_are_fetched_as_requested() -> None:
    plan = plan_years(dataset="acs5", years=[2019, 2022], published=PUBLISHED)
    assert plan.dataset == "acs5"
    assert plan.attempted == [2019, 2022]
    assert plan.omitted == []
    assert plan.acs1_ineligible is False


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
