import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# --- 页面基本设置 ---
st.set_page_config(page_title="不锈钢法兰定价分析看板 v3.0", layout="wide")

# --- 1. 数据加载与预处理 ---
@st.cache_data
def load_data():
    file_path = '不锈钢数据导出.xlsx'
    
    # 尝试多种方式读取，确保兼容性
    try:
        df = pd.read_csv(file_path)
    except Exception:
        try:
            df = pd.read_csv(file_path, encoding='gbk')
        except Exception:
            df = pd.read_excel(file_path)

    # 转换数值类型，处理异常
    numeric_cols = ['单价/每吨', '第二数量', '人民币']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 清洗：去除空值和0值
    df = df.dropna(subset=['单价/每吨', '第二数量'])
    df = df[df['单价/每吨'] > 0]
    
    return df

try:
    raw_df = load_data()
except Exception as e:
    st.error(f"数据加载失败，请检查文件名是否正确。错误信息: {e}")
    st.stop()

# --- 侧边栏：配置区 ---
st.sidebar.title("⚙️ 分析配置")

# 1. 极值处理
st.sidebar.subheader("1. 极值过滤 (IQR)")
enable_outlier = st.sidebar.checkbox("剔除价格异常极值", value=True)

if enable_outlier:
    Q1 = raw_df['单价/每吨'].quantile(0.25)
    Q3 = raw_df['单价/每吨'].quantile(0.75)
    IQR = Q3 - Q1
    lower_bound = Q1 - 1.5 * IQR
    upper_bound = Q3 + 1.5 * IQR
    df = raw_df[(raw_df['单价/每吨'] >= lower_bound) & (raw_df['单价/每吨'] <= upper_bound)]
    st.sidebar.caption(f"保留价格区间: {max(0, lower_bound):.0f} - {upper_bound:.0f} RMB")
else:
    df = raw_df.copy()

# 2. 筛选器
st.sidebar.subheader("2. 范围筛选")
selected_countries = st.sidebar.multiselect(
    "选择贸易伙伴", 
    options=df['贸易伙伴名称'].unique(),
    default=[] # 默认全选
)
if selected_countries:
    df = df[df['贸易伙伴名称'].isin(selected_countries)]

# --- 主页面 ---
st.title("🚀 不锈钢法兰：全球定价与市场分层看板")
st.markdown("识别 **高端溢价区** 与 **低端红海区**，辅助制定差异化报价策略。")

# 关键指标栏
col1, col2, col3, col4 = st.columns(4)
avg_price = df['人民币'].sum() / df['第二数量'].sum()
median_price = df['单价/每吨'].median()
low_end_threshold = df['单价/每吨'].quantile(0.25) # 定义低端市场的阈值

col1.metric("加权平均单价", f"¥{avg_price:,.0f}/吨")
col2.metric("中位数单价 (市场基准)", f"¥{median_price:,.0f}/吨")
col3.metric("📉 低端市场警戒线 (Bottom 25%)", f"¥{low_end_threshold:,.0f}/吨", delta_color="inverse")
col4.metric("总出口量", f"{df['第二数量'].sum():,.1f} 吨")

st.divider()

# 数据聚合准备
country_stats = df.groupby('贸易伙伴名称').agg({
    '单价/每吨': 'median',
    '第二数量': 'sum',
    '人民币': 'sum',
    '商品编码': 'count'
}).reset_index()

# 给国家打标签：高端 vs 低端
def categorize_market(price):
    if price >= df['单价/每吨'].quantile(0.75):
        return '🟢 高端/高溢价'
    elif price <= df['单价/每吨'].quantile(0.25):
        return '🔴 低端/红海竞争'
    else:
        return '🟡 中端/主流'

country_stats['市场类型'] = country_stats['单价/每吨'].apply(categorize_market)
country_stats_filtered = country_stats[country_stats['第二数量'] > 1] # 过滤极小销量

# --- 第一部分：低端市场分析 (New!) ---
st.header("📉 价格低端国家分析 (红海市场)")
st.info(f"💡 定义：平均单价低于 **¥{low_end_threshold:,.0f}/吨** 的市场。这些市场通常竞争激烈，以标准品走量为主。策略：严格控本，谨慎报价。")

col_low1, col_low2 = st.columns([1, 1])

with col_low1:
    st.subheader("低价“卷王”排行榜")
    # 筛选低端市场并按价格升序排列（越低越前）
    low_end_df = country_stats_filtered[country_stats_filtered['市场类型'] == '🔴 低端/红海竞争'].sort_values('单价/每吨', ascending=True).head(15)
    
    fig_low = px.bar(
        low_end_df,
        x='单价/每吨',
        y='贸易伙伴名称',
        orientation='h',
        text_auto='.0f',
        title="单价最低的 Top 15 国家 (价格洼地)",
        color='单价/每吨',
        color_continuous_scale='Teal' # 冷色调表示低价
    )
    fig_low.update_layout(yaxis={'categoryorder':'total descending'}) # 价格最低的在最上面
    st.plotly_chart(fig_low, use_container_width=True)

with col_low2:
    st.subheader("低端市场的销量贡献")
    # 看看低价市场占了多少量
    market_share = country_stats_filtered.groupby('市场类型')['第二数量'].sum().reset_index()
    fig_pie = px.pie(
        market_share, 
        values='第二数量', 
        names='市场类型', 
        title='各层级市场销量占比',
        color='市场类型',
        color_discrete_map={'🔴 低端/红海竞争':'#EF553B', '🟢 高端/高溢价':'#00CC96', '🟡 中端/主流':'#636EFA'}
    )
    st.plotly_chart(fig_pie, use_container_width=True)

# --- 第二部分：四象限全景分析 ---
st.header("🌍 全球市场四象限图")

fig_scatter = px.scatter(
    country_stats_filtered,
    x='单价/每吨',
    y='第二数量',
    size='人民币',
    color='市场类型', # 用我们刚才定义的标签上色
    color_discrete_map={'🔴 低端/红海竞争':'#EF553B', '🟢 高端/高溢价':'#00CC96', '🟡 中端/主流':'#636EFA'},
    hover_name='贸易伙伴名称',
    log_y=True, 
    text='贸易伙伴名称',
    title="价格 vs 销量 (颜色代表市场层级)"
)

# 添加辅助线
fig_scatter.add_vline(x=median_price, line_dash="dash", line_color="gray", annotation_text="中位价")
fig_scatter.add_vline(x=low_end_threshold, line_dash="dot", line_color="red", annotation_text="低价警戒线")
fig_scatter.update_traces(textposition='top center')
st.plotly_chart(fig_scatter, use_container_width=True)


# --- 第三部分：高端与价格弹性 (Box Plot) ---
st.header("📈 价格弹性分析 (Box Plot)")
st.caption("查看各国的价格波动范围。箱子越长，说明该国既有低价单也有高价单，机会更多。")

# 准备数据：销量前20国家
top_countries = df.groupby('贸易伙伴名称')['第二数量'].sum().nlargest(20).index
df_top = df[df['贸易伙伴名称'].isin(top_countries)]

# 排序
sorted_idx = df_top.groupby('贸易伙伴名称')['单价/每吨'].median().sort_values(ascending=False).index

fig_box = px.box(
    df_top, 
    x='贸易伙伴名称', 
    y='单价/每吨',
    color='贸易伙伴名称',
    category_orders={'贸易伙伴名称': sorted_idx},
    points="outliers"
)
fig_box.update_layout(showlegend=False, height=500)
st.plotly_chart(fig_box, use_container_width=True)

# --- 下载数据 ---
st.divider()
with st.expander("📥 下载分析结果数据"):
    st.write("你可以下载包含‘市场类型’标记的统计数据：")
    st.dataframe(country_stats_filtered)
    st.download_button(
        "下载 CSV",
        country_stats_filtered.to_csv(index=False).encode('utf-8-sig'),
        "market_segmentation.csv",
        "text/csv"
    )
