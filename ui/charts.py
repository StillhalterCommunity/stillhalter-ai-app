"""
Chart-Komponenten für das Dashboard.
Candlestick mit Indikatoren, Options-Visualisierung.
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from typing import Optional
from analysis.technicals import (
    calculate_sma, calculate_ema, calculate_macd,
    calculate_stochastic, calculate_linear_regression_channel,
    TechSignal
)


def _add_stillhalter_trend_band(
    fig,
    close: pd.Series,
    dates,
    fast_len: int = 2,
    slow_len: int = 9,
    row: int = 1
) -> None:
    """
    Zeichnet das Stillhalter Trend Model Band auf den Chart.
    Grünes Band: Aufwärtstrend | Gelbes Band: Abwärtstrend
    Exakt wie TradingView fill(plotFast, plotSlow, color=bandColor).
    """
    from analysis.technicals import calculate_ema

    fast_ema = calculate_ema(close, fast_len)
    slow_ema = calculate_ema(close, slow_len)

    bull = (fast_ema.values > slow_ema.values)

    # Segmente finden (wo sich die Richtung ändert)
    if len(bull) == 0:
        return

    segments = []
    start_idx = 0
    current_bull = bool(bull[0])

    for i in range(1, len(bull)):
        if bool(bull[i]) != current_bull:
            segments.append((start_idx, i, current_bull))
            start_idx = i
            current_bull = bool(bull[i])
    segments.append((start_idx, len(bull), current_bull))

    fast_arr = fast_ema.values
    slow_arr = slow_ema.values
    dates_arr = list(dates)

    for s_start, s_end, is_bull in segments:
        fill_color = "rgba(0,119,0,0.18)" if is_bull else "rgba(220,200,0,0.13)"
        line_color = "rgba(0,150,0,0.5)" if is_bull else "rgba(200,180,0,0.4)"

        seg_dates = dates_arr[s_start:s_end]
        seg_fast  = list(fast_arr[s_start:s_end])
        seg_slow  = list(slow_arr[s_start:s_end])

        if len(seg_dates) < 2:
            continue

        # Fill-Polygon: fast vorwärts + slow rückwärts
        x_fill = seg_dates + seg_dates[::-1]
        y_fill = seg_fast + seg_slow[::-1]

        fig.add_trace(
            go.Scatter(
                x=x_fill, y=y_fill,
                fill="toself",
                fillcolor=fill_color,
                line=dict(width=0, color="rgba(0,0,0,0)"),
                showlegend=False,
                hoverinfo="skip",
                mode="lines",
            ),
            row=row, col=1
        )

    # FastLine und SlowLine (sehr dünn, fast unsichtbar — nur Referenz)
    fig.add_trace(
        go.Scatter(
            x=dates_arr, y=list(fast_arr),
            mode="lines",
            line=dict(color="rgba(0,180,0,0.35)", width=1),
            name="SC Trend Fast",
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=dates_arr, y=list(slow_arr),
            mode="lines",
            line=dict(color="rgba(200,180,0,0.35)", width=1),
            name="SC Trend Slow",
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row, col=1
    )


COLORS = {
    "bullish": "#26a69a",
    "bearish": "#ef5350",
    "neutral": "#90a4ae",
    "highlight": "#ffd700",
    "bg": "#1e1e1e",
    "grid": "#333333",
    "text": "#e0e0e0",
    "sma50": "#ff9800",
    "sma200": "#2196f3",
    "channel_upper": "rgba(100,200,100,0.3)",
    "channel_lower": "rgba(200,100,100,0.3)",
    "support": "#4caf50",
    "resistance": "#f44336",
}


def render_stock_chart(
    df: pd.DataFrame,
    ticker: str,
    tech_signal: Optional[TechSignal] = None,
    show_indicators: bool = True,
    height: int = 700,
    trend_mode: str = "Very Tight",
) -> go.Figure:
    """
    Vollständiger Aktienchart mit:
    - Candlestick + Volumen
    - SMA 50 / 200
    - Linearer Regressionskanal
    - Support/Resistance Linien
    - MACD Subplot
    - Stochastik Subplot
    """
    if df is None or df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Keine Daten verfügbar", x=0.5, y=0.5, showarrow=False)
        return fig

    rows = 4 if show_indicators else 2
    row_heights = [0.5, 0.15, 0.175, 0.175] if show_indicators else [0.7, 0.3]
    subplot_titles = [ticker, "Volumen", "MACD", "Stochastik"] if show_indicators else [ticker, "Volumen"]

    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
        subplot_titles=subplot_titles,
    )

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    opens = df["Open"]
    volume = df["Volume"]
    dates = df.index

    # ── Candlestick ────────────────────────────────────────────────────────
    fig.add_trace(
        go.Candlestick(
            x=dates,
            open=opens, high=high, low=low, close=close,
            name=ticker,
            increasing_line_color=COLORS["bullish"],
            decreasing_line_color=COLORS["bearish"],
            showlegend=False,
        ),
        row=1, col=1
    )

    # ── Stillhalter Trend Model Band ──────────────────────────────────────────
    from analysis.multi_timeframe import TREND_MODES
    _fast, _slow = TREND_MODES.get(trend_mode, (2, 9))
    _add_stillhalter_trend_band(fig, close, dates, _fast, _slow, row=1)

    # ── EMA 50 ────────────────────────────────────────────────────────────
    ema50 = calculate_ema(close, 50)
    fig.add_trace(
        go.Scatter(x=dates, y=ema50, name="EMA 50",
                   line=dict(color=COLORS["sma50"], width=1.5),
                   hovertemplate="%{y:.2f}"),
        row=1, col=1
    )

    # ── EMA 200 ───────────────────────────────────────────────────────────
    if len(close) >= 50:
        ema200 = calculate_ema(close, min(200, len(close)))
        fig.add_trace(
            go.Scatter(x=dates, y=ema200, name="EMA 200",
                       line=dict(color=COLORS["sma200"], width=1.5),
                       hovertemplate="%{y:.2f}"),
            row=1, col=1
        )

    # ── Regressionskanal ──────────────────────────────────────────────────
    if tech_signal and tech_signal.channel_upper:
        period = min(50, len(close))
        x_range = dates[-period:]
        y = close.iloc[-period:].values
        x_idx = np.arange(period)
        coeffs = np.polyfit(x_idx, y, 1)
        fitted = np.polyval(coeffs, x_idx)
        std = np.std(y - fitted)

        fig.add_trace(
            go.Scatter(x=list(x_range) + list(x_range[::-1]),
                       y=list(fitted + 2 * std) + list(fitted - 2 * std),
                       fill="toself", fillcolor="rgba(100,150,200,0.1)",
                       line=dict(color="rgba(100,150,200,0)", width=0),
                       name="Regressionskanal", showlegend=True,
                       hoverinfo="skip"),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=x_range, y=fitted + 2 * std,
                       line=dict(color="rgba(100,150,200,0.6)", width=1, dash="dash"),
                       showlegend=False, hoverinfo="skip"),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=x_range, y=fitted - 2 * std,
                       line=dict(color="rgba(100,150,200,0.6)", width=1, dash="dash"),
                       showlegend=False, hoverinfo="skip"),
            row=1, col=1
        )

    # ── Support / Resistance ──────────────────────────────────────────────
    if tech_signal:
        for level in tech_signal.support_levels:
            fig.add_hline(
                y=level, line_dash="dot",
                line_color=COLORS["support"], line_width=1,
                annotation_text=f"S {level:.1f}",
                annotation_position="left",
                row=1, col=1
            )
        for level in tech_signal.resistance_levels:
            fig.add_hline(
                y=level, line_dash="dot",
                line_color=COLORS["resistance"], line_width=1,
                annotation_text=f"R {level:.1f}",
                annotation_position="left",
                row=1, col=1
            )

    # ── Volumen ───────────────────────────────────────────────────────────
    colors_vol = [COLORS["bullish"] if c >= o else COLORS["bearish"]
                  for c, o in zip(close, opens)]
    fig.add_trace(
        go.Bar(x=dates, y=volume, name="Volumen",
               marker_color=colors_vol, showlegend=False,
               hovertemplate="%{y:,.0f}"),
        row=2, col=1
    )

    if show_indicators:
        # ── MACD ──────────────────────────────────────────────────────────
        macd_line, signal_line, histogram = calculate_macd(close)

        hist_colors = [COLORS["bullish"] if v >= 0 else COLORS["bearish"]
                       for v in histogram]
        fig.add_trace(
            go.Bar(x=dates, y=histogram, name="MACD Hist.",
                   marker_color=hist_colors, showlegend=False,
                   hovertemplate="%{y:.3f}"),
            row=3, col=1
        )
        fig.add_trace(
            go.Scatter(x=dates, y=macd_line, name="MACD",
                       line=dict(color="#4fc3f7", width=1.5),
                       hovertemplate="%{y:.3f}"),
            row=3, col=1
        )
        fig.add_trace(
            go.Scatter(x=dates, y=signal_line, name="Signal",
                       line=dict(color="#ff8a65", width=1.5),
                       hovertemplate="%{y:.3f}"),
            row=3, col=1
        )

        # ── Stochastik ────────────────────────────────────────────────────
        stoch_k, stoch_d = calculate_stochastic(high, low, close)
        fig.add_trace(
            go.Scatter(x=dates, y=stoch_k, name="%K",
                       line=dict(color="#4fc3f7", width=1.5),
                       hovertemplate="%{y:.1f}"),
            row=4, col=1
        )
        fig.add_trace(
            go.Scatter(x=dates, y=stoch_d, name="%D",
                       line=dict(color="#ff8a65", width=1.5),
                       hovertemplate="%{y:.1f}"),
            row=4, col=1
        )
        fig.add_hline(y=80, line_dash="dot", line_color="rgba(244,67,54,0.5)", row=4, col=1)
        fig.add_hline(y=20, line_dash="dot", line_color="rgba(76,175,80,0.5)", row=4, col=1)
        fig.add_hrect(y0=80, y1=100, fillcolor="rgba(244,67,54,0.05)", row=4, col=1)
        fig.add_hrect(y0=0, y1=20, fillcolor="rgba(76,175,80,0.05)", row=4, col=1)

    # ── Layout ────────────────────────────────────────────────────────────
    fig.update_layout(
        height=height,
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["bg"],
        font=dict(color=COLORS["text"], family="Inter, sans-serif", size=12),
        xaxis_rangeslider_visible=False,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
            bgcolor="rgba(0,0,0,0)", font=dict(size=11)
        ),
        margin=dict(l=10, r=10, t=40, b=10),
        hovermode="x unified",
    )

    # Achsen-Styling
    axis_style = dict(
        gridcolor=COLORS["grid"],
        gridwidth=0.5,
        showgrid=True,
        zeroline=False,
        tickfont=dict(size=10),
    )
    for i in range(1, rows + 1):
        fig.update_xaxes(axis_style, row=i, col=1)
        fig.update_yaxes(axis_style, row=i, col=1)

    fig.update_yaxes(title_text="Preis", row=1, col=1)
    fig.update_yaxes(title_text="Vol", row=2, col=1)
    if show_indicators:
        fig.update_yaxes(title_text="MACD", row=3, col=1)
        fig.update_yaxes(title_text="Stoch", row=4, col=1, range=[0, 100])

    return fig


def render_payoff_diagram(
    current_price: float,
    strike: float,
    premium: float,
    option_type: str = "put",
    ticker: str = "",
) -> go.Figure:
    """Payoff-Diagramm für eine einzelne Short Option Position."""

    price_range = np.linspace(current_price * 0.6, current_price * 1.4, 300)

    if option_type == "put":
        # Short Put: max. Gewinn = Prämie, Verlust ab Strike abwärts
        payoff = np.where(
            price_range >= strike,
            premium * 100,
            (price_range - strike + premium) * 100
        )
        breakeven = strike - premium
        title = f"Short Put | Strike {strike:.2f} | Prämie {premium:.2f}"
    else:
        # Short Call: max. Gewinn = Prämie, Verlust ab Strike aufwärts
        payoff = np.where(
            price_range <= strike,
            premium * 100,
            (strike - price_range + premium) * 100
        )
        breakeven = strike + premium
        title = f"Short Call | Strike {strike:.2f} | Prämie {premium:.2f}"

    colors_payoff = [COLORS["bullish"] if p >= 0 else COLORS["bearish"] for p in payoff]

    fig = go.Figure()

    # Nulllinie
    fig.add_hline(y=0, line_color=COLORS["neutral"], line_width=1)

    # Payoff-Kurve
    fig.add_trace(go.Scatter(
        x=price_range, y=payoff,
        mode="lines",
        line=dict(color=COLORS["highlight"], width=2),
        fill="tozeroy",
        fillcolor="rgba(38,166,154,0.15)",
        name="P&L",
        hovertemplate="Kurs: %{x:.2f}<br>P&L: $%{y:.0f}<extra></extra>",
    ))

    # Aktueller Kurs
    fig.add_vline(x=current_price, line_dash="dash",
                  line_color=COLORS["neutral"], line_width=1,
                  annotation_text=f"Kurs {current_price:.2f}",
                  annotation_position="top right")

    # Strike
    fig.add_vline(x=strike, line_dash="dot",
                  line_color=COLORS["highlight"], line_width=1.5,
                  annotation_text=f"Strike {strike:.2f}",
                  annotation_position="top left")

    # Breakeven
    fig.add_vline(x=breakeven, line_dash="dot",
                  line_color=COLORS["bearish"], line_width=1,
                  annotation_text=f"BE {breakeven:.2f}",
                  annotation_position="bottom right")

    fig.update_layout(
        title=title,
        height=350,
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["bg"],
        font=dict(color=COLORS["text"]),
        xaxis=dict(title="Aktienkurs bei Verfall", gridcolor=COLORS["grid"]),
        yaxis=dict(title="P&L ($)", gridcolor=COLORS["grid"]),
        showlegend=False,
        margin=dict(l=10, r=10, t=40, b=40),
    )

    return fig
