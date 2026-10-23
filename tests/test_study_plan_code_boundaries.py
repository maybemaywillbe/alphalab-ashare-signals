from alphalab.study_plan import classify, quota_for


def test_chinext_code_family_boundaries():
    assert classify('300001') == 'chinext'
    assert classify('301001') == 'chinext'
    assert classify('302132') == 'chinext'
    assert classify('302001') == 'chinext'
    assert classify('302999') == 'chinext'
    assert classify('303001') is None
    assert classify('688001') == 'star'
    assert classify('600000') == 'sh_main'
    assert classify('000001') == 'sz_main'


def test_original_seed_target_and_quotas_unchanged():
    assert quota_for(100) == {'sh_main':40,'sz_main':40,'chinext':15,'star':5}
