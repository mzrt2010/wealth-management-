import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client

# ==========================================
# 1. INITIALIZATION & DATABASE CONNECTION
# ==========================================
st.set_page_config(page_title="Multi-Currency Wealth Manager", layout="wide")

@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL", "YOUR_SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY", "YOUR_SUPABASE_KEY")
    return create_client(url, key)

supabase = init_supabase()

def fetch_portfolio_data():
    try:
        response = supabase.table("wealth_portfolio").select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame()

df = fetch_portfolio_data()

# ==========================================
# 2. FIXED CURRENCY MULTIPLIERS (Base: USD)
# ==========================================
# Both AED and JOD are strictly pegged to the USD, making fixed conversion highly reliable.
EXCHANGE_RATES = {
    "USD": 1.0,
    "AED": 3.6725,  # 1 USD = 3.6725 AED
    "JOD": 0.7090   # 1 USD = 0.7090 JOD
}

CURRENCY_SYMBOLS = {
    "USD": "$",
    "AED": "AED ",
    "JOD": "JOD "
}

def convert_to_display_currency(val, asset_currency, target_currency):
    """Converts an amount from its native currency to the user's preferred viewing currency."""
    # Step 1: Normalize to USD base
    val_usd = val / EXCHANGE_RATES[asset_currency]
    # Step 2: Convert from USD base to Target Currency
    return val_usd * EXCHANGE_RATES[target_currency]

# ==========================================
# 3. APPLICATION LAYOUT
# ==========================================
st.title("💼 Multi-Currency Portfolio Management")
st.markdown("---")

# Global Controls in Sidebar
st.sidebar.header("Global Preferences")
display_currency = st.sidebar.selectbox("Dashboard Base View Currency", ["USD", "AED", "JOD"])
sym = CURRENCY_SYMBOLS[display_currency]

st.sidebar.markdown("---")
menu = st.sidebar.radio("Navigation", ["Dashboard & Reports", "Add/Manage Assets"])

# ==========================================
# MODULE A: DASHBOARD & REPORTS
# ==========================================
if menu == "Dashboard & Reports":
    if df.empty:
        st.info("Your portfolio is currently empty. Head over to 'Add/Manage Assets' to fill your portfolio!")
    else:
        # Create converted columns on the fly for aggregated reporting calculations
        df['cost_converted'] = df.apply(lambda row: convert_to_display_currency(row['total_cost'], row['currency'], display_currency), axis=1)
        df['value_converted'] = df.apply(lambda row: convert_to_display_currency(row['total_current_value'], row['currency'], display_currency), axis=1)
        df['income_converted'] = df.apply(lambda row: convert_to_display_currency(row['monthly_income'], row['currency'], display_currency), axis=1)

        # High-Level Aggregated Metrics
        total_portfolio_cost = df["cost_converted"].sum()
        total_portfolio_value = df["value_converted"].sum()
        total_monthly_income = df["income_converted"].sum()
        net_profit_loss = total_portfolio_value - total_portfolio_cost
        roi = (net_profit_loss / total_portfolio_cost) * 100 if total_portfolio_cost > 0 else 0

        # Metric Displays
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Net Worth", f"{sym}{total_portfolio_value:,.2f}")
        col2.metric("Total Invested Cost", f"{sym}{total_portfolio_cost:,.2f}")
        col3.metric("Net Profit / Loss", f"{sym}{net_profit_loss:,.2f}", delta=f"{roi:.2f}% ROI")
        col4.metric("Est. Monthly Yield", f"{sym}{total_monthly_income:,.2f}")
        
        st.markdown("---")
        
        # Interactive Charts
        st.subheader("📊 Portfolio Allocation")
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            fig_pie = px.pie(
                df, 
                values='value_converted', 
                names='asset_type', 
                title=f"Asset Allocation breakdown (Normalized to {display_currency})",
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Safe
            )
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with chart_col2:
            df_melted = df.groupby('asset_type')[['cost_converted', 'value_converted']].sum().reset_index()
            df_melted = df_melted.melt(id_vars='asset_type', value_vars=['cost_converted', 'value_converted'],
                                      var_name='Valuation Type', value_name='Amount')
            df_melted['Valuation Type'] = df_melted['Valuation Type'].map({'cost_converted': 'Invested Cost', 'value_converted': 'Current Value'})
            
            fig_bar = px.bar(
                df_melted,
                x='asset_type',
                y='Amount',
                color='Valuation Type',
                barmode='group',
                title=f'Asset Class Health Check ({display_currency})',
                labels={'asset_type': 'Asset Class', 'Amount': f'Value ({display_currency})'},
                color_discrete_sequence=['#4A90E2', '#2ECC71']
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")

        # Tabular Asset Ledger Report
        st.subheader("📑 Cross-Border Asset Ledger")
        
        # Clean copy for standard reporting showing original data with currency labels
        report_df = df[[
            "asset_name", "asset_type", "currency", "quantity", "unit_cost", 
            "total_cost", "current_price", "total_current_value", "monthly_income"
        ]].copy()
        
        st.dataframe(
            report_df,
            column_config={
                "asset_name": "Asset Name",
                "asset_type": "Asset Type",
                "currency": "Currency Type",
                "quantity": st.column_config.NumberColumn("Quantity", format="%.4f"),
                "unit_cost": st.column_config.NumberColumn("Local Unit Cost"),
                "total_cost": st.column_config.NumberColumn("Local Total Cost"),
                "current_price": st.column_config.NumberColumn("Local Market Price"),
                "total_current_value": st.column_config.NumberColumn("Local Current Value"),
                "monthly_income": st.column_config.NumberColumn("Local Monthly Income")
            },
            use_container_width=True,
            hide_index=True
        )

# ==========================================
# MODULE B: ADD/MANAGE ASSETS
# ==========================================
elif menu == "Add/Manage Assets":
    st.subheader("➕ Track New Multi-Currency Asset")
    
    with st.form("add_asset_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            asset_name = st.text_input("Asset Name / Ticker Identifier", placeholder="e.g., Emaar Properties, Amm. Real Estate, S&P 500 ETF")
            asset_type = st.selectbox("Asset Type Class", ["Shares", "Real Estate", "Bonds", "Private Equity", "Other"])
            asset_currency = st.selectbox("Denominated Asset Currency", ["AED", "JOD", "USD"], help="Select the exact currency this asset is purchased and valued in.")
            
            if asset_type in ["Shares", "Bonds"]:
                quantity = st.number_input("Total Quantity Units Held", min_value=0.0001, step=1.0, format="%.4f", value=1.0)
            else:
                quantity = 1.0
                
        with col2:
            unit_cost = st.number_input(f"Unit Purchase Cost (Local Denomination)", min_value=0.01, step=100.0, format="%.2f")
            current_price = st.number_input(f"Current Valuation Price (Local Denomination)", min_value=0.01, step=100.0, format="%.2f")
            monthly_income = st.number_input(f"Monthly Distribution Income Yield", min_value=0.0, step=10.0, format="%.2f", help="Dividends, rental yield checks, or bond coupons payouts in local currency asset values.")

        submit_btn = st.form_submit_button("Securely Record Asset")
        
        if submit_btn:
            if not asset_name:
                st.error("Asset tracking identifier name is required.")
            else:
                payload = {
                    "asset_name": asset_name,
                    "asset_type": asset_type,
                    "currency": asset_currency,
                    "quantity": quantity,
                    "unit_cost": unit_cost,
                    "current_price": current_price,
                    "monthly_income": monthly_income
                }
                
                try:
                    supabase.table("wealth_portfolio").insert(payload).execute()
                    st.success(f"Successfully pinned '{asset_name}' designated in {asset_currency} to your dashboard vault!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to post ledger updates to Supabase: {e}")

    # Section to delete assets
    if not df.empty:
        st.markdown("---")
        st.subheader("🗑️ Remove Assets")
        asset_to_delete = st.selectbox("Select asset to remove permanently:", df["asset_name"].unique())
        
        if st.button("Delete Asset", type="primary"):
            try:
                supabase.table("wealth_portfolio").delete().eq("asset_name", asset_to_delete).execute()
                st.success(f"Removed {asset_to_delete} from the database.")
                st.rerun()
            except Exception as e:
                st.error(f"Error removing asset: {e}")
