import streamlit as st
import pandas as pd
import datetime
import os
import matplotlib.pyplot as plt
import math
from streamlit_qrcode_scanner import qrcode_scanner

# read and load inventory data
@st.cache_data #缓存数据，避免每次运行都要重新加载数据
def load_inventory(file_path="inventory.xlsx"):
    return pd.read_excel(file_path)
# save cycle count results
def save_results(df, suffix="result"):
    today =datetime.date.today().strftime("%Y-%m-%d")
    file_name = f"cycle_count_{suffix}_{today}.xlsx"
    df.to_excel(file_name, index=False)
    return file_name

# generate 30 days plan
def generate_cycle_plan(inventory, days=30):
    plan = {}
    total =len(inventory)
    per_day = math.ceil(total / days)
    # 打乱顺序
    shuffled = inventory.sample(frac=1, random_state=42).reset_index(drop=True)# datafram.sample(frac=1)代表把数据整体打乱， random_sate=42代表每次运行结果一致， reset_index代表重新生成检索
    
    for d in range(days):
        start =d * per_day
        end = start + per_day
        plan[d+1] = shuffled.iloc[start:end]

    return plan

#---streamlit 页面----
st.set_page_config(page_title="Cycle Count 盘点系统", layout="wide")

st.title("📦 Cycle Count 盘点系统")
st.write("每天自动生成盘点任务, 支持扫码录入, 自动统计差异, 并可导出Excel报表")

# 加载库存
inventory = load_inventory()

#生成30天盘点计划
plan = generate_cycle_plan(inventory, days=30)

# 今天是第几天（简单用日期对30取余）
today = datetime.date.today()
day_index = (today.day % 30) or 30
daily_list = plan[day_index]

st.subheader(f"📅 今日盘点任务(Day {day_index}/30)")
st.dataframe(daily_list)

#保存清单
file = save_results(daily_list, "list")
st.info(f"今日盘点清单已生成: {file}")

#----扫码录入，输入实盘数据
st.subheader("📲 录入实盘数量（支持扫码输入 SKU)")

# 点击按钮触发扫码
if "show_scanner" not in st.session_state:
    st.session_state.show_scanner = False
if "scanner_id" not in st.session_state:
    st.session_state.scanner_id = 0

if st.button("📷 点击扫码录入 SKU"):
    st.session_state.show_scanner = True
    st.session_state.scanner_id += 1

#扫码界面
if st.session_state.show_scanner:
    qr_code = qrcode_scanner(key=f"qrcode_{st.session_state.scanner_id}")
    if qr_code:
        st.success(f"扫码成功: {qr_code}")
        st.session_state["last_scanned"] = qr_code
        st.session_state.show_scanner = False#扫码完成关闭界面

#扫码功能，先扫码，扫码结果缓存到st.session_state中
qr_code = qrcode_scanner(key="qrcode")
st.success(f"扫码成功: {qr_code}")
st.session_state["last_scanned"] = qr_code

#表单：手动输入/扫码输入 SKU+数量
with st.form("count_form"): #表示创建一个表单区域，在streamlit页面上创建一个名字叫count_form的表单区域
    default_sku = st.session_state.get("last_scanned", "") #返回之前存储的SKU，如果没有扫上就会返回空值
    sku_input = st.text_input("扫描/输入 SKU: ", value=default_sku)
    qty_input = st.number_input("实盘数量: ", min_value=0, step=1)
    submit = st.form_submit_button("提交记录")

if submit and sku_input:
    if "results" not in st.session_state:
        st.session_state.results = pd.DataFrame(columns=["SKU", "CountedQty"])

    new_row = pd.DataFrame({"SKU":[sku_input], "CountedQty":[qty_input]})
    st.session_state.results = pd.concat([st.session_state.results, new_row], ignore_index=True)
    st.success(f"已记录: {sku_input}-{qty_input}")

#显示已录入的数据
if "results" in st.session_state and not st.session_state.results.empty:
    st.subheader("📋 已录入盘点数据")
    st.dataframe(st.session_state.results)

    #生成差异报告+分析
    if st.button("生成盘点结果报告"): # st.button是streamlit中自带的UI，会自动产生一个按钮
        #统一SKU类型为字符串
        daily_list["SKU"] = daily_list["SKU"].astype(str)
        st.session_state.results["SKU"] = st.session_state.results["SKU"].astype(str)
       
        merged = daily_list.merge(st.session_state.results, on="SKU", how="left")
        merged["Variance"] = merged["CountedQty"] - merged["SystemQty"]

        file = save_results(merged, "final")
        st.success(f"📊 盘点结果已保存：{file}")
        st.dataframe(merged)

        #----导出Excel报表-----
        with open(file, "rb") as f: # with ... as .. 上下文链接的语句，用来读取文件，关闭文件用，rb表示已二进制的方式读取，excel,图片等都是二进制
            st.download_button(
                label="📥 点击下载盘点报表",
                data=f,
                file_name=file,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"#用来告诉浏览器这是什么类型的文档
            )
        
        #-----统计分析----
        st.subheader("📈 盘点分析")

        counted_mask = merged["CountedQty"].notna()
        total_counted = counted_mask.sum()
        correct_counted = ((merged["Variance"] == 0) & counted_mask).sum()
        accuracy = correct_counted / total_counted * 100 if total_counted > 0 else 0
        st.metric("盘点准确率", f"{accuracy:.2f}%")

        shortage = merged[merged["Variance"]<0].sort_values("Variance").head(5)
        overage = merged[merged["Variance"]>0].sort_values("Variance", ascending=False).head(5)
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("📉 缺货 Top SKU")
            st.dataframe(shortage[["SKU", "SystemQty", "CountedQty", "Variance"]])
        with col2:
            st.write("📈 多货 Top SKU")
            st.dataframe(overage[["SKU", "SystemQty", "CountedQty", "Variance"]])
        
        #差异可视化
        st.subheader("库存差异分布")
        fig, ax = plt.subplots()
        merged.set_index("SKU")["Variance"].plot(kind="bar", ax=ax)
        ax.set_ylabel("差异数量")
        ax.set_title("各SKU盘点差异")
        st.pyplot(fig)

        # 保存并提供下载
        plt.savefig("inventory_report.png", bbox_inches="tight")
        with open("inventory_report.png", "rb") as file:
            st.download_button(
                label="📎 下载盘点报告图表",
                data=file,
                file_name="inventory_report.png",
                mime="image/png"    
    )
        



