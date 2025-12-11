import streamlit as st
import pandas as pd
import plotly.express as px
import io

# --- 页面基本设置 ---
st.set_page_config(page_title="通用出口定价分析看板 (完美版)", layout="wide", page_icon="🚢")

# --- 侧边栏：上传数据 ---
st.sidebar.title("📂 数据导入")
st.sidebar.info("支持 CSV 或 Excel 文件。自动识别不锈钢/碳钢格式。")

uploaded_file = st.sidebar.file_uploader("请上传您的出口数据文件", type=['csv', 'xlsx', 'xls'])

# --- 核心函数：智能数据清洗 ---
def load_and_clean_data(file):
    # 1. 尝试读取文件
    try:
        if file.name.endswith('.csv'):
            try:
                df = pd.read_csv(file)
            except UnicodeDecodeError:
                file.seek(0)
                df = pd.read_csv(file, encoding='gbk')
        else:
            df = pd.read_excel(file)
    except Exception as e:
        return None, f"文件读取失败: {e}"

    # 2. 列名标准化
    df.columns = df.columns.str.strip()
    
    # 3. 智能寻找“单价”列
    price_col_candidates = ['单价/每吨', '价格/每吨', '单价', '价格', 'Price', 'Unit Price']
    found_price_col = None
    for col in df.columns:
        if col in price_col_candidates:
            found_price_col = col
            break
    if found_price_col:
        df.rename(columns={found_price_col: '单价/每吨'}, inplace=True)
    else:
        return None, f"❌ 找不到价格列！请确保文件里包含: {price_col_candidates}"

    # 4. 智能寻找“数量”列
    qty_col_candidates = ['第二数量', '数量', 'Quantity', 'Qty']
    found_qty_col = None
    for col in df.columns:
        if col in qty_col_candidates:
            found_qty_col = col
            break
    if found_qty_col:
        df.rename(columns={found_qty_col: '第二数量'}, inplace=True)
    else:
        return None, f"❌ 找不到数量列！请确保文件里包含: {qty_col_candidates}"

    # 5. 转换数值类型
    numeric_cols = ['单价/每吨', '第二数量', '人民币']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 6. 基础过滤
    df = df.dropna(subset=['单价/每吨', '第二数量'])
    df = df[df['单价/每吨'] > 0]
    
    return df, None

# --- 主逻辑 ---
if uploaded_file is not None:
    df_raw, error_msg = load_and_clean_data(uploaded_file)
    if error_msg:
        st.error(error_msg)
        st.stop()
        
    file_label = uploaded_file.name.split('.')[0]
    st.title(f"📊 {file_label} - 深度定价分析")

    # --- 侧边栏配置 ---
    st.sidebar.divider()
    st.sidebar.subheader("⚙️ 分析设置")
    
    # 1. 极值过滤
    use_iqr = st.sidebar.checkbox("剔除价格异常值 (IQR)", value=True)
    if use_iqr:
        Q1 = df_raw['单价/每吨'].quantile(0.25)
        Q3 = df_raw['单价/每吨'].quantile(0.75)
        IQR = Q3 - Q1
        lower = Q1 - 1.5 * IQR
        upper = Q3 + 1.5 * IQR
        df = df_raw[(df_raw['单价/每吨'] >= lower) & (df_raw['单价/每吨'] <= upper)]
        st.sidebar.caption(f"保留价格区间: {max(0, lower):.0f} - {upper:.0f}")
    else:
        df = df_raw.copy()

    # 2. 贸易伙伴筛选
    all_countries = sorted(df['贸易伙伴名称'].astype(str).unique())
    selected_countries = st.sidebar.multiselect("筛选贸易伙伴", all_countries)
    if selected_countries:
        df = df[df['贸易伙伴名称'].isin(selected_countries)]

    # --- 核心指标 ---
    col1, col2, col3, col4 = st.columns(4)
    avg_price = (df['人民币'].sum() / df['第二数量'].sum()) if '人民币' in df.columns else df['单价/每吨'].mean()
    median_price = df['单价/每吨'].median()
    low_threshold = df['单价/每吨'].quantile(0.25)
    
    col1.metric("加权平均价", f"¥{avg_price:,.0f}")
    col2.metric("中位数价格", f"¥{median_price:,.0f}")
    col3.metric("低端警戒线 (Bottom 25%)", f"¥{low_threshold:,.0f}", delta_color="inverse")
    col4.metric("分析样本量", f"{len(df)} 行")
    
    st.divider()

    # --- 聚合数据与分类 ---
    country_stats = df.groupby('贸易伙伴名称').agg({
        '单价/每吨': 'median',
        '第二数量': 'sum',
        '人民币': 'sum' if '人民币' in df.columns else 'count',
        '贸易伙伴名称': 'count' # 订单数
    }).rename(columns={'贸易伙伴名称':'订单数'}).reset_index()
    
    # 市场分类逻辑
    def classify(price):
        if price >= df['单价/每吨'].quantile(0.75): return '🟢 高端/溢价'
        elif price <= df['单价/每吨'].quantile(0.25): return '🔴 低端/红海'
        else: return '🟡 中端/主流'
    
    country_stats['类型'] = country_stats['单价/每吨'].apply(classify)
    country_stats = country_stats[country_stats['第二数量'] > 0] # 过滤0销量

    # --- 1. 市场结构与份额 (饼图 + 散点图) ---
    st.subheader("1. 市场结构全景")
    c1, c2 = st.columns([1, 2])
    
    with c1:
        # 补回饼图！
        market_share = country_stats.groupby('类型')['第二数量'].sum().reset_index()
        fig_pie = px.pie(market_share, values='第二数量', names='类型', title='各级市场销量占比',
                         color='类型',
                         color_discrete_map={'🔴 低端/红海':'#EF553B', '🟢 高端/溢价':'#00CC96', '🟡 中端/主流':'#636EFA'})
        st.plotly_chart(fig_pie, use_container_width=True)
        
    with c2:
        # 四象限图
        fig_scatter = px.scatter(
            country_stats, 
            x='单价/每吨', y='第二数量', 
            size='人民币' if '人民币' in df.columns else '第二数量',
            color='类型',
            color_discrete_map={'🔴 低端/红海':'#EF553B', '🟢 高端/溢价':'#00CC96', '🟡 中端/主流':'#636EFA'},
            hover_name='贸易伙伴名称', log_y=True,
            title=f"全球定价矩阵 (价格 vs 销量)"
        )
        fig_scatter.add_vline(x=median_price, line_dash="dash", line_color="gray", annotation_text="中位数")
        st.plotly_chart(fig_scatter, use_container_width=True)

    # --- 2. 价格排行 (Top & Bottom) ---
    st.subheader("2. 机会与风险 (Top 10)")
    col_l, col_r = st.columns(2)
    
    with col_l:
        st.caption("🏆 高溢价国家 (价格高，有销量)")
        top_df = country_stats.sort_values('单价/每吨', ascending=False).head(10)
        fig_top = px.bar(top_df, y='贸易伙伴名称', x='单价/每吨', orientation='h', color='单价/每吨', color_continuous_scale='Reds')
        fig_top.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_top, use_container_width=True)
        
    with col_r:
        st.caption("📉 低价红海国家 (价格卷，竞争大)")
        bot_df = country_stats.sort_values('单价/每吨', ascending=True).head(10)
        fig_bot = px.bar(bot_df, y='贸易伙伴名称', x='单价/每吨', orientation='h', color='单价/每吨', color_continuous_scale='Teal')
        fig_bot.update_layout(yaxis={'categoryorder':'total descending'})
        st.plotly_chart(fig_bot, use_container_width=True)

    # --- 3. 价格箱线图 ---
    st.subheader("3. 重点国家价格弹性 (Box Plot)")
    top_vol_countries = df.groupby('贸易伙伴名称')['第二数量'].sum().nlargest(15).index
    df_box = df[df['贸易伙伴名称'].isin(top_vol_countries)]
    
    # 按照中位数价格排序
    sorted_idx = df_box.groupby('贸易伙伴名称')['单价/每吨'].median().sort_values(ascending=False).index
    
    fig_box = px.box(df_box, x='贸易伙伴名称', y='单价/每吨', color='贸易伙伴名称', 
                     category_orders={'贸易伙伴名称': sorted_idx})
    fig_box.update_layout(showlegend=False)
    st.plotly_chart(fig_box, use_container_width=True)

    # --- 4. 数据下载 (补回功能) ---
    st.divider()
    with st.expander("📥 下载分析结果"):
        st.dataframe(country_stats)
        st.download_button(
            label="下载CSV (含市场分级标签)",
            data=country_stats.to_csv(index=False).encode('utf-8-sig'),
            file_name=f'{file_label}_analysis.csv',
            mime='text/csv'
        )

else:
    # --- 欢迎页面 ---
    st.markdown("""
    <div style='text-align: center; padding: 50px;'>
        <h1>👋 通用定价分析看板</h1>
        <p style='font-size: 1.2em; color: grey;'>
            <b>一站式分析工具</b><br>
            请在左侧上传不锈钢、碳钢或任意出口数据文件 (CSV/Excel)。
        </p>
    </div>
    """, unsafe_allow_html=True)
