from monitor.matching import categorize, match_existing


def test_small_title_edit_is_the_same_offer():
    existing = ["Cebu Island Hopping – Premium Boat Joiner Tour 2026-2027"]
    assert match_existing("Cebu Island Hopping - Premium Boat Joiner Tour 2027-2028", existing) == existing[0]


def test_private_and_shared_stay_separate():
    existing = ["Private Mactan Island Hopping in Cebu (3 Islands)"]
    assert match_existing("Joiners Mactan Island Hopping in Cebu (3 Islands)", existing) is None


def test_shared_version_of_a_similar_tour_is_a_separate_offer():
    # Found on the first live run: these two were merged and one snapshot was lost.
    existing = ["Oslob Whale Shark Snorkeling + Badian Canyoneering in Kawasan Falls Tour Package"]
    assert match_existing("SHARED: Whale Shark Snorkeling + Badian Canyoneering in Kawasan Falls", existing) is None


def test_different_island_count_is_a_separate_offer():
    assert match_existing("Mactan Island Hopping (2 Islands)", ["Mactan Island Hopping (3 Islands)"]) is None


def test_different_tour_is_new():
    assert match_existing("Kawasan Falls Full Course Canyoneering", ["Mactan Island Hopping"]) is None


def test_no_existing_offers():
    assert match_existing("Anything", []) is None


def test_category_is_the_same_across_competitors():
    a = categorize("Oslob Whale Shark Watching + Badian Canyoneering Adventure Day Tour")
    b = categorize("Whaleshark Watching and Canyoneering Tour")
    assert a == b == "canyoneering+whale_shark"


def test_category_other():
    assert categorize("Airport transfer") == "other"
