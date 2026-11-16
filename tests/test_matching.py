from monitor.matching import categorize, match_existing


def test_small_title_edit_is_the_same_offer():
    existing = ["Cebu Island Hopping – Premium Boat Joiner Tour 2026-2027"]
    assert match_existing("Cebu Island Hopping - Premium Boat Joiner Tour 2027-2028", existing) == existing[0]


def test_private_and_shared_stay_separate():
    existing = ["Private Mactan Island Hopping in Cebu (3 Islands)"]
    assert match_existing("Joiners Mactan Island Hopping in Cebu (3 Islands)", existing) is None


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
