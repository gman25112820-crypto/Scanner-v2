with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# ============================================================
# 1. RAGE ENGINE GLOW BRANDING
# ============================================================
old_logo = 'RAGE <span style="background: linear-gradient(90deg, #ff4500, #ff8c00); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">ENGINE</span>'
new_logo = 'RAGE <span style="background: linear-gradient(90deg, #ff4500, #ff8c00, #ffcc00); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-shadow: 0 0 20px rgba(255,69,0,0.5); letter-spacing: 2px;">ENGINE</span>'
content = content.replace(old_logo, new_logo)

# ============================================================
# 2. ADD QUOTES + WELCOME AFTER IMPORTS / BEFORE MAIN
# ============================================================
quotes_code = '''
# ============================================================
# RAGE ENGINE - Quotes & Welcome
# ============================================================
import random as _random
import datetime as _datetime

RAGE_QUOTES = [
    ("The stock market is a device for transferring money from the impatient to the patient.", "Warren Buffett"),
    ("In investing, what is comfortable is rarely profitable.", "Robert Arnott"),
    ("Risk comes from not knowing what you are doing.", "Warren Buffett"),
    ("The four most dangerous words in investing are: This time it is different.", "Sir John Templeton"),
    ("Wide diversification is only required when investors do not understand what they are doing.", "Warren Buffett"),
    ("The market is filled with individuals who know the price of everything, but the value of nothing.", "Philip Fisher"),
    ("It is not the strongest of the species that survives, but the most adaptable.", "Charles Darwin"),
    ("Be fearful when others are greedy, and greedy when others are fearful.", "Warren Buffett"),
    ("The goal of a successful trader is to make the best trades. Money is secondary.", "Alexander Elder"),
    ("In trading, the money you lose is tuition. The money you make is profit.", "Unknown"),
    ("Markets can remain irrational longer than you can remain solvent.", "John Maynard Keynes"),
    ("The trend is your friend until the end when it bends.", "Ed Seykota"),
    ("Cut your losses and let your profits run.", "David Ricardo"),
    ("Plan the trade and trade the plan.", "Unknown"),
    ("Success in investing does not correlate with IQ. What you need is the temperament to control urges.", "Warren Buffett"),
]

def get_daily_quote():
    idx = _datetime.date.today().toordinal() % len(RAGE_QUOTES)
    return RAGE_QUOTES[idx]

def get_welcome_message():
    hour = _datetime.datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"
    return greeting

'''

# Insert quotes code near top after imports
import_end = content.find('\n\n# ')
if import_end == -1:
    import_end = content.find('\ndef ')
if import_end > 0:
    content = content[:import_end] + '\n' + quotes_code + content[import_end:]

# ============================================================
# 3. ADD WELCOME + QUOTE TO SIDEBAR
# ============================================================
old_sidebar_sub = 'ROB AND GARETH ENGINE'
new_sidebar_sub = '''ROB AND GARETH ENGINE</div>
    <div style="margin-top:8px; padding:8px; border-left:3px solid #ff4500; background:rgba(255,69,0,0.05);">
    <div style="font-size:10px; color:#888; font-style:italic; line-height:1.4;" id="rage-quote">
    Built by Rob &amp; Gareth. Father and son.<br>
    <span style="color:#ff8c00;">&#x26A1; RAGE Engine</span> — Trading Intelligence Platform
    </div></div'''
content = content.replace(old_sidebar_sub, new_sidebar_sub)

# ============================================================
# 4. ADD WELCOME BANNER TO OVERVIEW PAGE
# ============================================================
old_overview = 'def render_overview('
new_overview = '''def render_overview('''

# Find overview render and add welcome
overview_marker = 'if page == "Overview":'
if overview_marker in content:
    welcome_inject = '''if page == "Overview":
    # RAGE ENGINE WELCOME BANNER
    quote_text, quote_author = get_daily_quote()
    greeting = get_welcome_message()
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, rgba(255,69,0,0.15), rgba(0,0,0,0.3)); 
                border: 1px solid rgba(255,69,0,0.3); border-radius:12px; 
                padding:20px; margin-bottom:20px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <div style="font-size:22px; font-weight:700; color:#fff;">
                    ⚡ {greeting}, welcome to <span style="background: linear-gradient(90deg, #ff4500, #ff8c00); 
                    -webkit-background-clip:text; -webkit-text-fill-color:transparent;">RAGE Engine</span>
                </div>
                <div style="font-size:12px; color:#888; margin-top:4px;">
                    Rob And Gareth Engine &nbsp;|&nbsp; {_datetime.datetime.now().strftime('%A, %d %B %Y')}
                </div>
            </div>
        </div>
        <div style="margin-top:16px; padding-top:16px; border-top:1px solid rgba(255,255,255,0.1);">
            <div style="font-size:13px; color:#ccc; font-style:italic;">
                &ldquo;{quote_text}&rdquo;
            </div>
            <div style="font-size:11px; color:#ff8c00; margin-top:6px;">— {quote_author}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
'''
    content = content.replace(overview_marker, welcome_inject)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('RAGE Engine patch applied successfully.')