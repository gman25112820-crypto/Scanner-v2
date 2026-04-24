with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the exact end of Markets block and replace with chart appended
old_end = '    elif page == "Reports":'
new_end = '''    # == RAGE ENGINE CHART ==
    st.markdown("---")
    st.markdown("### 📊 Interactive Chart")
    import yfinance as _yf2
    import plotly.graph_objects as _go2
    from plotly.subplots import make_subplots as _msp2
    _cc1,_cc2,_cc3=st.columns(3)
    with _cc1: _csym=st.text_input("Symbol","AAPL").upper()
    with _cc2: _cper=st.selectbox("Period",["1mo","3mo","6mo","1y","2y","5y"],index=3)
    with _cc3: _ctyp=st.selectbox("Chart Type",["Candlestick","Line","Area"])
    _ec1,_ec2,_ec3=st.columns(3)
    _e20=_ec1.checkbox("EMA 20",value=True)
    _e50=_ec2.checkbox("EMA 50",value=True)
    _e200=_ec3.checkbox("EMA 200",value=False)
    try:
        _tk2=_yf2.Ticker(_csym)
        _df2=_tk2.history(period=_cper)
        if not _df2.empty:
            _df2['E20']=_df2['Close'].ewm(span=20).mean()
            _df2['E50']=_df2['Close'].ewm(span=50).mean()
            _df2['E200']=_df2['Close'].ewm(span=200).mean()
            _pc2=((_df2['Close'].iloc[-1]-_df2['Close'].iloc[0])/_df2['Close'].iloc[0])*100
            _cur2=_df2['Close'].iloc[-1]
            _dc2=((_df2['Close'].iloc[-1]-_df2['Close'].iloc[-2])/_df2['Close'].iloc[-2])*100
            _m1,_m2,_m3,_m4=st.columns(4)
            _m1.metric("Price",f"${_cur2:.2f}",f"{_dc2:+.2f}%")
            _m2.metric("Period Return",f"{_pc2:+.2f}%")
            _m3.metric("High",f"${_df2['High'].max():.2f}")
            _m4.metric("Low",f"${_df2['Low'].min():.2f}")
            _fig2=_msp2(rows=2,cols=1,shared_xaxes=True,vertical_spacing=0.03,row_heights=[0.75,0.25])
            if _ctyp=="Candlestick":
                _fig2.add_trace(_go2.Candlestick(x=_df2.index,open=_df2['Open'],high=_df2['High'],low=_df2['Low'],close=_df2['Close'],name=_csym,increasing_line_color='#00e676',decreasing_line_color='#ff3d00'),row=1,col=1)
            elif _ctyp=="Line":
                _fig2.add_trace(_go2.Scatter(x=_df2.index,y=_df2['Close'],name=_csym,line=dict(color='#00e5ff',width=2)),row=1,col=1)
            else:
                _fig2.add_trace(_go2.Scatter(x=_df2.index,y=_df2['Close'],name=_csym,fill='tozeroy',line=dict(color='#ff4500',width=2),fillcolor='rgba(255,69,0,0.15)'),row=1,col=1)
            if _e20: _fig2.add_trace(_go2.Scatter(x=_df2.index,y=_df2['E20'],name='EMA20',line=dict(color='#ffeb3b',width=1,dash='dot')),row=1,col=1)
            if _e50: _fig2.add_trace(_go2.Scatter(x=_df2.index,y=_df2['E50'],name='EMA50',line=dict(color='#ff9800',width=1,dash='dot')),row=1,col=1)
            if _e200: _fig2.add_trace(_go2.Scatter(x=_df2.index,y=_df2['E200'],name='EMA200',line=dict(color='#f44336',width=1,dash='dot')),row=1,col=1)
            _vc2=['#00e676' if c>=o else '#ff3d00' for c,o in zip(_df2['Close'],_df2['Open'])]
            _fig2.add_trace(_go2.Bar(x=_df2.index,y=_df2['Volume'],name='Volume',marker_color=_vc2,opacity=0.7),row=2,col=1)
            _fig2.update_layout(template='plotly_dark',paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0.3)',title=dict(text=f"{_csym} — {_cper.upper()}",font=dict(size=16,color='#ff8c00')),xaxis_rangeslider_visible=False,height=550,margin=dict(l=0,r=0,t=40,b=0))
            _fig2.update_xaxes(gridcolor='rgba(255,255,255,0.05)')
            _fig2.update_yaxes(gridcolor='rgba(255,255,255,0.05)')
            st.plotly_chart(_fig2,use_container_width=True)
            st.markdown("### 🌡️ Sector Heatmap")
            _secs2={'XLK':'Tech','XLF':'Finance','XLE':'Energy','XLV':'Health','XLI':'Industrial','XLY':'Cons Disc','XLP':'Staples','XLU':'Utilities','XLB':'Materials','XLRE':'Real Estate'}
            _sp2={}
            for _ts2,_tn2 in _secs2.items():
                try:
                    _sd2=_yf2.Ticker(_ts2).history(period='1mo')
                    if not _sd2.empty: _sp2[_tn2]=((_sd2['Close'].iloc[-1]-_sd2['Close'].iloc[0])/_sd2['Close'].iloc[0])*100
                except: pass
            if _sp2:
                _hf2=_go2.Figure(_go2.Treemap(labels=list(_sp2.keys()),parents=['']*len(_sp2),values=[abs(v)+0.1 for v in _sp2.values()],text=[f"{v:+.2f}%" for v in _sp2.values()],textinfo="label+text",marker=dict(colors=list(_sp2.values()),colorscale=[[0,'#b71c1c'],[0.5,'#1a1a2e'],[1,'#1b5e20']],cmid=0,showscale=True)))
                _hf2.update_layout(template='plotly_dark',paper_bgcolor='rgba(0,0,0,0)',height=280,margin=dict(l=0,r=0,t=10,b=0))
                st.plotly_chart(_hf2,use_container_width=True)
    except Exception as _ce2:
        st.error(f"Chart error: {_ce2}")

    elif page == "Reports":'''

if old_end in content:
    content = content.replace(old_end, new_end)
    print('Injected successfully')
else:
    print('ERROR: marker not found')

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)