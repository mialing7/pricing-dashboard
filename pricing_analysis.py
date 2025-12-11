import streamlit as st
import pandas as pd
import plotly.express as px

# --- 页面设置 ---
st.set_page_config(page_title="出口定价全景分析看板 v7.0", layout="wide", page_icon="🚢")

# --- 侧边栏：数据上传与筛选 ---
st.sidebar.title("📂 数据与筛选")

# 1. 上传
uploaded_file = st.sidebar.file_uploader("1. 上传数据文件 (CSV/Excel)", type=['csv', 'xlsx', 'xls'])

# --- 数据处理函数 ---
def load_and_process(file):
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
        return None, f"读取错误: {e}"

    # 清洗列名
    df.columns = df.columns.str.strip()
    
    # 智能映射列名
    col_map = {}
    for col in df.columns:
        if col in ['单价/每吨', '价格/每吨', '单价', 'Price']:
            col_map[col] = '单价'
        elif col in ['第二数量', '数量', 'Qty', 'Quantity']:
            col_map[col] = '销量(吨)'
        elif col in ['贸易伙伴名称', '国家', 'Country']:
            col_map[col] = '国家'
            
    df.rename(columns=col_map, inplace=True)
    
    # 检查必要列
    required = ['单价', '销量(吨)', '国家']
    if not all(c in df.columns for c in required):
        return None, f"缺少必要列，请确保文件包含: {required}"

    # 转换数值
    for c in ['单价', '销量(吨)']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    
    df = df.dropna(subset=['单价', '销量(吨)'])
    df = df[df['单价'] > 0]
    
    # 计算总销售额
    df['总销售额'] = df['单价'] * df['销量(吨)']
    
    return df, None

# --- 主界面逻辑 ---
if uploaded_file:
    df, err = load_and_process(uploaded_file)
    if err:
        st.error(err)
        st.stop()
        
    # --- 侧边栏：高级筛选 ---
    st.sidebar.divider()
    st.sidebar.subheader("2. 分析过滤器")
    
    # 筛选1: 极值处理
    use_iqr = st.sidebar.checkbox("剔除价格极值 (IQR算法)", value=True)
    if use_iqr:
        Q1 = df['单价'].quantile(0.25)
        Q3 = df['单价'].quantile(0.75)
        IQR = Q3 - Q1
        df = df[(df['单价'] >= Q1 - 1.5*IQR) & (df['单价'] <= Q3 + 1.5*IQR)]
        
    # 筛选2: 按客户总金额筛选
    country_total_sales = df.groupby('国家')['总销售额'].sum()
    min_sales_input = st.sidebar.number_input(
        "剔除小客户: 仅分析总销售额大于...", 
        min_value=0, 
        value=10000, 
        step=5000,
        help="剔除由于样品单或极小订单造成的干扰。"
    )
    
    valid_countries = country_total_sales[country_total_sales >= min_sales_input].index
    df = df[df['国家'].isin(valid_countries)]
    
    # 筛选3: 指定国家
    selected_countries = st.sidebar.multiselect("特定国家筛选", options=sorted(df['国家'].unique()))
    if selected_countries:
        df = df[df['国家'].isin(selected_countries)]

    # --- 顶部：业务解释 ---
    st.title(f"📊 {uploaded_file.name.split('.')[0]} - 深度定价分析报告")
    
    with st.expander("📖 **分析指南：如何使用本看板？(点击展开)**", expanded=False):
        st.markdown("""
        * **全球定价矩阵 (气泡图)：** * **横轴**=价格，**纵轴**=销量。
            * **气泡大小**=总销售额。寻找**右上角**（又贵又多）的“现金牛”国家。
        * **市场分层定义：**
            * 🔴 **红海 (Low End)：** 价格最低的 25% 订单，竞争最激烈。
            * 🟢 **蓝海 (High End)：** 价格最高的 25% 订单，高溢价区域。
            * 🟡 **主流 (Mainstream)：** 中间 50% 的大众市场。
        * **箱线图 (Box Plot)：** 展示一个国家的报价波动范围。箱子越长，说明价格弹性越大（既买便宜也买贵）。
        """)

    # --- 关键指标卡片 ---
    total_vol = df['销量(吨)'].sum()
    total_rev = df['总销售额'].sum()
    avg_price = total_rev / total_vol if total_vol > 0 else 0
    q1_price = df['单价'].quantile(0.25)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("加权平均单价", f"¥{avg_price:,.0f}")
    col2.metric("总销售额 (筛选后)", f"¥{total_rev/10000:,.1f} 万")
    col3.metric("红海警戒线 (<25%)", f"¥{q1_price:,.0f}", delta="低于此价需警惕", delta_color="inverse")
    col4.metric("有效样本量", f"{len(df)} 笔")
    
    st.divider()

    # --- 数据聚合 ---
    country_stats = df.groupby('国家').agg({
        '单价': 'median',
        '销量(吨)': 'sum',
        '总销售额': 'sum',
        '国家': 'count'
    }).rename(columns={'国家':'订单数'})
    
    country_stats.index.name = '国家'
    country_stats = country_stats.reset_index()

    # 划分市场类型
    p25 = df['单价'].quantile(0.25)
    p75 = df['单价'].quantile(0.75)
    def get_type(p):
        if p >= p75: return '🟢 高价蓝海'
        elif p <= p25: return '🔴 低价红海'
        else: return '🟡 主流市场'
    country_stats['市场类型'] = country_stats['单价'].apply(get_type)

    # --- 1. 定价矩阵 ---
    st.subheader("1. 全球定价矩阵 (Price-Volume Matrix)")
    fig_matrix = px.scatter(
        country_stats, x='单价', y='销量(吨)', size='总销售额', 
        color='市场类型',
        color_discrete_map={'🔴 低价红海':'#EF553B', '🟢 高价蓝海':'#00CC96', '🟡 主流市场':'#636EFA'},
        hover_name='国家', log_y=True, text='国家'
    )
    fig_matrix.add_vline(x=df['单价'].median(), line_dash="dash", line_color="gray", annotation_text="中位价")
    fig_matrix.add_hline(y=df['销量(吨)'].median(), line_dash="dash", line_color="gray", annotation_text="中位量")
    fig_matrix.update_traces(textposition='top center')
    st.plotly_chart(fig_matrix, use_container_width=True)

    # --- 2. 业务规模统计面板 ---
    st.subheader("2. 业务规模分布 (Statistics)")
    st.info("📊 辅助判断：我们的业务结构是靠“大客户”还是“散单”？")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**📦 销量统计 (Volume)**")
        v1, v2 = st.columns(2)
        v1.metric("单笔最大销量", f"{df['销量(吨)'].max():,.1f} 吨")
        v2.metric("国家最大总销量", f"{country_stats['销量(吨)'].max():,.1f} 吨")
    with c2:
        st.markdown("**💰 金额统计 (Revenue)**")
        m1, m2 = st.columns(2)
        m1.metric("单笔最大金额", f"¥{df['总销售额'].max()/10000:,.1f} 万")
        m2.metric("国家最大总金额", f"¥{country_stats['总销售额'].max()/10000:,.1f} 万")

    st.divider()

    # --- 3. 排行榜 ---
    st.subheader("3. 机会与风险 (Rankings)")
    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("#### 🏆 高溢价蓝海 (Top 10)")
        top_df = country_stats.sort_values('单价', ascending=False).head(10)
        fig_top = px.bar(top_df, y='国家', x='单价', orientation='h', color='单价', color_continuous_scale='Reds')
        fig_top.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_top, use_container_width=True)
    with col_r:
        st.markdown("#### 📉 低价红海 (Top 10)")
        bot_df = country_stats.sort_values('单价', ascending=True).head(10)
        fig_bot = px.bar(bot_df, y='国家', x='单价', orientation='h', color='单价', color_continuous_scale='Teal')
        fig_bot.update_layout(yaxis={'categoryorder':'total descending'}) 
        st.plotly_chart(fig_bot, use_container_width=True)

    # --- 4. 价格箱线图 (已加回!) ---
    st.subheader("4. 重点国家价格弹性 (Box Plot)")
    st.caption("箱子越长，代表该国价格波动越大（既有便宜也有贵），溢价机会通常也越大。")
    # 选取销量前20的国家进行分析
    top_countries = df.groupby('国家')['销量(吨)'].sum().nlargest(20).index
    df_box = df[df['国家'].isin(top_countries)]
    
    # 按中位价排序
    sorted_idx = df_box.groupby('国家')['单价'].median().sort_values(ascending=False).index
    
    fig_box = px.box(df_box, x='国家', y='单价', color='国家', category_orders={'国家': sorted_idx})
    fig_box.update_layout(showlegend=False)
    st.plotly_chart(fig_box, use_container_width=True)

    # --- 5. 数据下载 (已加回!) ---
    st.divider()
    with st.expander("📥 下载详细分析数据"):
        st.dataframe(country_stats)
        st.download_button(
            label="下载 CSV (含市场分级标签)",
            data=country_stats.to_csv(index=False).encode('utf-8-sig'),
            file_name=f'{uploaded_file.name}_analysis.csv',
            mime='text/csv'
        )

else:
    st.markdown("""
    <div style='text-align: center; padding: 80px;'>
        <h1>👋 欢迎使用定价决策看板 v7.0 (Final)</h1>
        <p>支持多品类数据分析 | 自动识别红海蓝海 | 辅助销售决策</p>
        <p style='color: gray; font-size: 0.9em;'>请在左侧上传 CSV 或 Excel 文件</p>
    </div>
    """, unsafe_allow_html=True)
