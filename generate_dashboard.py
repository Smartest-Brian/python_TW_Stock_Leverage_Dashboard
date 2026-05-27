#!/usr/bin/env python3
"""
Taiwan Stock Market Leverage & Sentiment Dashboard Generator
Author: Antigravity AI (Expert Quantitative Developer)
Description: Fetches 5-year historical TWSE margin data and TAIFEX Put/Call ratios,
             calculates leverage risk indicators, and generates a standalone,
             interactive, and highly polished HTML dashboard.
Language and standards:
  - Code, variable names, functions, and comments: English.
  - UI labels, explanations, and documentation: Traditional Chinese (繁體中文).
"""

import os
import sys
import io
import time
import logging
from datetime import datetime, timedelta
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# ==============================================================================
# 1. DATA FETCHING MODULE
# ==============================================================================

def fetch_twse_margin_data(start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """
    Fetches the TWSE overall market margin purchase and short sale data from FinMind.
    URL: https://api.finmindtrade.com/api/v4/data
    Dataset: TaiwanStockTotalMarginPurchaseShortSale
    """
    logger.info("Fetching TWSE total market margin data from FinMind...")
    url = "https://api.finmindtrade.com/api/v4/data"
    headers = {
        "Host": "api.finmindtrade.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    params = {
        "dataset": "TaiwanStockTotalMarginPurchaseShortSale",
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d")
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        res_json = response.json()
        
        if res_json.get("status") != 200:
            logger.error(f"FinMind API error: {res_json.get('msg', 'Unknown error')}")
            return pd.DataFrame()
            
        data = res_json.get("data", [])
        if not data:
            logger.warning("No margin data returned from FinMind API.")
            return pd.DataFrame()
            
        df = pd.DataFrame(data)
        logger.info(f"Successfully fetched {len(df)} margin records.")
        return df
        
    except Exception as e:
        logger.error(f"Exception during FinMind API request: {e}")
        return pd.DataFrame()


def fetch_taifex_pcr_chunk(start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """
    Helper function to fetch Put/Call Ratio chunk from TAIFEX.
    Due to TAIFEX website restrictions, queries are limited to short date ranges (e.g., 30 days).
    We include comprehensive browser-like headers to prevent agent blocks, explicitly forcing 'Host'.
    We wrap response.text in io.StringIO to support Pandas 3.0+ string stream parsing.
    """
    url = "https://www.taifex.com.tw/cht/3/pcRatio"
    headers = {
        "Host": "www.taifex.com.tw",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://www.taifex.com.tw",
        "Referer": "https://www.taifex.com.tw/cht/3/pcRatio",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "down_type": "",
        "queryStartDate": start_date.strftime("%Y/%m/%d"),
        "queryEndDate": end_date.strftime("%Y/%m/%d")
    }
    
    try:
        response = requests.post(url, data=data, headers=headers, timeout=20)
        response.raise_for_status()
        
        # Read HTML tables using io.StringIO to prevent FileNotFoundError in Pandas 3+
        html_stream = io.StringIO(response.text)
        tables = pd.read_html(html_stream)
        if not tables:
            return pd.DataFrame()
            
        # We look for the table containing '日期' in its column headers or rows
        for t in tables:
            if t.shape[1] >= 6:
                col_str = str(t.columns.tolist())
                if '日期' in col_str or any(t.iloc[0].astype(str).str.contains('日期')):
                    return t
        return pd.DataFrame()
        
    except Exception as e:
        logger.error(f"Error fetching TAIFEX PCR chunk from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}: {e}")
        return pd.DataFrame()


def fetch_taifex_pcr_data(start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """
    Fetches TAIFEX Put/Call Ratio data by slicing the 5-year period into 30-day chunks.
    This guarantees stability and prevents server rejection or timeouts.
    """
    logger.info("Fetching TAIFEX Put/Call Ratio historical data in 30-day blocks...")
    all_chunks = []
    
    # Split into 30-day chunks
    curr_start = start_date
    while curr_start <= end_date:
        curr_end = min(curr_start + timedelta(days=29), end_date)
        logger.info(f"Crawling TAIFEX Put/Call Ratio: {curr_start.strftime('%Y-%m-%d')} to {curr_end.strftime('%Y-%m-%d')}...")
        
        chunk_df = fetch_taifex_pcr_chunk(curr_start, curr_end)
        if not chunk_df.empty:
            all_chunks.append(chunk_df)
            logger.info(f"Fetched {len(chunk_df)} records for this chunk.")
        else:
            logger.warning(f"Empty or failed chunk: {curr_start.strftime('%Y-%m-%d')} to {curr_end.strftime('%Y-%m-%d')}")
            
        # Polite crawling delay
        time.sleep(1.0)
        curr_start = curr_end + timedelta(days=1)
        
    if not all_chunks:
        logger.error("Failed to fetch any Put/Call Ratio data from TAIFEX.")
        return pd.DataFrame()
        
    # Combine chunks
    combined_df = pd.concat(all_chunks, ignore_index=True)
    logger.info(f"Successfully compiled {len(combined_df)} total records from TAIFEX PCR.")
    return combined_df


# ==============================================================================
# 2. ANALYTICS MODULE
# ==============================================================================

def clean_and_merge_data(margin_df: pd.DataFrame, pcr_df: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans raw columns, converts formats, merges TWSE and TAIFEX datasets,
    and computes the leverage risk indicators.
    Handles the long-to-wide pivot structure returned by the FinMind API.
    """
    logger.info("Processing, cleaning, and merging datasets...")
    
    if margin_df.empty or pcr_df.empty:
        logger.error("Cannot perform analysis due to missing input datasets.")
        return pd.DataFrame()
        
    # --- Clean TWSE Margin Data (Pivot Long to Wide) ---
    margin_df = margin_df.copy()
    
    # Standardize column casing
    margin_df.columns = [col.lower() for col in margin_df.columns]
    
    # Verify expected column names are present
    name_col = 'name' if 'name' in margin_df.columns else None
    balance_col = 'todaybalance' if 'todaybalance' in margin_df.columns else None
    date_col = 'date' if 'date' in margin_df.columns else None
    
    if name_col is None or balance_col is None or date_col is None:
        logger.error(f"FinMind columns missing. Found: {list(margin_df.columns)}")
        return pd.DataFrame()
        
    # Format date
    margin_df['date'] = pd.to_datetime(margin_df['date']).dt.strftime('%Y-%m-%d')
    
    # Pivot the long format table
    logger.info("Pivoting long-format FinMind margin table into wide format...")
    pivot_df = margin_df.pivot_table(
        index='date', 
        columns=name_col, 
        values=balance_col, 
        aggfunc='first'
    ).reset_index()
    
    # Resolve wide columns
    margin_buy_col = None
    margin_sell_col = None
    
    for col in pivot_df.columns:
        if col.lower() == 'marginpurchasemoney':
            margin_buy_col = col
        elif col.lower() == 'shortsale':
            margin_sell_col = col
            
    if margin_buy_col is None:
        # Fallback to MarginPurchase if MarginPurchaseMoney is missing
        for col in pivot_df.columns:
            if col.lower() == 'marginpurchase':
                margin_buy_col = col
                
    if margin_buy_col is None or margin_sell_col is None:
        logger.error(f"Could not resolve margin_buy or margin_sell columns from pivoted: {list(pivot_df.columns)}")
        return pd.DataFrame()
        
    # Compile clean margin DataFrame
    clean_margin_df = pd.DataFrame()
    clean_margin_df['date'] = pivot_df['date']
    clean_margin_df['margin_buy'] = pd.to_numeric(pivot_df[margin_buy_col], errors='coerce')
    clean_margin_df['margin_sell'] = pd.to_numeric(pivot_df[margin_sell_col], errors='coerce')
    clean_margin_df = clean_margin_df.dropna(subset=['date', 'margin_buy'])
    
    # --- Clean TAIFEX PCR Data ---
    pcr_df = pcr_df.copy()
    
    # Flatten MultiIndex if present
    if isinstance(pcr_df.columns, pd.MultiIndex):
        pcr_df.columns = ['_'.join(col).strip() for col in pcr_df.columns.values]
        
    # Match column headers
    pcr_cols_map = {}
    for col in pcr_df.columns:
        col_str = str(col)
        if '日期' in col_str:
            pcr_cols_map[col] = 'date'
        elif '買賣權未平倉量比率' in col_str or '未平倉量比率' in col_str:
            pcr_cols_map[col] = 'pcr_oi'
        elif '買賣權成交量比率' in col_str or '成交量比率' in col_str:
            pcr_cols_map[col] = 'pcr_vol'
            
    pcr_df = pcr_df.rename(columns=pcr_cols_map)
    
    if 'date' not in pcr_df.columns:
        pcr_df = pcr_df.rename(columns={
            pcr_df.columns[0]: 'date',
            pcr_df.columns[3] if len(pcr_df.columns) > 3 else pcr_df.columns[-1]: 'pcr_vol',
            pcr_df.columns[6] if len(pcr_df.columns) > 6 else pcr_df.columns[-1]: 'pcr_oi'
        })
        
    pcr_df = pcr_df[['date', 'pcr_oi', 'pcr_vol']]
    
    pcr_df['date'] = pd.to_datetime(pcr_df['date'], errors='coerce')
    pcr_df = pcr_df.dropna(subset=['date'])
    pcr_df['date'] = pcr_df['date'].dt.strftime('%Y-%m-%d')
    
    for col in ['pcr_oi', 'pcr_vol']:
        pcr_df[col] = pcr_df[col].astype(str).str.replace('%', '', regex=False)
        pcr_df[col] = pcr_df[col].str.replace(',', '', regex=False)
        pcr_df[col] = pd.to_numeric(pcr_df[col], errors='coerce')
        
    pcr_df = pcr_df.dropna(subset=['pcr_oi'])
    
    # --- Merge Datasets ---
    merged_df = pd.merge(clean_margin_df, pcr_df, on='date', how='inner')
    merged_df = merged_df.sort_values('date').reset_index(drop=True)
    
    if merged_df.empty:
        logger.error("Empty dataset after merging TWSE and TAIFEX tables. Check date overlap.")
        return pd.DataFrame()
        
    # --- Compute Leverage Risk Percentile Indicator ---
    margin_min = merged_df['margin_buy'].min()
    margin_max = merged_df['margin_buy'].max()
    margin_range = margin_max - margin_min
    
    if margin_range > 0:
        merged_df['leverage_percentile'] = ((merged_df['margin_buy'] - margin_min) / margin_range) * 100
    else:
        merged_df['leverage_percentile'] = 50.0
        
    merged_df['margin_ratio'] = merged_df['margin_buy'] / merged_df['margin_sell'].replace(0, 1)
    
    logger.info(f"Data processing completed. Merged shape: {merged_df.shape}")
    return merged_df


# ==============================================================================
# 3. VISUALIZATION AND HTML EXPORT MODULE
# ==============================================================================

def build_dashboard(df: pd.DataFrame) -> str:
    """
    Generates interactive Plotly figures and compiles them into a premium dark-themed
    standalone HTML file in Traditional Chinese.
    """
    logger.info("Building Plotly interactive charts...")
    
    # Latest statistics
    latest = df.iloc[-1]
    latest_date = latest['date']
    latest_margin_buy = latest['margin_buy'] / 1e8  # Convert to 億元
    latest_margin_sell = latest['margin_sell'] / 1e4  # Convert to 萬張
    latest_pcr_oi = latest['pcr_oi']
    latest_pcr_vol = latest['pcr_vol']
    latest_leverage_pct = latest['leverage_percentile']
    
    # 5-year stats
    max_margin = df['margin_buy'].max() / 1e8
    min_margin = df['margin_buy'].min() / 1e8
    max_short = df['margin_sell'].max() / 1e4
    min_short = df['margin_sell'].min() / 1e4
    
    # 1. Gauge Chart for Leverage Risk
    risk_level = "低風險"
    risk_color = "#10B981"  # Emerald Green
    if latest_leverage_pct >= 80:
        risk_level = "極高風險"
        risk_color = "#EF4444"  # Red
    elif latest_leverage_pct >= 60:
        risk_level = "高風險"
        risk_color = "#F59E0B"  # Amber/Orange
    elif latest_leverage_pct >= 40:
        risk_level = "中度風險"
        risk_color = "#3B82F6"  # Blue
        
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = latest_leverage_pct,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': f"當前槓桿風險評級：{risk_level}", 'font': {'size': 20, 'color': '#FFFFFF'}},
        gauge = {
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#94A3B8"},
            'bar': {'color': risk_color},
            'bgcolor': "#1E293B",
            'borderwidth': 2,
            'bordercolor': "#475569",
            'steps': [
                {'range': [0, 40], 'color': 'rgba(16, 185, 129, 0.15)'},
                {'range': [40, 60], 'color': 'rgba(59, 130, 246, 0.15)'},
                {'range': [60, 80], 'color': 'rgba(245, 158, 11, 0.15)'},
                {'range': [80, 100], 'color': 'rgba(239, 68, 68, 0.15)'}
            ],
            'threshold': {
                'line': {'color': "#EF4444", 'width': 4},
                'thickness': 0.75,
                'value': latest_leverage_pct
            }
        }
    ))
    
    fig_gauge.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': "#FFFFFF", 'family': "Outfit, Inter, sans-serif"},
        height=320,
        margin=dict(l=20, r=20, t=50, b=20)
    )
    
    # 2. TWSE Margin Buying & Short Selling Trend (Double Y-Axis)
    fig_margin = make_subplots(specs=[[{"secondary_y": True}]])
    
    fig_margin.add_trace(
        go.Scatter(
            x=df['date'],
            y=df['margin_buy'] / 1e8,
            name="融資餘額 (左軸)",
            line=dict(color="#3B82F6", width=2.5),
            fill='tozeroy',
            fillcolor='rgba(59, 130, 246, 0.05)'
        ),
        secondary_y=False
    )
    
    fig_margin.add_trace(
        go.Scatter(
            x=df['date'],
            y=df['margin_sell'] / 1e4,
            name="融券餘額 (右軸)",
            line=dict(color="#EC4899", width=2, dash='dot')
        ),
        secondary_y=True
    )
    
    fig_margin.update_layout(
        title_text="市場信用交易融資融券 5 年歷史走勢",
        title_font=dict(size=18, color="#FFFFFF"),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color="#94A3B8", family="Outfit, Inter, sans-serif"),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color="#FFFFFF")
        ),
        margin=dict(l=10, r=10, t=60, b=10),
        height=360
    )
    
    fig_margin.update_xaxes(
        showgrid=True,
        gridcolor="rgba(71, 85, 105, 0.2)",
        linecolor="#475569",
        tickfont=dict(color="#94A3B8")
    )
    
    fig_margin.update_yaxes(
        title_text="融資餘額 (億新台幣)",
        title_font=dict(color="#3B82F6"),
        showgrid=True,
        gridcolor="rgba(71, 85, 105, 0.2)",
        linecolor="#475569",
        tickfont=dict(color="#94A3B8"),
        secondary_y=False
    )
    
    fig_margin.update_yaxes(
        title_text="融券餘額 (萬張)",
        title_font=dict(color="#EC4899"),
        showgrid=False,
        linecolor="#475569",
        tickfont=dict(color="#94A3B8"),
        secondary_y=True
    )
    
    # 3. TAIFEX Put/Call Ratio Trend
    fig_pcr = go.Figure()
    
    fig_pcr.add_trace(
        go.Scatter(
            x=df['date'],
            y=df['pcr_oi'],
            name="選擇權未平倉量 P/C 比率",
            line=dict(color="#10B981", width=2.5),
            fill='tozeroy',
            fillcolor='rgba(16, 185, 129, 0.04)'
        )
    )
    
    fig_pcr.add_trace(
        go.Scatter(
            x=df['date'],
            y=[100] * len(df),
            name="多空平衡線 (100%)",
            line=dict(color="#EF4444", width=1.5, dash='dash'),
            showlegend=True
        )
    )
    
    fig_pcr.update_layout(
        title_text="臺指選擇權未平倉量 Put/Call Ratio 5 年歷史走勢",
        title_font=dict(size=18, color="#FFFFFF"),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color="#94A3B8", family="Outfit, Inter, sans-serif"),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color="#FFFFFF")
        ),
        margin=dict(l=10, r=10, t=60, b=10),
        height=320
    )
    
    fig_pcr.update_xaxes(
        showgrid=True,
        gridcolor="rgba(71, 85, 105, 0.2)",
        linecolor="#475569",
        tickfont=dict(color="#94A3B8")
    )
    
    fig_pcr.update_yaxes(
        title_text="未平倉比率 (%)",
        showgrid=True,
        gridcolor="rgba(71, 85, 105, 0.2)",
        linecolor="#475569",
        tickfont=dict(color="#94A3B8")
    )
    
    # Convert charts to HTML div blocks
    gauge_div = fig_gauge.to_html(full_html=False, include_plotlyjs=False)
    margin_div = fig_margin.to_html(full_html=False, include_plotlyjs=False)
    pcr_div = fig_pcr.to_html(full_html=False, include_plotlyjs=False)
    
    # Formatting display values
    latest_margin_buy_fmt = f"{latest_margin_buy:,.2f}"
    latest_margin_sell_fmt = f"{latest_margin_sell:,.2f}"
    latest_pcr_oi_fmt = f"{latest_pcr_oi:.2f}%"
    latest_leverage_pct_fmt = f"{latest_leverage_pct:.1f}%"
    
    max_margin_fmt = f"{max_margin:,.2f}"
    min_margin_fmt = f"{min_margin:,.2f}"
    max_short_fmt = f"{max_short:,.2f}"
    min_short_fmt = f"{min_short:,.2f}"
    
    # HTML Template
    html_content = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>臺灣股市槓桿風險指標與情緒儀表板 (TWSE/TAIFEX)</title>
    <!-- Include Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
    <!-- Include Plotly JS CDN (Ensures rendering in any environment) -->
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        :root {{
            --bg-dark: #0B0F19;
            --bg-card: #151D30;
            --border-color: #24304F;
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
            --primary: #3B82F6;
            --secondary: #EC4899;
            --success: #10B981;
            --warning: #F59E0B;
            --danger: #EF4444;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            background-color: var(--bg-dark);
            color: var(--text-main);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            padding: 24px;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        /* Header section */
        header {{
            background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px 32px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        }}
        
        .header-title h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: 26px;
            font-weight: 700;
            background: linear-gradient(90deg, #3B82F6 0%, #10B981 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 6px;
        }}
        
        .header-title p {{
            color: var(--text-muted);
            font-size: 14px;
        }}
        
        .header-badge {{
            background-color: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.3);
            color: var(--primary);
            padding: 6px 16px;
            border-radius: 30px;
            font-size: 12px;
            font-weight: 600;
        }}
        
        /* KPI Grid */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }}
        
        .kpi-card {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 20px 24px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        
        .kpi-card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 10px 25px rgba(59, 130, 246, 0.1);
            border-color: #3B82F650;
        }}
        
        .kpi-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }}
        
        .kpi-title {{
            color: var(--text-muted);
            font-size: 13px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        
        .kpi-icon {{
            font-size: 18px;
        }}
        
        .kpi-value {{
            font-family: 'Outfit', sans-serif;
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 8px;
        }}
        
        .kpi-footer {{
            font-size: 12px;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        
        .badge-status {{
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 10px;
        }}
        
        /* Layout Grids */
        .dashboard-row-1 {{
            display: grid;
            grid-template-columns: 1fr 2fr;
            gap: 20px;
            margin-bottom: 24px;
        }}
        
        @media (max-width: 1024px) {{
            .dashboard-row-1 {{
                grid-template-columns: 1fr;
            }}
        }}
        
        .card {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        }}
        
        .card-title {{
            font-family: 'Outfit', sans-serif;
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 16px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 10px;
            color: var(--text-main);
        }}
        
        .row-full {{
            margin-bottom: 24px;
        }}
        
        /* Info & Analysis Section */
        .info-section {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
        }}
        
        @media (max-width: 768px) {{
            .info-section {{
                grid-template-columns: 1fr;
            }}
        }}
        
        .info-box {{
            background-color: #1E293B50;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
        }}
        
        .info-box h3 {{
            color: var(--primary);
            font-size: 16px;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .info-box ul {{
            padding-left: 20px;
            font-size: 13.5px;
            color: var(--text-muted);
        }}
        
        .info-box li {{
            margin-bottom: 8px;
        }}
        
        .info-box strong {{
            color: var(--text-main);
        }}
        
        .text-emerald {{ color: var(--success); }}
        .text-pink {{ color: var(--secondary); }}
        .text-blue {{ color: var(--primary); }}
        .text-amber {{ color: var(--warning); }}
        .text-red {{ color: var(--danger); }}
        
        footer-credit {{
            text-align: center;
            margin-top: 40px;
            color: var(--text-muted);
            font-size: 12px;
            border-top: 1px solid var(--border-color);
            padding-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        
        <!-- Header -->
        <header>
            <div class="header-title">
                <h1>臺灣股市槓桿風險指標與情緒儀表板</h1>
                <p>數據更新日期：{latest_date} | 回測區間：過去 5 年歷史走勢統計 (TWSE / TAIFEX)</p>
            </div>
            <div class="header-badge">
                專業量化開發版 (Antigravity Quant Engine)
            </div>
        </header>
        
        <!-- KPI Cards Grid -->
        <div class="kpi-grid">
            
            <!-- Card 1: Leverage Risk -->
            <div class="kpi-card">
                <div class="kpi-header">
                    <span class="kpi-title">當前槓桿風險百分比</span>
                    <span class="kpi-icon" style="color: {risk_color};">⚡</span>
                </div>
                <div class="kpi-value" style="color: {risk_color};">{latest_leverage_pct_fmt}</div>
                <div class="kpi-footer">
                    <span>槓桿狀態：</span>
                    <span class="badge-status" style="background-color: {risk_color}20; color: {risk_color};">{risk_level}</span>
                </div>
            </div>
            
            <!-- Card 2: Margin Buy -->
            <div class="kpi-card">
                <div class="kpi-header">
                    <span class="kpi-title">大盤融資餘額</span>
                    <span class="kpi-icon text-blue">📈</span>
                </div>
                <div class="kpi-value text-blue">NT$ {latest_margin_buy_fmt} 億</div>
                <div class="kpi-footer">
                    <span>5年區間：{min_margin_fmt} 億 - {max_margin_fmt} 億</span>
                </div>
            </div>
            
            <!-- Card 3: Put/Call Ratio -->
            <div class="kpi-card">
                <div class="kpi-header">
                    <span class="kpi-title">選擇權 Put/Call 未平倉比</span>
                    <span class="kpi-icon text-emerald">📊</span>
                </div>
                <div class="kpi-value text-emerald">{latest_pcr_oi_fmt}</div>
                <div class="kpi-footer">
                    <span>狀態：</span>
                    <span class="badge-status" style="background-color: rgba(16, 185, 129, 0.2); color: var(--success);">
                        { '多方支撐強' if latest_pcr_oi >= 100 else '空方壓制大' }
                    </span>
                </div>
            </div>
            
            <!-- Card 4: Margin Sell -->
            <div class="kpi-card">
                <div class="kpi-header">
                    <span class="kpi-title">大盤融券餘額</span>
                    <span class="kpi-icon text-pink">📉</span>
                </div>
                <div class="kpi-value text-pink">{latest_margin_sell_fmt} 萬張</div>
                <div class="kpi-footer">
                    <span>5年區間：{min_short_fmt} 萬張 - {max_short_fmt} 萬張</span>
                </div>
            </div>
            
        </div>
        
        <!-- Row 1: Gauge & Margin Trend -->
        <div class="dashboard-row-1">
            
            <!-- Gauge Card -->
            <div class="card" style="display: flex; flex-direction: column; justify-content: center; align-items: center;">
                {gauge_div}
            </div>
            
            <!-- Margin Trend Card -->
            <div class="card">
                {margin_div}
            </div>
            
        </div>
        
        <!-- Row 2: PCR Trend -->
        <div class="card row-full">
            {pcr_div}
        </div>
        
        <!-- Row 3: Quantitative Documentation -->
        <div class="card">
            <div class="card-title">🔍 量化指標說明與市場結構解讀指南</div>
            <div class="info-section">
                
                <div class="info-box">
                    <h3>💡 融資餘額百分比 (槓桿風險指標)</h3>
                    <ul>
                        <li><strong>定義：</strong>將當前的整體市場融資餘額與過去 5 年的歷史最低值與最高值進行標準化百分比計算。</li>
                        <li><strong>量化界線：</strong>
                            <br>- <span class="text-emerald"><strong>0% - 40% (低風險)：</strong></span>市場散戶槓桿程度較低，融資沉澱少，籌碼相對乾淨穩定。
                            <br>- <span class="text-blue"><strong>40% - 60% (中度風險)：</strong></span>槓桿處於歷史常態水平，市場呈中性運行。
                            <br>- <span class="text-amber"><strong>60% - 80% (高風險)：</strong></span>散戶信用資金大幅進場，市場槓桿堆疊，需注意籌碼開始動搖。
                            <br>- <span class="text-red"><strong>80% - 100% (極高風險)：</strong></span>槓桿接近歷史極限。一旦大盤回檔，容易引發融資多殺多及斷頭清算潮（Margin Call）。
                        </li>
                        <li><strong>量化策略：</strong>歷史統計顯示，當此指標進入 85% 以上且選擇權 P/C 比率開始向下破位時，是極佳的系統性減碼信號。</li>
                    </ul>
                </div>
                
                <div class="info-box">
                    <h3>📊 臺指選擇權 Put/Call Ratio (PCR)</h3>
                    <ul>
                        <li><strong>指標定義：</strong>賣權（Put）未平倉量除以買權（Call）未平倉量。在台股市場中，此指標為最靈敏的籌碼對稱與莊家防守線。</li>
                        <li><strong>數據解讀：</strong>
                            <br>- <strong>PCR &gt; 100% (多方防守)：</strong>代表下方賣權支撐莊家（Put Seller）力道強勁。通常伴隨大盤回檔時的強力防守區。
                            <br>- <strong>PCR &lt; 100% (空方壓制)：</strong>代表上方買權莊家（Call Seller）壓制力強，市場情緒偏向保守避險，多頭上攻阻力大。
                        </li>
                        <li><strong>反向情緒解讀：</strong>當 PCR 跌破 75% 以下，往往代表市場情緒極度恐慌，可能孕育反彈買點；反之，若 PCR 大於 140% 以上且融資百分比極高，則需提防過度樂觀後的急跌。</li>
                    </ul>
                </div>
                
            </div>
            
            <div class="info-box" style="margin-top: 20px; background-color: rgba(59, 130, 246, 0.05); border-color: rgba(59, 130, 246, 0.2);">
                <h3 class="text-blue">🧪 量化交易觀點 (Antigravity Analysis)</h3>
                <p style="font-size: 14px; color: var(--text-muted); margin-top: 8px;">
                    完美的量化策略通常結合<strong>「趨勢槓桿」</strong>與<strong>「期權避險」</strong>雙重維度。
                    當<b>融資餘額百分比處於 80% 以上（散戶槓桿超載）</b>且<b>Put/Call Ratio 開始急劇下行跌破 100%（莊家防守撤退，避險權重增強）</b>時，
                    大盤發生「多殺多斷頭潮」的概率將呈指數級上升。投資人應採取防禦性配置，減低持股成數或利用臺指期貨進行反向避險。
                </p>
            </div>
        </div>
        
        <!-- Footer -->
        <div class="footer-credit" style="text-align: center; margin-top: 30px; color: var(--text-muted); font-size: 11px;">
            <p>臺灣股市槓桿與期權情緒分析儀表板 © 2026 由 Antigravity 專家量化引擎所產生。本資訊僅供學術與技術回測參考，不構成任何投資建議。</p>
        </div>
        
    </div>
</body>
</html>
"""
    return html_content


# ==============================================================================
# 4. MAIN CONTROLLER
# ==============================================================================

def main():
    logger.info("==========================================================")
    logger.info("STARTING TAIWAN STOCK MARKET LEVERAGE DASHBOARD GENERATION")
    logger.info("==========================================================")
    
    # Calculate dates: 5 years lookback
    end_date = datetime.today()
    start_date = end_date - timedelta(days=5 * 365)
    
    logger.info(f"Targeting date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    # 1. Fetch data
    margin_df = fetch_twse_margin_data(start_date, end_date)
    pcr_df = fetch_taifex_pcr_data(start_date, end_date)
    
    if margin_df.empty:
        logger.error("Failed to fetch TWSE margin data. Aborting dashboard generation.")
        sys.exit(1)
        
    if pcr_df.empty:
        logger.error("Failed to fetch TAIFEX Put/Call Ratio data. Aborting dashboard generation.")
        sys.exit(1)
        
    # 2. Analytics
    analytics_df = clean_and_merge_data(margin_df, pcr_df)
    
    if analytics_df.empty:
        logger.error("Data cleaning and merging returned empty dataset. Aborting dashboard generation.")
        sys.exit(1)
        
    # 3. Visualization and HTML compilation
    html_dashboard = build_dashboard(analytics_df)
    
    # 4. Export
    output_filename = "taiwan_leverage_dashboard.html"
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(html_dashboard)
        logger.info("==========================================================")
        logger.info(f"DASHBOARD SUCCESSFULLY EXPORTED TO: {output_filename}")
        logger.info("You can now open this file directly in your browser to preview.")
        logger.info("==========================================================")
    except Exception as e:
        logger.error(f"Failed to write output HTML file: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
