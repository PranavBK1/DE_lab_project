"""Plotly figure builders: the ONE place the chart style is defined.

Style: plotly_white, one accent colour for single-series charts, neutral grey
for "the rest", thin bars, light grid, axis titles always set, the chart title
states the question or the takeaway. Value labels in dark grey (never in the
bar colour), on every bar when there are at most 10 bars, otherwise only on
the highlighted / top bar. Hover shows the exact value and the count.
No dual axes, no pie charts, no rainbow colours.
"""
import plotly.graph_objects as go

ACCENT = "#2a78d6"
NEUTRAL = "#b8b7b0"
TEXT = "#3d3d3a"
GRID = "#ebebe7"
MAX_LABELLED_BARS = 10


def _style(fig, title, x_title, y_title, height):
    fig.update_layout(
        template="plotly_white",
        title={"text": title, "x": 0, "xanchor": "left", "font": {"size": 16, "color": TEXT}},
        font={"color": TEXT, "size": 13},
        margin={"l": 8, "r": 24, "t": 56, "b": 48},
        height=height,
        showlegend=False,
        bargap=0.45,                      # thin bars
        hoverlabel={"bgcolor": "white", "font_color": TEXT},
    )
    fig.update_xaxes(title_text=x_title, gridcolor=GRID, zeroline=False, automargin=True)
    fig.update_yaxes(title_text=y_title, gridcolor=GRID, zeroline=False, automargin=True)
    return fig


def _labels(text, highlight):
    """Value labels: all of them for <= 10 bars, else only the highlighted ones
    (or the first, i.e. the top bar)."""
    if text is None:
        return None
    if len(text) <= MAX_LABELLED_BARS:
        return list(text)
    keep = highlight if highlight is not None else [i == 0 for i in range(len(text))]
    return [t if k else "" for t, k in zip(text, keep)]


def hbar(labels, values, *, title, value_title, label_title="", text=None, hover=None,
         highlight=None, value_range=None):
    """Horizontal bars, first item at the top.

    labels / values: sequences in display order (largest first).
    text:      value label per bar (thinned out when there are > 10 bars).
    hover:     full hover text per bar (exact value + count).
    highlight: booleans; True bars get the accent colour, the rest grey.
               None = every bar in the accent colour.
    """
    labels, values = list(labels), list(values)
    colors = ACCENT if highlight is None else [ACCENT if h else NEUTRAL for h in highlight]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=colors,
        text=_labels(text, highlight), textposition="outside",
        textfont={"color": TEXT}, cliponaxis=False,
        hovertext=hover, hoverinfo="text" if hover is not None else "x+y",
    ))
    fig.update_yaxes(autorange="reversed", categoryorder="array", categoryarray=labels)
    if value_range is not None:
        fig.update_xaxes(range=value_range)
    height = 90 + 30 * len(labels)
    return _style(fig, title, value_title, label_title, max(height, 220))


def vbar(labels, values, *, title, x_title, y_title, text=None, hover=None, log_y=False,
         highlight=None):
    """Vertical bars in the given (category) order."""
    labels, values = [str(l) for l in labels], list(values)
    colors = ACCENT if highlight is None else [ACCENT if h else NEUTRAL for h in highlight]
    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=colors,
        text=_labels(text, highlight), textposition="outside",
        textfont={"color": TEXT}, cliponaxis=False,
        hovertext=hover, hoverinfo="text" if hover is not None else "x+y",
    ))
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=labels, showgrid=False)
    if log_y:
        fig.update_yaxes(type="log")
    return _style(fig, title, x_title, y_title + (" (log scale)" if log_y else ""), 380)
