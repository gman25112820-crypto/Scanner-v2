with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the Markets page stop point and add chart section before it
chart_section = '''
    # == RAGE ENGINE ENHANCED CHARTS ==
    st.markdown("---")
    st.markdown("### 📊 Interactive Chart")
    
    import yfinance as yf
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    chart_col1, chart_col2, chart_col3 = st.columns(3)
    with chart_col1:
        chart_sym = st.text_input("Chart Symbol", value="AAPL").upper()
    with chart_col2:
        chart_period = st.selectbox("Period", ["1mo","3mo","6mo","1y","2y","5y"], index=3)
    with chart_col3:
        chart_type = st.selectbox("Chart Type", ["Candlestick","Line","Area"])

    ema_col1, ema_col2, ema_col3 = st.columns(3)
    show_ema20 = ema_col1.checkbox("EMA 20", value=True)
    show_ema50 = ema_col2.checkbox("EMA 50", value=True)
    show_ema200 = ema_col3.checkbox("EMA 200", value=False)

    try:
        _ticker = yf.Ticker(chart_sym)
        _df = _ticker.history(period=chart_period)
        _info = _ticker.info

        if not _df.empty:
            _df['EMA20'] = _df['Close'].ewm(span=20).mean()
            _df['EMA50'] = _df['Close'].ewm(span=50).mean()
            _df['EMA200'] = _df['Close'].ewm(span=200).mean()

            _price_chg = ((_df['Close'].iloc[-1] - _df['Close'].iloc[0]) / _df['Close'].iloc[0]) * 100
            _current = _df['Close'].iloc[-1]
            _day_chg = ((_df['Close'].iloc[-1] - _df['Close'].iloc[-2]) / _df['Close'].iloc[-2]) * 100

            mc1,mc2,mc3,mc4 = st.columns(4)
            mc1.metric("Price", f"${_current:.2f}", f"{_day_chg:+.2f}%")
            mc2.metric("Period Return", f"{_price_chg:+.2f}%")
            mc3.metric("Period High", f"${_df['High'].max():.2f}")
            mc4.metric("Period Low", f"${_df['Low'].min():.2f}")

            _fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                               vertical_spacing=0.03, row_heights=[0.75,0.25])

            if chart_type == "Candlestick":
                _fig.add_trace(go.Candlestick(
                    x=_df.index, open=_df['Open'], high=_df['High'],
                    low=_df['Low'], close=_df['Close'], name=chart_sym,
                    increasing_line_color='#00e676', decreasing_line_color='#ff3d00'
                ), row=1, col=1)
            elif chart_type == "Line":
                _fig.add_trace(go.Scatter(
                    x=_df.index, y=_df['Close'], name=chart_sym,
                    line=dict(color='#00e5ff', width=2)
                ), row=1, col=1)
            else:
                _fig.add_trace(go.Scatter(
                    x=_df.index, y=_df['Close'], name=chart_sym,
                    fill='tozeroy', line=dict(color='#ff4500', width=2),
                    fillcolor='rgba(255,69,0,0.15)'
                ), row=1, col=1)

            if show_ema20:
                _fig.add_trace(go.Scatter(x=_df.index, y=_df['EMA20'], name='EMA 20',
                    line=dict(color='#ffeb3b', width=1, dash='dot')), row=1, col=1)
            if show_ema50:
                _fig.add_trace(go.Scatter(x=_df.index, y=_df['EMA50'], name='EMA 50',
                    line=dict(color='#ff9800', width=1, dash='dot')), row=1, col=1)
            if show_ema200:
                _fig.add_trace(go.Scatter(x=_df.index, y=_df['EMA200'], name='EMA 200',
                    line=dict(color='#f44336', width=1, dash='dot')), row=1, col=1)

            _colors = ['#00e676' if c >= o else '#ff3d00'
                      for c,o in zip(_df['Close'], _df['Open'])]
            _fig.add_trace(go.Bar(x=_df.index, y=_df['Volume'], name='Volume',
                                 marker_color=_colors, opacity=0.7), row=2, col=1)

            _fig.update_layout(
                template='plotly_dark',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0.3)',
                title=dict(text=f"{chart_sym} — {chart_period.upper()}", font=dict(size=16,color='#ff8c00')),
                xaxis_rangeslider_visible=False,
                height=550,
                legend=dict(bgcolor='rgba(0,0,0,0.5)'),
                margin=dict(l=0,r=0,t=40,b=0)
            )
            _fig.update_xaxes(gridcolor='rgba(255,255,255,0.05)')
            _fig.update_yaxes(gridcolor='rgba(255,255,255,0.05)')
            st.plotly_chart(_fig, use_container_width=True)

            # Sector Heatmap
            st.markdown("### 🌡️ Sector Heatmap (1 Month)")
            _sectors = {
                'XLK':'Technology','XLF':'Financials','XLE':'Energy',
                'XLV':'Healthcare','XLI':'Industrials','XLY':'Consumer Disc',
                'XLP':'Consumer Staples','XLU':'Utilities','XLB':'Materials','XLRE':'Real Estate'
            }
            _perf = {}
            for _ts, _tn in _sectors.items():
                try:
                    _sd = yf.Ticker(_ts).history(period='1mo')
                    if not _sd.empty:
                        _perf[_tn] = ((_sd['Close'].iloc[-1]-_sd['Close'].iloc[0])/_sd['Close'].iloc[0])*100
                except: pass

            if _perf:
                _hfig = go.Figure(go.Treemap(
                    labels=list(_perf.keys()),
                    parents=['']*len(_perf),
                    values=[abs(v)+0.1 for v in _perf.values()],
                    text=[f"{v:+.2f}%" for v in _perf.values()],
                    textinfo="label+text",
                    marker=dict(
                        colors=list(_perf.values()),
                        colorscale=[[0,'#b71c1c'],[0.5,'#1a1a2e'],[1,'#1b5e20']],
                        cmid=0, showscale=True
                    )
                ))
                _hfig.update_layout(
                    template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
                    height=280, margin=dict(l=0,r=0,t=10,b=0)
                )
                st.plotly_chart(_hfig, use_container_width=True)
    except Exception as _e:
        st.error(f"Chart error: {_e}")
'''

# Insert before the st.stop() that follows Markets
old_stop = '''if page == "Markets":
    render_enhanced_markets()
    st.stop()'''

if old_stop in content:
    content = content.replace(old_stop, f'if page == "Markets":\n    render_enhanced_markets()\n    st.stop()')

# Find existing markets page render and append charts
markets_render = 'render_markets()'
if markets_render in content:
    content = content.replace(markets_render, f'render_markets()\n{chart_section}')
else:
    # Try finding the markets section directly
    markets_marker = 'if page == "Markets":'
    if markets_marker in content:
        # Find end of markets block and inject
        idx = content.find(markets_marker)
        next_if = content.find('\nif page ==', idx+1)
        if next_if > 0:
            content = content[:next_if] + '\n' + chart_section + content[next_if:]

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Charts v2 patch applied.')