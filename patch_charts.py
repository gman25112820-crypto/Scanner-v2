with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# ============================================================
# RAGE ENGINE - Enhanced Markets/Charts Page
# ============================================================

charts_code = '''
def render_enhanced_markets():
    import yfinance as yf
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import pandas as pd
    import datetime

    st.markdown("""
    <div style="background:linear-gradient(135deg,rgba(255,69,0,0.15),rgba(0,0,0,0.3));
                border:1px solid rgba(255,69,0,0.3);border-radius:12px;padding:16px;margin-bottom:20px;">
        <span style="font-size:20px;font-weight:700;color:#fff;">📈 Market Charts</span>
        <span style="font-size:12px;color:#888;margin-left:12px;">Powered by RAGE Engine</span>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.text_input("Symbol", value="AAPL").upper()
    with col2:
        period = st.selectbox("Period", ["1mo","3mo","6mo","1y","2y","5y"], index=3)
    with col3:
        chart_type = st.selectbox("Chart Type", ["Candlestick","Line","Area"])

    show_ema20 = st.checkbox("EMA 20", value=True)
    show_ema50 = st.checkbox("EMA 50", value=True)
    show_ema200 = st.checkbox("EMA 200", value=True)

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period)
        info = ticker.info

        if df.empty:
            st.error(f"No data found for {symbol}")
            return

        # EMAs
        df['EMA20'] = df['Close'].ewm(span=20).mean()
        df['EMA50'] = df['Close'].ewm(span=50).mean()
        df['EMA200'] = df['Close'].ewm(span=200).mean()

        # Price change
        price_chg = ((df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0]) * 100
        current_price = df['Close'].iloc[-1]
        day_chg = ((df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2]) * 100

        # Metric cards
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Current Price", f"${current_price:.2f}", f"{day_chg:+.2f}%")
        c2.metric("Period Change", f"{price_chg:+.2f}%")
        c3.metric("Period High", f"${df['High'].max():.2f}")
        c4.metric("Period Low", f"${df['Low'].min():.2f}")

        # Build chart
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                           vertical_spacing=0.03, row_heights=[0.75, 0.25])

        if chart_type == "Candlestick":
            fig.add_trace(go.Candlestick(
                x=df.index, open=df['Open'], high=df['High'],
                low=df['Low'], close=df['Close'], name=symbol,
                increasing_line_color='#00e676', decreasing_line_color='#ff3d00'
            ), row=1, col=1)
        elif chart_type == "Line":
            fig.add_trace(go.Scatter(
                x=df.index, y=df['Close'], name=symbol,
                line=dict(color='#00e5ff', width=2)
            ), row=1, col=1)
        else:  # Area
            fig.add_trace(go.Scatter(
                x=df.index, y=df['Close'], name=symbol,
                fill='tozeroy', line=dict(color='#ff4500', width=2),
                fillcolor='rgba(255,69,0,0.15)'
            ), row=1, col=1)

        # EMAs
        if show_ema20:
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA20'], name='EMA 20',
                line=dict(color='#ffeb3b', width=1, dash='dot')), row=1, col=1)
        if show_ema50:
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA50'], name='EMA 50',
                line=dict(color='#ff9800', width=1, dash='dot')), row=1, col=1)
        if show_ema200:
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA200'], name='EMA 200',
                line=dict(color='#f44336', width=1, dash='dot')), row=1, col=1)

        # Volume
        colors = ['#00e676' if c >= o else '#ff3d00'
                 for c, o in zip(df['Close'], df['Open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='Volume',
                            marker_color=colors, opacity=0.7), row=2, col=1)

        fig.update_layout(
            template='plotly_dark',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0.3)',
            font=dict(color='#fff'),
            title=dict(text=f"{symbol} — {period.upper()} Chart", font=dict(size=16, color='#ff8c00')),
            xaxis_rangeslider_visible=False,
            height=600,
            legend=dict(bgcolor='rgba(0,0,0,0.5)', bordercolor='rgba(255,69,0,0.3)'),
            margin=dict(l=0, r=0, t=40, b=0)
        )
        fig.update_xaxes(gridcolor='rgba(255,255,255,0.05)')
        fig.update_yaxes(gridcolor='rgba(255,255,255,0.05)')

        st.plotly_chart(fig, use_container_width=True)

        # Sector comparison heatmap
        st.markdown("### 🌡️ Sector Heatmap")
        sectors = {
            'XLK':'Technology','XLF':'Financials','XLE':'Energy',
            'XLV':'Healthcare','XLI':'Industrials','XLY':'Consumer Disc',
            'XLP':'Consumer Staples','XLU':'Utilities','XLB':'Materials','XLRE':'Real Estate'
        }
        perf = {}
        for ticker_sym, name in sectors.items():
            try:
                d = yf.Ticker(ticker_sym).history(period='1mo')
                if not d.empty:
                    perf[name] = ((d['Close'].iloc[-1] - d['Close'].iloc[0]) / d['Close'].iloc[0]) * 100
            except:
                pass

        if perf:
            heat_fig = go.Figure(go.Treemap(
                labels=list(perf.keys()),
                parents=['']*len(perf),
                values=[abs(v) for v in perf.values()],
                text=[f"{v:+.2f}%" for v in perf.values()],
                textinfo="label+text",
                marker=dict(
                    colors=list(perf.values()),
                    colorscale=[[0,'#b71c1c'],[0.5,'#1a1a2e'],[1,'#1b5e20']],
                    cmid=0,
                    showscale=True
                )
            ))
            heat_fig.update_layout(
                template='plotly_dark',
                paper_bgcolor='rgba(0,0,0,0)