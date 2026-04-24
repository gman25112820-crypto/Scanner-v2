with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

charts_handler = '''    elif page == "Charts":
        st.markdown("""
        <div style="background:linear-gradient(135deg,rgba(255,69,0,0.15),rgba(0,0,0,0.3));
                    border:1px solid rgba(255,69,0,0.3);border-radius:12px;
                    padding:16px;margin-bottom:20px;">
            <span style="font-size:22px;font-weight:700;color:#fff;">📊 RAGE Engine Charts</span>
            <span style="font-size:12px;color:#888;margin-left:12px;">Interactive Market Analysis</span>
        </div>
        """, unsafe_allow_html=True)
        import yfinance as _yf3
        import plotly.graph_objects as _go3
        from plotly.subplots import make_subplots as _msp3
        _cc1,_cc2,_cc3=st.columns(3)
        with _cc1: _csym3=st.text_input("Symbol","AAPL").upper()
        with _cc2: _cper3=st.selectbox("Period",["1mo","3mo","6mo","1y","2y","5y"],index=3)
        with _cc3: _ctyp3=st.selectbox("Chart Type",["Candlestick","Line","Area"])
        _ec1,_ec2,_ec3=st.columns(3)
        _e20=_ec1.checkbox("EMA 20",value=True)
        _e50=_ec2.checkbox("EMA 50",value=True)
        _e200=_ec3.checkbox("EMA 200",value=False)
        try:
            _tk3=_yf3.Ticker(_csym3)
            _df3=_tk3.history(period=_cper3)
            _info3=_tk3.info
            if not _df3.empty:
                _df3['E20']=_df3['Close'].ewm(span=20).mean()
                _df3['E50']=_df3['Close'].ewm(span=50).mean()
                _df3['E200']=_df3['Close'].ewm(span=200).mean()
                _pc3=((_df3['Close'].iloc[-1]-_df3['Close'].iloc[0])/_df3['Close'].iloc[0])*100
                _cur3=_df3['Close'].iloc[-1]
                _dc3=((_df3['Close'].iloc[-1]-_df3['Close'].iloc[-2])/_df3['Close'].iloc[-2])*100
                _m1,_m2,_m3,_m4=st.columns(4)
                _m1.metric("Price",f"${_cur3:.2f}",f"{_dc3:+.2f}%")
                _m2.metric("Period Return",f"{_pc3:+.2f}%")
                _m3.metric("High",f"${_df3['High'].max():.2f}")
                _m4.metric("Low",f"${_df3['Low'].min():.2f}")
                _fig3=_msp3(rows=2,cols=1,shared_xaxes=True,vertical_spacing=0.03,row_heights=[0.75,0.25])
                if _ctyp3=="Candlestick":
                    _fig3.add_trace(_go3.Candlestick(x=_df3.index,open=_df3['Open'],high=_df3['High'],low=_df3['Low'],close=_df3['Close'],name=_csym3,increasing_line_color='#00e676',decreasing_line_color='#ff3d00'),row=1,col=1)
                elif _ctyp3=="Line":
                    _fig3.add_trace(_go3.Scatter(x=_df3.index,y=_df3['Close'],name=_csym3,line=dict(color='#00e5ff',width=2)),row=1,col=1)
                else:
                    _fig3.add_trace(_go3.Scatter(x=_df3.index,y=_df3['Close'],name=_csym3,fill='tozeroy',line=dict(color='#ff4500',width=2),fillcolor='rgba(255,69,0,0.15)'),row=1,col=1)
                if _e20: _fig3.add_trace(_go3.Scatter(x=_df3.index,y=_df3['E20'],name='EMA20',line=dict(color='#ffeb3b',width=1,dash='dot')),row=1,col=1)
                if _e50: _fig3.add_trace(_go3.Scatter(x=_df3.index,y=_df3['E50'],name='EMA50',line=dict(color='#ff9800',width=1,dash='dot')),