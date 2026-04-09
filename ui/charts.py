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
    calculate_stillhalter_macd, find_sr_levels_with_strength,
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
    "bg": "#000000",          # Reines Schwarz (Dark Mode)
    "bg_light": "#ffffff",    # Reines Weiß (Light Mode)
    "grid": "#141414",        # Sehr dunkles Gitter
    "grid_light": "#e8e8e8",
    "text": "#c8c8c8",
    "text_light": "#222222",
    "sma50": "#ff9800",
    "sma200": "#2196f3",
    "channel_upper": "rgba(100,200,100,0.25)",
    "channel_lower": "rgba(200,100,100,0.25)",
    "support": "#4caf50",
    "resistance": "#f44336",
    "top_put": "#22c55e",       # Top-Put Strike im Chart
    "top_call": "#f59e0b",      # Top-Call Strike im Chart
    "top_strangle": "#a78bfa",  # Strangle Strikes
}


def render_stock_chart(
    df: pd.DataFrame,
    ticker: str,
    tech_signal: Optional[TechSignal] = None,
    show_indicators: bool = True,
    height: int = 700,
    trend_mode: str = "Very Tight",
    top_options: Optional[pd.DataFrame] = None,   # Top-Optionen → Strikes im Chart
    dark_mode: bool = True,
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

    # ── Farben nach Dark/Light Mode ────────────────────────────────────────
    bg     = COLORS["bg"]       if dark_mode else COLORS["bg_light"]
    grid   = COLORS["grid"]     if dark_mode else COLORS["grid_light"]
    txt    = COLORS["text"]     if dark_mode else COLORS["text_light"]
    axis_c = "#2a2a2a"          if dark_mode else "#cccccc"

    rows = 4 if show_indicators else 2
    row_heights = [0.5, 0.15, 0.175, 0.175] if show_indicators else [0.7, 0.3]
    subplot_titles = [ticker, "Volumen", "Stillhalter MACD Pro", "Dual Stochastik"] \
                     if show_indicators else [ticker, "Volumen"]

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

    # ── Support / Resistance (multi-method mit Stärke-Visualisierung) ─────
    # Neuberechnung mit Volume und mehr Levels
    vol_for_sr = df["Volume"] if "Volume" in df.columns else None
    sr_levels  = find_sr_levels_with_strength(
        high, low, close, volume=vol_for_sr, lookback=250, n_levels=8
    )

    # Fallback auf TechSignal-Levels wenn keine gefunden
    if not sr_levels and tech_signal:
        for level in tech_signal.support_levels:
            sr_levels.append(type("SR", (), {
                "price": level, "level_type": "support",
                "strength": 2, "label": f"🟢 S ${level:.2f}", "distance_pct": 0
            })())
        for level in tech_signal.resistance_levels:
            sr_levels.append(type("SR", (), {
                "price": level, "level_type": "resistance",
                "strength": 2, "label": f"🔴 R ${level:.2f}", "distance_pct": 0
            })())

    for sr in sr_levels:
        is_sup  = sr.level_type == "support"
        color   = COLORS["support"] if is_sup else COLORS["resistance"]
        opacity = 0.3 + min(sr.strength, 5) * 0.12   # Stärke → Deckkraft 0.42–0.90

        # Liniendicke nach Stärke: 1 Stern = dünn, 5 Sterne = dick
        lw = 0.8 + sr.strength * 0.25   # 1.05 – 2.05px

        # Linienstil: Stark = durchgezogen, Schwach = gepunktet
        dash = "solid" if sr.strength >= 4 else "dot" if sr.strength <= 2 else "dash"

        # Leichte Hintergrundzone für starke Levels (≥ 3 Sterne)
        if sr.strength >= 3:
            zone_h = float(close.iloc[-1]) * 0.004   # ±0.4% Zone
            fill_c = f"rgba(76,175,80,0.04)" if is_sup else f"rgba(244,67,54,0.04)"
            fig.add_hrect(
                y0=sr.price - zone_h,
                y1=sr.price + zone_h,
                fillcolor=fill_c,
                line_width=0,
                row=1, col=1,
            )

        # Linie
        fig.add_hline(
            y=sr.price,
            line_dash=dash,
            line_color=f"rgba({76 if is_sup else 244},{175 if is_sup else 67},{80 if is_sup else 54},{opacity:.2f})",
            line_width=lw,
            annotation=dict(
                text=f"  {sr.label}",
                font=dict(
                    color=color, size=9 + sr.strength,  # Stärke → Schriftgröße
                    family="RedRose, Inter, sans-serif",
                ),
                bgcolor="rgba(0,0,0,0.55)" if dark_mode else "rgba(255,255,255,0.80)",
                bordercolor=color,
                borderwidth=1,
                borderpad=3,
            ),
            annotation_position="right",
            row=1, col=1,
        )

    # ── Top-3 Optionen: Strikes im Chart ─────────────────────────────────
    if top_options is not None and not top_options.empty and "Strike" in top_options.columns:
        top3 = top_options.head(3)
        rank_labels = ["🥇", "🥈", "🥉"]
        for rank, (_, row_opt) in enumerate(top3.iterrows()):
            strike = float(row_opt.get("Strike", 0))
            if strike <= 0:
                continue
            # Farbe abhängig von Optionstyp
            opt_t = str(row_opt.get("Typ", "")).lower()
            if "call" in opt_t:
                lc = COLORS["top_call"]
            elif "strangle" in opt_t:
                lc = COLORS["top_strangle"]
            else:
                lc = COLORS["top_put"]

            prem  = row_opt.get("Prämie",     "")
            expiry = row_opt.get("Verfall",    "")
            dte   = row_opt.get("DTE",         "")
            crv   = row_opt.get("⭐ CRV", row_opt.get("CRV Score", ""))
            ann   = row_opt.get("Rendite ann. %", row_opt.get("ROI ann. %", ""))

            label_txt = (
                f"  {rank_labels[rank]} Strike ${strike:.2f}"
                + (f" | ${float(prem):.2f}" if prem != "" else "")
                + (f" | {expiry}" if expiry else "")
                + (f" | {dte}d" if dte != "" else "")
                + (f" | CRV {float(crv):.1f}" if crv != "" else "")
                + (f" | {float(ann):.1f}% ann." if ann != "" else "")
            )
            fig.add_hline(
                y=strike,
                line_dash="solid" if rank == 0 else "dash",
                line_color=lc,
                line_width=1.5 if rank == 0 else 1.0,
                annotation=dict(
                    text=label_txt,
                    font=dict(color=lc, size=10),
                    bgcolor="rgba(0,0,0,0.6)" if dark_mode else "rgba(255,255,255,0.8)",
                    bordercolor=lc,
                    borderwidth=1,
                ),
                annotation_position="left",
                row=1, col=1,
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
        # ── Stillhalter MACD Pro (10/35/5) ────────────────────────────────
        sc_macd = calculate_stillhalter_macd(close, high, low)

        if sc_macd.hist is not None and sc_macd.hist_colors:
            # 4-Farb-Histogramm (exakt wie Pine Script)
            fig.add_trace(
                go.Bar(
                    x=dates, y=sc_macd.hist,
                    name="SC MACD Hist.",
                    marker_color=sc_macd.hist_colors,
                    showlegend=False,
                    hovertemplate="%{y:.4f}",
                ),
                row=3, col=1,
            )
            # MACD-Linie (hell blau)
            fig.add_trace(
                go.Scatter(x=dates, y=sc_macd.macd,
                           name="SC MACD",
                           line=dict(color="#4fc3f7", width=1.5),
                           hovertemplate="%{y:.4f}"),
                row=3, col=1,
            )
            # Signal-Linie (orange)
            fig.add_trace(
                go.Scatter(x=dates, y=sc_macd.signal,
                           name="SC Signal",
                           line=dict(color="#ff8a65", width=1.5),
                           hovertemplate="%{y:.4f}"),
                row=3, col=1,
            )

            # Z-Score Punkte (nur bei |z|>2, 6-stufige Farben)
            if sc_macd.z_score is not None and sc_macd.z_colors:
                z_x, z_y, z_c = [], [], []
                for i, (zc, zh) in enumerate(
                    zip(sc_macd.z_colors, sc_macd.hist.values)
                ):
                    if zc is not None and i < len(dates):
                        z_x.append(dates.iloc[i] if hasattr(dates, "iloc") else dates[i])
                        z_y.append(zh)
                        z_c.append(zc)
                if z_x:
                    fig.add_trace(
                        go.Scatter(
                            x=z_x, y=z_y, mode="markers",
                            name="Z-Score",
                            marker=dict(symbol="circle", size=6, color=z_c,
                                        line=dict(width=0)),
                            hovertemplate="Z: %{text}<extra>Z-Score</extra>",
                            text=[f"{float(sc_macd.z_score.iloc[i]):.2f}"
                                  for i in range(len(sc_macd.hist))
                                  if sc_macd.z_colors[i] is not None],
                        ),
                        row=3, col=1,
                    )

            # ADX Signal-Marker (Dreiecke auf Crossover-Kerzen)
            def _adx_markers(idxs, sym, col, nm):
                if not idxs:
                    return
                xs = [dates.iloc[i] if hasattr(dates, "iloc") else dates[i]
                      for i in idxs if i < len(dates)]
                ys = [float(sc_macd.hist.iloc[i]) for i in idxs if i < len(sc_macd.hist)]
                if xs:
                    fig.add_trace(
                        go.Scatter(
                            x=xs, y=ys, mode="markers",
                            marker=dict(symbol=sym, size=9, color=col),
                            name=nm, showlegend=True,
                        ),
                        row=3, col=1,
                    )

            _adx_markers(sc_macd.bull_cross_20_idx, "triangle-up",   "#81C784", "Bull ADX>20")
            _adx_markers(sc_macd.bear_cross_20_idx, "triangle-down", "#E57373", "Bear ADX>20")
            _adx_markers(sc_macd.bull_cross_40_idx, "triangle-up",   "#1B5E20", "Bull ADX>40 ⭐")
            _adx_markers(sc_macd.bear_cross_40_idx, "triangle-down", "#B71C1C", "Bear ADX>40 ⭐")

            # Nulllinie
            fig.add_hline(y=0, line_dash="dot",
                          line_color="rgba(255,255,255,0.2)",
                          line_width=1, row=3, col=1)

        # ── Dual Stochastic (Stillhalter AI App) ────────────────────────
        # Schnell (14,3,3): blau/%K, orange/%D
        from analysis.technicals import calculate_dual_stochastic
        ds = calculate_dual_stochastic(high, low, close, include_series=True)

        if ds.fast_k_series is not None:
            # Schnelle Stochastik
            fig.add_trace(
                go.Scatter(x=dates, y=ds.fast_k_series, name="Stillhalter Dual Stochastik (Schnell)",
                           line=dict(color="#4fc3f7", width=2),
                           hovertemplate="%{y:.1f}"),
                row=4, col=1
            )
            fig.add_trace(
                go.Scatter(x=dates, y=ds.fast_d_series, name="Schnell %D",
                           line=dict(color="#ff8a65", width=1),
                           hovertemplate="%{y:.1f}"),
                row=4, col=1
            )

        if ds.slow_k_series is not None:
            # Langsame Stochastik (35,10,5): dunkelgrün/%K, hellgelb/%D
            fig.add_trace(
                go.Scatter(x=dates, y=ds.slow_k_series, name="Stillhalter Dual Stochastik (Langsam)",
                           line=dict(color="#007700", width=2),
                           hovertemplate="%{y:.1f}"),
                row=4, col=1
            )
            fig.add_trace(
                go.Scatter(x=dates, y=ds.slow_d_series, name="Langsam %D",
                           line=dict(color="#ffff99", width=1),
                           hovertemplate="%{y:.1f}"),
                row=4, col=1
            )

        # Signale als Marker (nur aktuelle Signale auf letzter Kerze)
        last_date = dates.iloc[-1] if hasattr(dates, 'iloc') else dates[-1]
        _mk = lambda y, sym, col, nm: go.Scatter(
            x=[last_date], y=[y], mode="markers",
            marker=dict(symbol=sym, size=10, color=col),
            name=nm, showlegend=True
        )
        if ds.fast_ready_buy:
            fig.add_trace(_mk(5, "triangle-up", "#00e676", "🟢 Ready Buy Schnell"), row=4, col=1)
        if ds.fast_ready_sell:
            fig.add_trace(_mk(95, "triangle-down", "#ef4444", "🔴 Ready Sell Schnell"), row=4, col=1)
        if ds.slow_ready_buy:
            fig.add_trace(_mk(8, "triangle-up", "#69f0ae", "🟢 Ready Buy Langsam"), row=4, col=1)
        if ds.slow_ready_sell:
            fig.add_trace(_mk(92, "triangle-down", "#ff8a65", "🔴 Ready Sell Langsam"), row=4, col=1)

        # Überkauft/Überverkauft-Zonen
        fig.add_hline(y=80, line_dash="solid", line_color="rgba(244,67,54,0.6)",
                      line_width=1, row=4, col=1)
        fig.add_hline(y=20, line_dash="solid", line_color="rgba(76,175,80,0.6)",
                      line_width=1, row=4, col=1)
        fig.add_hrect(y0=80, y1=100, fillcolor="rgba(244,67,54,0.06)", row=4, col=1)
        fig.add_hrect(y0=0,  y1=20,  fillcolor="rgba(76,175,80,0.06)",  row=4, col=1)

    # ── Layout ────────────────────────────────────────────────────────────
    fig.update_layout(
        height=height,
        paper_bgcolor=bg,
        plot_bgcolor=bg,
        font=dict(color=txt, family="RedRose, Inter, sans-serif", size=12),
        xaxis_rangeslider_visible=False,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
            bgcolor="rgba(0,0,0,0.4)" if dark_mode else "rgba(255,255,255,0.7)",
            font=dict(size=10, color=txt),
            bordercolor=axis_c, borderwidth=1,
        ),
        margin=dict(l=10, r=10, t=40, b=10),
        hovermode="x unified",
    )

    # Achsen-Styling
    axis_style = dict(
        gridcolor=grid,
        gridwidth=0.5,
        showgrid=True,
        zeroline=False,
        tickfont=dict(size=10, color=txt),
        linecolor=axis_c,
        linewidth=1,
    )
    for i in range(1, rows + 1):
        fig.update_xaxes(axis_style, row=i, col=1)
        fig.update_yaxes(axis_style, row=i, col=1)

    fig.update_yaxes(title_text="Preis", title_font=dict(color=txt), row=1, col=1)
    fig.update_yaxes(title_text="Vol",   title_font=dict(color=txt), row=2, col=1)
    if show_indicators:
        fig.update_yaxes(title_text="MACD",  title_font=dict(color=txt), row=3, col=1)
        fig.update_yaxes(title_text="Stoch", title_font=dict(color=txt), row=4, col=1,
                         range=[0, 100])

    # Subplot-Titel Farbe
    for ann in fig.layout.annotations:
        ann.font.color = txt

    return fig


def render_payoff_diagram(
    current_price: float,
    strike: float,
    premium: float,
    option_type: str = "put",
    ticker: str = "",
    dte: int = 30,
) -> go.Figure:
    """
    Payoff-Diagramm für eine Short Option (Put oder Call).
    Zeigt farbige Gewinn-/Verlust-Zonen, Break-Even, Szenarien.
    """
    n_pts = 400
    lo = current_price * 0.65
    hi = current_price * 1.35
    price_range = np.linspace(lo, hi, n_pts)

    if option_type == "put":
        payoff = np.where(
            price_range >= strike,
            premium * 100,
            (price_range - strike + premium) * 100,
        )
        breakeven = strike - premium
        max_profit = premium * 100
        max_loss_price = lo
        max_loss = (max_loss_price - strike + premium) * 100
        strat_label = "Short Put"
    else:
        payoff = np.where(
            price_range <= strike,
            premium * 100,
            (strike - price_range + premium) * 100,
        )
        breakeven = strike + premium
        max_profit = premium * 100
        max_loss_price = hi
        max_loss = (strike - max_loss_price + premium) * 100
        strat_label = "Short Call"

    # Gewinn-Zone (grün) und Verlust-Zone (rot) separat
    profit_mask = payoff >= 0
    loss_mask   = payoff < 0

    fig = go.Figure()

    # Farbige Hintergrundzonen
    if option_type == "put":
        # Grüne Zone rechts vom Strike (Profit-Bereich)
        fig.add_vrect(x0=breakeven, x1=hi,
                      fillcolor="rgba(34,197,94,0.05)", line_width=0)
        # Rote Zone links vom Breakeven
        fig.add_vrect(x0=lo, x1=breakeven,
                      fillcolor="rgba(239,68,68,0.05)", line_width=0)
    else:
        fig.add_vrect(x0=lo, x1=breakeven,
                      fillcolor="rgba(34,197,94,0.05)", line_width=0)
        fig.add_vrect(x0=breakeven, x1=hi,
                      fillcolor="rgba(239,68,68,0.05)", line_width=0)

    # Gewinn-Linie (grün)
    y_profit = np.where(profit_mask, payoff, np.nan)
    fig.add_trace(go.Scatter(
        x=price_range, y=y_profit,
        mode="lines", fill="tozeroy",
        fillcolor="rgba(34,197,94,0.18)",
        line=dict(color="#22c55e", width=2.5),
        name="Gewinn",
        hovertemplate="Kurs: $%{x:.2f}<br>P&L: $%{y:.0f}<extra>Gewinn</extra>",
    ))

    # Verlust-Linie (rot)
    y_loss = np.where(loss_mask, payoff, np.nan)
    fig.add_trace(go.Scatter(
        x=price_range, y=y_loss,
        mode="lines", fill="tozeroy",
        fillcolor="rgba(239,68,68,0.18)",
        line=dict(color="#ef4444", width=2.5),
        name="Verlust",
        hovertemplate="Kurs: $%{x:.2f}<br>P&L: $%{y:.0f}<extra>Verlust</extra>",
    ))

    # Nulllinie
    fig.add_hline(y=0, line_color="#333", line_width=1)

    # Break-Even Linie (prominent)
    fig.add_vline(
        x=breakeven, line_dash="dash", line_color="#f59e0b", line_width=2,
        annotation_text=f"⚡ Break-Even ${breakeven:.2f}",
        annotation_font_color="#f59e0b", annotation_font_size=11,
        annotation_position="top",
    )

    # Aktueller Kurs
    fig.add_vline(
        x=current_price, line_dash="dot", line_color="#888", line_width=1.5,
        annotation_text=f"Kurs ${current_price:.2f}",
        annotation_font_color="#888", annotation_font_size=10,
        annotation_position="bottom right",
    )

    # Strike
    fig.add_vline(
        x=strike, line_dash="dot", line_color="#d4a843", line_width=1.5,
        annotation_text=f"Strike ${strike:.2f}",
        annotation_font_color="#d4a843", annotation_font_size=10,
        annotation_position="top left",
    )

    # Szenarien: -10%, -5%, +5%, +10%
    scenarios = [
        (current_price * 0.90, "-10%"),
        (current_price * 0.95, "-5%"),
        (current_price * 1.05, "+5%"),
        (current_price * 1.10, "+10%"),
    ]
    for sc_price, sc_label in scenarios:
        if lo < sc_price < hi:
            if option_type == "put":
                sc_pnl = premium * 100 if sc_price >= strike else (sc_price - strike + premium) * 100
            else:
                sc_pnl = premium * 100 if sc_price <= strike else (strike - sc_price + premium) * 100
            sc_color = "#22c55e" if sc_pnl >= 0 else "#ef4444"
            fig.add_annotation(
                x=sc_price, y=sc_pnl,
                text=f"{sc_label}<br>${sc_pnl:+.0f}",
                showarrow=True, arrowhead=2, arrowcolor=sc_color,
                arrowsize=0.8, arrowwidth=1,
                font=dict(size=9, color=sc_color),
                bgcolor="rgba(12,12,12,0.8)",
                bordercolor=sc_color, borderwidth=1,
            )

    # OTM-Puffer-Annotation
    otm_pct = abs(current_price - strike) / current_price * 100
    be_pct  = abs(current_price - breakeven) / current_price * 100
    fig.add_annotation(
        x=0.02, y=0.97, xref="paper", yref="paper",
        text=(f"<b style='color:#d4a843'>Max. Gewinn:</b> ${max_profit:.0f}<br>"
              f"<b style='color:#888'>OTM Puffer:</b> {otm_pct:.1f}%<br>"
              f"<b style='color:#f59e0b'>BE-Puffer:</b> {be_pct:.1f}%<br>"
              f"<b style='color:#888'>Prämie/Tag:</b> ${premium/max(dte,1)*100:.2f}"),
        showarrow=False, align="left",
        font=dict(size=10, color="#888"),
        bgcolor="rgba(20,20,20,0.85)",
        bordercolor="#2a2a2a", borderwidth=1,
        borderpad=8,
    )

    fig.update_layout(
        title=dict(
            text=f"{strat_label} · {ticker} · Strike ${strike:.2f} · Prämie ${premium:.2f}",
            font=dict(size=13, color="#ccc"),
        ),
        height=380,
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["bg"],
        font=dict(color=COLORS["text"], family="RedRose, sans-serif"),
        xaxis=dict(
            title=dict(text="Aktienkurs bei Verfall ($)", font=dict(color="#666")),
            gridcolor=COLORS["grid"], zeroline=False,
            tickformat="$,.2f",
        ),
        yaxis=dict(
            title=dict(text="P&L pro Kontrakt ($)", font=dict(color="#666")),
            gridcolor=COLORS["grid"], zeroline=False,
            tickformat="$,.0f",
        ),
        legend=dict(
            orientation="h", y=-0.15,
            font=dict(size=10, color="#666"),
        ),
        margin=dict(l=10, r=10, t=50, b=60),
        hovermode="x unified",
    )

    return fig


def render_option_mini_chart(
    hist: pd.DataFrame,
    ticker: str,
    current_price: float,
    strike: float,
    premium: float,
    dte: int,
    iv_pct: float,
    option_type: str = "put",
    expiry_date: str = "",
) -> go.Figure:
    """
    Kompakter Inline-Chart: Kurshistorie + Options-Overlay.
    Zeigt Profit/Warning/Loss-Zonen, Strike, Break-Even und IV-Kegel.
    """
    df = hist.tail(90) if len(hist) > 90 else hist
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Keine Kursdaten verfügbar", x=0.5, y=0.5,
                           xref="paper", yref="paper", showarrow=False,
                           font=dict(color="#555"))
        fig.update_layout(height=240, paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)")
        return fig

    close  = df["Close"].values
    dates  = list(df.index)

    # Break-Even je Optionstyp
    if option_type == "put":
        breakeven = round(strike - premium, 2)
        otm_side  = current_price >= strike   # Kurs ist OTM → im Profit-Bereich
    else:
        breakeven = round(strike + premium, 2)
        otm_side  = current_price <= strike

    # IV-Kegel-Endpunkte
    sigma_move = current_price * (iv_pct / 100) * np.sqrt(max(dte, 1) / 365)
    iv_upper   = current_price + sigma_move
    iv_lower   = current_price - sigma_move

    # Expiry-Datum für Kegel-Projektion
    last_date = dates[-1]
    if isinstance(last_date, pd.Timestamp):
        expiry_dt = last_date + pd.Timedelta(days=dte)
    else:
        expiry_dt = pd.Timestamp.now() + pd.Timedelta(days=dte)

    # Y-Achsen-Bounds
    all_prices = list(close) + [iv_upper, iv_lower, strike, breakeven]
    y_pad = (max(all_prices) - min(all_prices)) * 0.08 or current_price * 0.04
    y_min = min(all_prices) - y_pad
    y_max = max(all_prices) + y_pad

    fig = go.Figure()

    # ── Farbzonen (horizontal) ─────────────────────────────────────────────
    if option_type == "put":
        fig.add_hrect(y0=strike,    y1=y_max,
                      fillcolor="rgba(34,197,94,0.07)",  line_width=0)
        fig.add_hrect(y0=breakeven, y1=strike,
                      fillcolor="rgba(234,179,8,0.07)",  line_width=0)
        fig.add_hrect(y0=y_min,     y1=breakeven,
                      fillcolor="rgba(239,68,68,0.07)",  line_width=0)
    else:
        fig.add_hrect(y0=y_min,     y1=strike,
                      fillcolor="rgba(34,197,94,0.07)",  line_width=0)
        fig.add_hrect(y0=strike,    y1=breakeven,
                      fillcolor="rgba(234,179,8,0.07)",  line_width=0)
        fig.add_hrect(y0=breakeven, y1=y_max,
                      fillcolor="rgba(239,68,68,0.07)",  line_width=0)

    # Zonen-Labels (rechts außen)
    if option_type == "put":
        _zone_lbls = [
            ("🟢 Max Profit", max(y_max - y_pad * 0.5, strike + y_pad * 0.3), "#22c55e"),
            ("⚠️ Recovery",   (strike + breakeven) / 2,                        "#f59e0b"),
            ("🔴 Verlust",    min(y_min + y_pad * 0.5, breakeven - y_pad * 0.3), "#ef4444"),
        ]
    else:
        _zone_lbls = [
            ("🟢 Max Profit", min(y_min + y_pad * 0.5, strike - y_pad * 0.3), "#22c55e"),
            ("⚠️ Recovery",   (strike + breakeven) / 2,                        "#f59e0b"),
            ("🔴 Verlust",    max(y_max - y_pad * 0.5, breakeven + y_pad * 0.3), "#ef4444"),
        ]
    for lbl, y_pos, col in _zone_lbls:
        fig.add_annotation(x=1.01, y=y_pos, xref="paper", yref="y",
                           text=lbl, showarrow=False, xanchor="left",
                           font=dict(size=8, color=col))

    # ── IV-Kegel (Projektion in die Zukunft) ──────────────────────────────
    cone_x = [last_date, expiry_dt,  expiry_dt, last_date]
    cone_y = [current_price, iv_upper, iv_lower, current_price]
    fig.add_trace(go.Scatter(
        x=cone_x, y=cone_y,
        fill="toself",
        fillcolor="rgba(59,130,246,0.09)",
        line=dict(color="rgba(59,130,246,0.25)", width=1, dash="dot"),
        name=f"IV-Kegel ±${sigma_move:.1f} ({dte}d)",
        hoverinfo="skip", showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=[last_date, expiry_dt], y=[current_price, iv_upper],
        mode="lines", line=dict(color="rgba(59,130,246,0.35)", width=1, dash="dot"),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=[last_date, expiry_dt], y=[current_price, iv_lower],
        mode="lines", line=dict(color="rgba(59,130,246,0.35)", width=1, dash="dot"),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_annotation(x=expiry_dt, y=iv_upper,
                       text=f"+1σ ${iv_upper:.0f}", showarrow=False,
                       xanchor="left", font=dict(size=8, color="#3b82f6"))
    fig.add_annotation(x=expiry_dt, y=iv_lower,
                       text=f"-1σ ${iv_lower:.0f}", showarrow=False,
                       xanchor="left", font=dict(size=8, color="#3b82f6"))

    # ── Kurshistorie ──────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=dates, y=close,
        mode="lines",
        line=dict(color="#9ca3af", width=1.5),
        name=ticker,
        hovertemplate="%{x|%d.%m.%y}: <b>$%{y:.2f}</b><extra>" + ticker + "</extra>",
    ))
    # Aktueller Kurs (Marker)
    status_icon = "✅" if otm_side else "⚠️"
    fig.add_trace(go.Scatter(
        x=[last_date], y=[current_price],
        mode="markers",
        marker=dict(color="#d4a843", size=9, symbol="circle",
                    line=dict(color="#fff", width=1)),
        name=f"{status_icon} Kurs ${current_price:.2f}",
        hovertemplate=f"Aktuell: <b>${current_price:.2f}</b><extra>Kurs</extra>",
    ))

    # ── Horizontale Linien ────────────────────────────────────────────────
    fig.add_hline(
        y=strike, line=dict(color="#3b82f6", dash="dash", width=1.8),
        annotation_text=f" Strike ${strike:.2f}",
        annotation_font_color="#3b82f6", annotation_font_size=10,
        annotation_position="right",
    )
    fig.add_hline(
        y=breakeven, line=dict(color="#f59e0b", dash="dot", width=1.5),
        annotation_text=f" BE ${breakeven:.2f}",
        annotation_font_color="#f59e0b", annotation_font_size=10,
        annotation_position="right",
    )
    fig.add_hline(
        y=current_price, line=dict(color="#d4a843", dash="dot", width=1),
        annotation_text=f" Kurs ${current_price:.2f}",
        annotation_font_color="#d4a843", annotation_font_size=9,
        annotation_position="left",
    )

    # ── Kennzahlen-Badge (oben links) ─────────────────────────────────────
    otm_pct   = abs(current_price - strike)   / current_price * 100
    be_pct    = abs(current_price - breakeven) / current_price * 100
    ann_yield = (premium / max(strike, 1)) * (365 / max(dte, 1)) * 100
    fig.add_annotation(
        x=0.01, y=0.99, xref="paper", yref="paper",
        text=(f"<b>OTM:</b> {otm_pct:.1f}%  "
              f"<b>BE-Puffer:</b> {be_pct:.1f}%  "
              f"<b>Prämie/Tag:</b> ${premium / max(dte, 1) * 100:.2f}  "
              f"<b>Rendite ann.:</b> {ann_yield:.1f}%"),
        showarrow=False, xanchor="left", yanchor="top",
        font=dict(size=9, color="#9ca3af"),
        bgcolor="rgba(12,12,12,0.80)", borderpad=5,
        bordercolor="#2a2a2a", borderwidth=1,
    )

    # ── Layout ─────────────────────────────────────────────────────────────
    strat = "Short Put" if option_type == "put" else "Short Call"
    title = (f"{ticker} · {strat} · Strike ${strike:.2f}"
             f"{' · ' + expiry_date if expiry_date else ''}")
    fig.update_layout(
        height=260,
        title=dict(text=title, font=dict(size=11, color="#9ca3af"), x=0),
        margin=dict(l=10, r=120, t=36, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(12,12,12,0.6)",
        font=dict(color="#9ca3af", family="RedRose, Inter, sans-serif", size=10),
        xaxis=dict(
            gridcolor="#1e1e1e", zeroline=False, tickfont=dict(size=9),
            range=[dates[0],
                   expiry_dt + pd.Timedelta(days=max(dte // 8, 3))],
        ),
        yaxis=dict(
            gridcolor="#1e1e1e", zeroline=False,
            tickfont=dict(size=9), tickformat="$,.0f",
            range=[y_min, y_max],
        ),
        legend=dict(orientation="h", y=-0.20, x=0,
                    font=dict(size=8, color="#555"),
                    bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
    )
    return fig
