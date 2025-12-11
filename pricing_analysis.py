import streamlit as st
import pandas as pd
import plotly.express as px

# --- 页面全局设置 ---
st.set_page_config(page_title="全球定价决策看板", layout="wide", page_icon="📊")

# ==========================================
# 1. 侧边栏：上传与筛选
# ==========================================
st.sidebar.title("📂 数据与筛选")

# [功能] 文件上传
uploaded_file = st.sidebar.file_uploader("1. 上传数据文件 (支持 CSV/Excel)", type=['csv', 'xlsx', 'xls'])

# --- 数据清洗函数 ---
def load_and_process(file):
    # A. 读取文件
    try:
        if file.name.endswith('.csv'):
            try:
                df = pd.read_csv(file)
            except:
                file.seek(0)
                df = pd.read_csv(file, encoding='gbk')
        else:
            df = pd.read_excel(file)
    except Exception as e:
        return None, f"文件读取错误: {e}"

    # B. 列名清洗
    df.columns = df.columns.str.strip()
    
    # C. 智能列名映射
    col_map = {}
    for col in df.columns:
        if col in ['单价/每吨', '价格/每吨', '单价', 'Price', 'Unit Price']:
            col_map[col] = '单价'
        elif col in ['第二数量', '数量', 'Qty', 'Quantity', 'Sales Qty']:
            col_map[col] = '销量(吨)'
        elif col in ['贸易伙伴名称', '国家', 'Country', 'Partner']:
            col_map[col] = '国家'
            
    df.rename(columns=col_map, inplace=True)
    
    # D. 检查必要列
    required_cols = ['单价', '销量(吨)', '国家']
    if not all(c in df.columns for c in required_cols):
        return None, f"❌ 数据缺失！请确保文件中包含: {required_cols}"

    # E. 数值转换
    for c in ['单价', '销量(吨)']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    
    df = df.dropna(subset=['单价', '销量(吨)'])
    df = df[df['单价'] > 0] 
    
    # [核心计算] 总销售额
    df['总销售额'] = df['单价'] * df['销量(吨)']
    
    return df, None

# ==========================================
# 主逻辑开始
# ==========================================
if uploaded_file:
    # 1. 加载数据
    df, err = load_and_process(uploaded_file)
    if err:
        st.error(err)
        st.stop()
        
    st.sidebar.divider()
    st.sidebar.subheader("2. 高级过滤器")

    # [筛选1] 极值剔除
    use_iqr = st.sidebar.checkbox("剔除价格异常值 (IQR)", value=True, help="自动剔除价格过高或过低的极端订单。")
    if use_iqr:
        Q1 = df['单价'].quantile(0.25)
        Q3 = df['单价'].quantile(0.75)
        IQR = Q3 - Q1
        df = df[(df['单价'] >= Q1 - 1.5*IQR) & (df['单价'] <= Q3 + 1.5*IQR)]

    # [筛选2] 销售额门槛筛选
    country_sales_sum = df.groupby('国家')['总销售额'].sum()
    min_sales_threshold = st.sidebar.number_input(
        "💰 最小销售额过滤 (元)", 
        min_value=0, 
        value=10000, 
        step=5000,
        help="剔除总生意额低于此数值的国家（如样品单）。"
    )
    valid_countries = country_sales_sum[country_sales_sum >= min_sales_threshold].index
    df = df[df['国家'].isin(valid_countries)]

    # [筛选3] 指定国家
    all_valid_countries = sorted(df['国家'].unique())
    selected_countries = st.sidebar.multiselect("🌍 特定国家筛选", options=all_valid_countries)
    if selected_countries:
        df = df[df['国家'].isin(selected_countries)]

    # ==========================================
    # 2. 顶部：标题与业务解释
    # ==========================================
    file_name = uploaded_file.name.split('.')[0]
    st.title(f"📊 {file_name} - 全球定价决策分析")
    
    with st.expander("📖 **分析指南：名词解释与判断依据 (点击展开)**", expanded=True):
        st.markdown("""
        * **🔴 红海 (Low End)：** 价格最低的 25% 订单。竞争激烈，拼价格。
        * **🟢 蓝海 (High End)：** 价格最高的 25% 订单。高溢价，高利润。
        * **全球定价矩阵：** 横轴=价格，纵轴=销量，气泡=总金额。寻找右上角的“现金牛”。
        """)

    st.divider()

    # ==========================================
    # 数据聚合准备
    # ==========================================
    country_stats = df.groupby('国家').agg({
        '单价': 'median',       
        '销量(吨)': 'sum',      
        '总销售额': 'sum',      
        '国家': 'count'         
    }).rename(columns={'国家':'订单数'}).reset_index()

    # 市场分类
    p25 = df['单价'].quantile(0.25)
    p75 = df['单价'].quantile(0.75)
    def classify_market(price):
        if price >= p75: return '🟢 高价蓝海'
        elif price <= p25: return '🔴 低价红海'
        else: return '🟡 主流市场'
    country_stats['市场类型'] = country_stats['单价'].apply(classify_market)

    # 计算整体加权平均价
    total_rev = df['总销售额'].sum()
    total_vol = df['销量(吨)'].sum()
    avg_price_weighted = total_rev / total_vol if total_vol > 0 else 0

   # ==========================================
    # 3. 三大独立统计面板 (布局优化版：防止数值挤压)
    # ==========================================
    st.subheader("1. 核心统计概览 (Descriptive Statistics)")
    st.info("从 **价格、销量、业绩** 三个维度透视业务健康度。")

    # [安全计算] 防止筛选后数据为空导致报错
    if len(df) == 0:
        st.warning("⚠️ 当前筛选后无数据，请调整左侧筛选条件。")
        st.stop()

    # 重新计算需要的统计值
    total_rev = df['总销售额'].sum()
    total_vol = df['销量(吨)'].sum()
    avg_price_weighted = total_rev / total_vol if total_vol > 0 else 0
    
    # 样式优化：每个板块内部不再一行塞5个，而是分两行显示
    
    # --- 面板 1: 价格统计 (Price) ---
    with st.container():
        st.markdown("### 🏷️ 1. 价格统计 (Price Metrics)")
        # 第一行：看主流
        c1, c2, c3 = st.columns(3)
        c1.metric("加权平均单价", f"¥{avg_price_weighted:,.0f}")
        c2.metric("中位数单价", f"¥{df['单价'].median():,.0f}")
        c3.metric("单笔最高价", f"¥{df['单价'].max():,.0f}")
        
        # 第二行：看分层
        c4, c5, c6 = st.columns(3)
        c4.metric("🔴 红海门槛 (Q1)", f"< ¥{p25:,.0f}", delta="Low", delta_color="inverse")
        c5.metric("🟢 蓝海门槛 (Q3)", f"> ¥{p75:,.0f}", delta="High")
        c6.write("") # 占位符，保持排版整齐

    st.divider()

    # --- 面板 2: 销量统计 (Volume) ---
    with st.container():
        st.markdown("### 📦 2. 销量统计 (Volume Metrics)")
        # 第一行：宏观总量
        v1, v2, v3 = st.columns(3)
        v1.metric("总出口销量", f"{total_vol:,.1f} 吨")
        v2.metric("单笔平均销量", f"{df['销量(吨)'].mean():,.2f} 吨")
        v3.metric("单笔最大销量", f"{df['销量(吨)'].max():,.1f} 吨")
        
        # 第二行：国家维度
        v4, v5, v6 = st.columns(3)
        mean_country_vol = country_stats['销量(吨)'].mean() if not country_stats.empty else 0
        max_country_vol = country_stats['销量(吨)'].max() if not country_stats.empty else 0
        
        v4.metric("国家平均总销量", f"{mean_country_vol:,.1f} 吨")
        v5.metric("国家最大总销量", f"{max_country_vol:,.1f} 吨")
        v6.write("") 

    st.divider()

    # --- 面板 3: 业绩/销售额统计 (Revenue) ---
    with st.container():
        st.markdown("### 💎 3. 业绩统计 (Revenue Metrics)")
        # 第一行：总账
        r1, r2, r3 = st.columns(3)
        r1.metric("总销售额", f"¥{total_rev/10000:,.1f} 万")
        r2.metric("平均客单价 (单笔)", f"¥{df['总销售额'].mean()/10000:,.2f} 万")
        r3.metric("最高客单价 (单笔)", f"¥{df['总销售额'].max()/10000:,.1f} 万")
        
        # 第二行：国家贡献
        r4, r5, r6 = st.columns(3)
        mean_country_rev = country_stats['总销售额'].mean() if not country_stats.empty else 0
        max_country_rev = country_stats['总销售额'].max() if not country_stats.empty else 0
        
        r4.metric("国家平均贡献额", f"¥{mean_country_rev/10000:,.1f} 万")
        r5.metric("国家最高贡献额", f"¥{max_country_rev/10000:,.1f} 万")
        r6.write("")

    st.divider()

    # ==========================================
    # 4. 图表分析区
    # ==========================================
    
    # Chart 1: 市场结构
    st.subheader("2. 市场结构全景")
    c_chart1, c_chart2 = st.columns([3, 2])
    with c_chart1:
        st.markdown("**🌍 全球定价矩阵**")
        fig_matrix = px.scatter(
            country_stats,
            x='单价', y='销量(吨)',
            size='总销售额',
            color='市场类型',
            color_discrete_map={'🔴 低价红海':'#EF553B', '🟢 高价蓝海':'#00CC96', '🟡 主流市场':'#636EFA'},
            hover_name='国家',
            log_y=True, 
            text='国家'
        )
        fig_matrix.add_vline(x=df['单价'].median(), line_dash="dash", line_color="gray", annotation_text="中位价")
        fig_matrix.add_hline(y=df['销量(吨)'].median(), line_dash="dash", line_color="gray", annotation_text="中位量")
        fig_matrix.update_traces(textposition='top center')
        st.plotly_chart(fig_matrix, use_container_width=True)
        
    with c_chart2:
        st.markdown("**🍰 市场销量份额**")
        pie_data = country_stats.groupby('市场类型')['销量(吨)'].sum().reset_index()
        fig_pie = px.pie(
            pie_data, values='销量(吨)', names='市场类型',
            color='市场类型',
            color_discrete_map={'🔴 低价红海':'#EF553B', '🟢 高价蓝海':'#00CC96', '🟡 主流市场':'#636EFA'},
            hole=0.4
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    # Chart 2: 排行榜 (含悬停数据)
    st.subheader("3. 机会与风险排行榜")
    rank_c1, rank_c2 = st.columns(2)
    
    with rank_c1:
        st.markdown("#### 🏆 高溢价蓝海 Top 10")
        top_df = country_stats.sort_values('单价', ascending=False).head(10)
        fig_top = px.bar(
            top_df, y='国家', x='单价', orientation='h', 
            text_auto='.0f', color='单价', color_continuous_scale='Reds',
            hover_data={'单价':':.0f', '销量(吨)':':.1f', '总销售额':':,.0f'}
        )
        fig_top.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_top, use_container_width=True)
        
    with rank_c2:
        st.markdown("#### 📉 低价红海 Top 10")
        bot_df = country_stats.sort_values('单价', ascending=True).head(10)
        bot_df_plot = bot_df.sort_values('单价', ascending=False)
        fig_bot = px.bar(
            bot_df_plot, y='国家', x='单价', orientation='h', 
            text_auto='.0f', color='单价', color_continuous_scale='Teal',
            hover_data={'单价':':.0f', '销量(吨)':':.1f', '总销售额':':,.0f'}
        )
        fig_bot.update_layout(yaxis={'categoryorder': 'array', 'categoryarray': bot_df['国家'].tolist()[::-1]})
        st.plotly_chart(fig_bot, use_container_width=True)

    # Chart 3: 箱线图
    st.subheader("4. 重点国家价格弹性 (Box Plot)")
    top_vol_countries = df.groupby('国家')['销量(吨)'].sum().nlargest(20).index
    df_box = df[df['国家'].isin(top_vol_countries)]
    sorted_idx = df_box.groupby('国家')['单价'].median().sort_values(ascending=False).index
    fig_box = px.box(
        df_box, x='国家', y='单价', color='国家', category_orders={'国家': sorted_idx}
    )
    fig_box.update_layout(showlegend=False, height=500)
    st.plotly_chart(fig_box, use_container_width=True)

    # ==========================================
    # 5. 下载按钮
    # ==========================================
    st.divider()
    with st.expander("📥 下载分析结果数据"):
        st.dataframe(country_stats)
        st.download_button(
            label="点击下载分析结果 CSV",
            data=country_stats.to_csv(index=False).encode('utf-8-sig'),
            file_name=f'{file_name}_analysis_report.csv',
            mime='text/csv'
        )

else:
    # 欢迎页
    st.markdown("""
    <div style='text-align: center; padding: 100px;'>
        <h1>👋 欢迎使用全球定价决策看板 v11.0</h1>
        <p style='font-size: 1.2em; color: grey;'>
            三维统计面板 | 深度图表分析 | 完整数据报表
        </p>
        <hr>
        <p>👈 请在左侧上传 CSV 或 Excel 数据文件</p>
    </div>
    """, unsafe_allow_html=True)
