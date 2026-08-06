"""ECharts chart building and rendering.

Pure functions build ECharts `option` dicts from report data; `render_echart`
embeds one in the Streamlit page. Colors come from the dataviz-validated
palette (light surface, categorical order 1-8).
"""

import json

import streamlit as st

# Validated palette (dataviz skill, light surface).
SURFACE, INK, INK2, MUTED, GRID, AXIS = (
    "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7")
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
               "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
S_BLUE, S_ORANGE = CATEGORICAL[0], CATEGORICAL[1]


def fmt_num(value) -> str:
    """Format a number with thousands separators; '—' for None."""
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value:,}"


def growth(financials: list, key: str):
    """YoY % change of `key` between the last two years, or None."""
    if len(financials) < 2:
        return None
    prev, latest = financials[-2].get(key), financials[-1].get(key)
    if prev in (None, 0) or latest is None:
        return None
    return (latest - prev) / prev * 100


def render_echart(option: dict, height: int = 420) -> None:
    """Embed an ECharts chart from the given option dict (loaded via CDN)."""
    # Escape "</" so a label containing "</script>" can't break out of the tag.
    payload = json.dumps(option).replace("</", "<\\/")
    html = f"""
    <div id="c" style="width:100%;height:{height}px;"></div>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
    <script>
      var chart = echarts.init(document.getElementById('c'));
      chart.setOption({payload});
      window.addEventListener('resize', function() {{ chart.resize(); }});
      // Re-measure once layout settles, so the chart fills the iframe width.
      setTimeout(function() {{ chart.resize(); }}, 200);
    </script>
    """
    st.iframe(html, height=height + 10)


def trend_chart(financials, lab, unit):
    """Grouped bars: revenue and net income over the years."""
    years = [r.get("year", "") for r in financials]
    title = lab["trend"] + (f" ({unit})" if unit else "")
    return {
        "backgroundColor": SURFACE,
        "title": {"text": title, "textStyle": {"color": INK, "fontSize": 14}},
        "tooltip": {"trigger": "axis"},
        "legend": {"data": [lab["revenue"], lab["net_income"]], "bottom": 0,
                   "textStyle": {"color": INK2}},
        "grid": {"left": "3%", "right": "4%", "bottom": "14%", "top": "20%",
                 "containLabel": True},
        "xAxis": {"type": "category", "data": years,
                  "axisLabel": {"color": MUTED},
                  "axisLine": {"lineStyle": {"color": AXIS}}},
        "yAxis": {"type": "value", "axisLabel": {"color": MUTED},
                  "splitLine": {"lineStyle": {"color": GRID}}},
        "series": [
            {"name": lab["revenue"], "type": "bar",
             "data": [r.get("revenue") for r in financials],
             "itemStyle": {"color": S_BLUE, "borderRadius": [4, 4, 0, 0]}},
            {"name": lab["net_income"], "type": "bar",
             "data": [r.get("net_income") for r in financials],
             "itemStyle": {"color": S_ORANGE, "borderRadius": [4, 4, 0, 0]}},
        ],
    }


def segment_chart(segments, lab):
    """Donut: revenue by business segment."""
    return {
        "backgroundColor": SURFACE,
        "title": {"text": lab["segments"], "textStyle": {"color": INK, "fontSize": 14}},
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "legend": {"bottom": 0, "textStyle": {"color": INK2}},
        "color": CATEGORICAL,
        "series": [{
            "type": "pie", "radius": ["40%", "68%"], "center": ["50%", "46%"],
            "avoidLabelOverlap": True,
            "label": {"show": True, "formatter": "{b}\n{d}%", "color": INK},
            "data": [{"value": s.get("revenue"), "name": s.get("name", "")}
                     for s in segments],
        }],
    }


def profit_donut(net_margin, lab):
    """Donut: profit vs the rest of each revenue dollar."""
    rest = round(100 - net_margin, 1)
    return {
        "backgroundColor": SURFACE,
        "title": {"text": lab["profit_share"],
                  "textStyle": {"color": INK, "fontSize": 14}},
        "tooltip": {"trigger": "item", "formatter": "{b}: {c}%"},
        "series": [{
            "type": "pie", "radius": ["50%", "72%"], "center": ["50%", "52%"],
            "label": {"show": True, "formatter": "{b}\n{c}%", "color": INK},
            "data": [
                {"value": net_margin, "name": lab["profit_label"],
                 "itemStyle": {"color": S_BLUE}},
                {"value": rest, "name": lab["other_label"],
                 "itemStyle": {"color": GRID}},
            ],
        }],
    }


def two_bar_chart(title, cats, values, colors, unit=""):
    """A small 2-bar chart (cash vs debt, operating vs free cash flow)."""
    data = [{"value": v, "itemStyle": {"color": c}}
            for v, c in zip(values, colors)]
    return {
        "backgroundColor": SURFACE,
        "title": {"text": title + (f" ({unit})" if unit else ""),
                  "textStyle": {"color": INK, "fontSize": 14}},
        "tooltip": {"trigger": "axis"},
        "grid": {"left": "3%", "right": "4%", "bottom": "6%", "top": "20%",
                 "containLabel": True},
        "xAxis": {"type": "category", "data": cats,
                  "axisLabel": {"color": MUTED},
                  "axisLine": {"lineStyle": {"color": AXIS}}},
        "yAxis": {"type": "value", "axisLabel": {"color": MUTED},
                  "splitLine": {"lineStyle": {"color": GRID}}},
        "series": [{
            "type": "bar", "barWidth": "45%", "data": data,
            "itemStyle": {"borderRadius": [4, 4, 0, 0]},
            "label": {"show": True, "position": "top", "color": INK2},
        }],
    }
