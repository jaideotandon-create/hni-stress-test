import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="HNI Portfolio Stress Test", layout="wide")
st.title("HNI Portfolio Stress Test")
st.caption("Educational tool. Historical shocks are rough approximations of "
           "Indian-investor (INR) returns; check and edit them before professional use.")

# ---------- Asset classes ----------
ASSETS = [
    "Large Cap Equity",
    "Mid & Small Cap Equity",
    "Debt Funds / Bonds",
    "Gold",
    "International Equity",
    "Real Estate / REITs",
    "AIF / PMS (Illiquid)",
    "Cash",
]
DEFAULTS = [6.0, 3.0, 5.0, 1.5, 2.0, 2.0, 1.5, 1.0]
LIQUID = ["Large Cap Equity", "Mid & Small Cap Equity", "Debt Funds / Bonds",
          "Gold", "International Equity", "Cash"]
PLEDGEABLE = ["Large Cap Equity", "Mid & Small Cap Equity"]

# ---------- Sidebar: client inputs ----------
st.sidebar.header("Client portfolio (₹ crore)")
holdings = {}
for asset, default in zip(ASSETS, DEFAULTS):
    holdings[asset] = st.sidebar.number_input(asset, min_value=0.0, value=default, step=0.5)

st.sidebar.header("Debt and leverage")
duration = st.sidebar.number_input("Modified duration of debt (years)", 0.0, 30.0, 4.0, 0.5)
convexity = st.sidebar.number_input("Convexity of debt", 0.0, 500.0, 30.0, 5.0)
loan = st.sidebar.number_input("Loan against shares (₹ crore)", min_value=0.0, value=0.0, step=0.5)
max_ltv = st.sidebar.slider("Maximum loan-to-value allowed on pledged equity (%)", 10, 80, 50)

total = sum(holdings.values())
if total == 0:
    st.warning("Enter at least one holding in the sidebar to run a stress test.")
    st.stop()

# ---------- Historical scenarios (approximate peak-to-trough, INR terms) ----------
HISTORICAL = {
    "Global Financial Crisis (2008)": {
        "Large Cap Equity": -0.55, "Mid & Small Cap Equity": -0.70, "Debt Funds / Bonds": 0.05,
        "Gold": 0.25, "International Equity": -0.40, "Real Estate / REITs": -0.30,
        "AIF / PMS (Illiquid)": -0.50, "Cash": 0.0},
    "COVID crash (Feb-Mar 2020)": {
        "Large Cap Equity": -0.38, "Mid & Small Cap Equity": -0.42, "Debt Funds / Bonds": 0.00,
        "Gold": 0.05, "International Equity": -0.28, "Real Estate / REITs": -0.10,
        "AIF / PMS (Illiquid)": -0.35, "Cash": 0.0},
    "Taper tantrum (2013)": {
        "Large Cap Equity": -0.15, "Mid & Small Cap Equity": -0.20, "Debt Funds / Bonds": -0.05,
        "Gold": 0.10, "International Equity": 0.10, "Real Estate / REITs": -0.05,
        "AIF / PMS (Illiquid)": -0.15, "Cash": 0.0},
    "Demonetisation (2016)": {
        "Large Cap Equity": -0.10, "Mid & Small Cap Equity": -0.15, "Debt Funds / Bonds": 0.02,
        "Gold": -0.05, "International Equity": 0.02, "Real Estate / REITs": -0.15,
        "AIF / PMS (Illiquid)": -0.10, "Cash": 0.0},
    "Global rate hikes (2022)": {
        "Large Cap Equity": -0.15, "Mid & Small Cap Equity": -0.20, "Debt Funds / Bonds": -0.02,
        "Gold": 0.05, "International Equity": -0.15, "Real Estate / REITs": -0.05,
        "AIF / PMS (Illiquid)": -0.15, "Cash": 0.0},
}


def stress(shocks):
    rows = []
    for asset in ASSETS:
        value = holdings[asset]
        shock = shocks.get(asset, 0.0)
        pnl = value * shock
        rows.append({
            "Asset class": asset,
            "Value before (₹ Cr)": value,
            "Shock (%)": shock * 100,
            "P&L (₹ Cr)": pnl,
            "Value after (₹ Cr)": value + pnl,
        })
    return pd.DataFrame(rows)


def show_results(df, key):
    before = df["Value before (₹ Cr)"].sum()
    after = df["Value after (₹ Cr)"].sum()
    pnl = after - before

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Portfolio before", f"₹{before:,.2f} Cr")
    c2.metric("Portfolio after", f"₹{after:,.2f} Cr", f"{pnl / before * 100:.1f}%")
    c3.metric("Gain / loss", f"₹{pnl:,.2f} Cr")
    c4.metric("Net worth after loan", f"₹{after - loan:,.2f} Cr")

    # Leverage check
    if loan > 0:
        pledged = df[df["Asset class"].isin(PLEDGEABLE)]["Value after (₹ Cr)"].sum()
        if pledged <= 0:
            st.error("No pledged equity left to cover the loan.")
        else:
            ltv = loan / pledged * 100
            if ltv > max_ltv:
                shortfall = loan - (max_ltv / 100) * pledged
                st.error(f"Margin call: loan-to-value is {ltv:.1f}%, above the {max_ltv}% limit. "
                         f"The client must repay or top up about ₹{shortfall:,.2f} Cr.")
            else:
                st.success(f"Loan-to-value after the shock is {ltv:.1f}%, within the {max_ltv}% limit.")

    # Liquidity check
    liquid = df[df["Asset class"].isin(LIQUID)]["Value after (₹ Cr)"].sum()
    if after > 0:
        st.info(f"Money that can be raised within about a week after the shock: "
                f"₹{liquid:,.2f} Cr ({liquid / after * 100:.0f}% of the portfolio).")

    fig = px.bar(df, x="Asset class", y="P&L (₹ Cr)", color="P&L (₹ Cr)",
                 color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                 title="Gain / loss by asset class")
    st.plotly_chart(fig, key=key)
    st.dataframe(df.round(2), hide_index=True)


tab1, tab2, tab3 = st.tabs(["Historical scenarios", "Build your own shock", "Compare all scenarios"])

# ---------- Tab 1: historical ----------
with tab1:
    choice = st.selectbox("Choose a historical crisis", list(HISTORICAL.keys()))
    show_results(stress(HISTORICAL[choice]), key="historical")

# ---------- Tab 2: hypothetical ----------
with tab2:
    col_a, col_b = st.columns(2)
    with col_a:
        lc = st.slider("Large cap equity change (%)", -70, 30, -30)
        mc = st.slider("Mid & small cap equity change (%)", -80, 30, -40)
        rate_bps = st.slider("Interest rate change (bps)", -300, 500, 200)
        gold = st.slider("Gold change (%)", -40, 60, 10)
    with col_b:
        global_eq = st.slider("Global equities change in USD (%)", -60, 30, -20)
        inr = st.slider("Rupee depreciation vs USD (%)", -20, 40, 10)
        real_estate = st.slider("Real estate change (%)", -50, 20, -15)
        aif = st.slider("AIF / PMS change (%)", -60, 20, -25)

    dy = rate_bps / 10000
    debt_shock = -duration * dy + 0.5 * convexity * dy ** 2
    intl_shock = (1 + global_eq / 100) * (1 + inr / 100) - 1

    hypothetical = {
        "Large Cap Equity": lc / 100, "Mid & Small Cap Equity": mc / 100,
        "Debt Funds / Bonds": debt_shock, "Gold": gold / 100,
        "International Equity": intl_shock, "Real Estate / REITs": real_estate / 100,
        "AIF / PMS (Illiquid)": aif / 100, "Cash": 0.0,
    }
    st.caption(f"Debt impact from duration and convexity: {debt_shock * 100:.2f}%. "
               f"International equity in rupees: {intl_shock * 100:.2f}%.")
    show_results(stress(hypothetical), key="hypothetical")

# ---------- Tab 3: comparison ----------
with tab3:
    all_scenarios = dict(HISTORICAL)
    all_scenarios["Your custom shock"] = hypothetical
    summary = []
    for name, shocks in all_scenarios.items():
        df = stress(shocks)
        change = df["P&L (₹ Cr)"].sum()
        summary.append({"Scenario": name, "Gain / loss (₹ Cr)": round(change, 2),
                        "Change (%)": round(change / total * 100, 1)})
    summary_df = pd.DataFrame(summary).sort_values("Change (%)")
    fig = px.bar(summary_df, x="Change (%)", y="Scenario", orientation="h",
                 color="Change (%)", color_continuous_scale="RdYlGn",
                 color_continuous_midpoint=0, title="Portfolio impact across scenarios")
    st.plotly_chart(fig, key="compare")
    st.dataframe(summary_df, hide_index=True)
