from sdocs_mcp.ui_interval_options import INTERVAL_PRESET_SECONDS, render_interval_options


def test_render_interval_includes_all_presets() -> None:
    html = render_interval_options()
    for sec in INTERVAL_PRESET_SECONDS:
        assert f'value="{sec}"' in html


def test_render_interval_without_custom() -> None:
    html = render_interval_options(include_custom=False)
    assert 'custom' not in html
