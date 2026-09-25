from matching.filters import infer_seniority, blocks_visa_sponsorship, passes_hard_filters


class _Job:
    def __init__(self, location=None, remote=False, seniority=None, description=""):
        self.location = location
        self.remote = remote
        self.seniority = seniority
        self.description = description


def test_infer_seniority_detects_senior():
    assert infer_seniority("Senior Backend Engineer") == "senior"


def test_infer_seniority_detects_intern():
    assert infer_seniority("Software Engineering Intern") == "intern"


def test_infer_seniority_detects_lead_and_staff():
    assert infer_seniority("Staff Engineer") == "staff"
    assert infer_seniority("Lead Product Manager") == "lead"


def test_infer_seniority_returns_none_when_no_signal():
    assert infer_seniority("Backend Engineer") is None


def test_blocks_visa_sponsorship_detects_no_sponsorship_language():
    assert blocks_visa_sponsorship("We are unable to sponsor visas for this role.")
    assert blocks_visa_sponsorship("Must be a U.S. citizen only.")


def test_blocks_visa_sponsorship_false_for_normal_description():
    assert not blocks_visa_sponsorship("We build scalable backend systems in Python.")


def test_passes_hard_filters_no_prefs_passes_everything():
    job = _Job(location="Berlin", remote=False, seniority="junior")
    assert passes_hard_filters({}, job) is True


def test_passes_hard_filters_location_mismatch_fails():
    job = _Job(location="Berlin", remote=False)
    assert passes_hard_filters({"locations": ["Bengaluru"]}, job) is False


def test_passes_hard_filters_remote_job_passes_remote_pref():
    job = _Job(location="Anywhere", remote=True)
    assert passes_hard_filters({"locations": ["Bengaluru"], "remote_types": ["remote"]}, job) is True


def test_passes_hard_filters_remote_job_fails_onsite_only_pref():
    job = _Job(location="Anywhere", remote=True)
    assert passes_hard_filters({"remote_types": ["onsite"]}, job) is False


def test_passes_hard_filters_missing_location_data_does_not_exclude():
    job = _Job(location=None, remote=False)
    assert passes_hard_filters({"locations": ["Bengaluru"]}, job) is True


def test_passes_hard_filters_seniority_mismatch_fails():
    job = _Job(seniority="intern")
    assert passes_hard_filters({"seniority": ["senior"]}, job) is False


def test_passes_hard_filters_missing_seniority_data_does_not_exclude():
    job = _Job(seniority=None)
    assert passes_hard_filters({"seniority": ["senior"]}, job) is True


def test_passes_hard_filters_visa_required_blocks_no_sponsorship_job():
    job = _Job(description="We do not sponsor visas.")
    assert passes_hard_filters({"visa_sponsorship_required": True}, job) is False


def test_passes_hard_filters_visa_not_required_ignores_sponsorship_text():
    job = _Job(description="We do not sponsor visas.")
    assert passes_hard_filters({}, job) is True
