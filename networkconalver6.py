import streamlit as st
import pandas as pd
import altair as alt

# 페이지 기본 설정
st.set_page_config(page_title="여객노선부 연결 분석기", layout="wide")

st.title("연결 스케줄 확인 앱 VER.2")

# --- 모드 선택 ---
analysis_mode = st.radio(
    "분석 모드 선택",
    ["단일 스케줄 분석", "두 스케줄 비교 분석"],
    horizontal=True
)

# --- [NOTICE] 데이터 작성 가이드 ---
with st.expander("📢 [필독] 데이터 파일(CSV) 작성 양식 가이드", expanded=False):
    st.markdown("""
    ##### 1. 필수 컬럼
    * **SEASON**: 시즌 (예: S26)
    * **FLT NO**: 편명 (예: '081')
    * **ORGN**: 출발지 공항
    * **DEST** (또는 DESTINATION): 도착지 공항
    * **STD / STA**: 시간 (HH:MM)
    * **OPS**: 항공사 코드
    * **ROUTE**: 노선 구분 (예: 미주노선, 동남아노선) -> **그룹핑 기준 (필수)**
    * **구분**: `To ICN` (도착) / `From ICN` (출발)
    """)
    
    example_data = pd.DataFrame({
        'SEASON': ['S26'], 'FLT NO': ['081'],
        'ORGN': ['JFK'], 'DEST': ['ICN'],
        'STD': ['12:00'], 'STA': ['16:30'],
        'OPS': ['KE'], '구분': ['To ICN'],
        'ROUTE': ['미주노선']
    })
    st.dataframe(example_data, hide_index=True)

# --- 데이터 로드 함수 ---
@st.cache_data
def load_data(file):
    encodings = ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr']
    for enc in encodings:
        try:
            file.seek(0)
            df = pd.read_csv(file, encoding=enc)
            
            df.columns = df.columns.str.strip()
            if 'DESTINATION' in df.columns:
                df.rename(columns={'DESTINATION': 'DEST'}, inplace=True)

            required = ['OPS', 'FLT NO', '구분', 'STD', 'STA', 'ORGN', 'DEST', 'ROUTE']
            if not all(col in df.columns for col in required):
                continue
            
            for col in ['구분', 'FLT NO', 'ROUTE', 'OPS', 'ORGN', 'DEST']:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip()
                    
            return df
        except:
            continue
    raise ValueError("파일을 읽을 수 없습니다. 인코딩 문제이거나 필수 컬럼이 누락되었습니다.")

def time_to_minutes(t_str):
    try:
        h, m = map(int, t_str.split(':'))
        return h * 60 + m
    except:
        return None

# --- 분석 로직 ---
def analyze_connections_flexible(df, min_limit, max_limit, 
                               group_a_routes, group_a_ops, 
                               group_b_routes, group_b_ops):
    results = []
    
    def analyze_one_direction(start_routes, start_ops, end_routes, end_ops, direction_label):
        inbound = df[
            (df['ROUTE'].isin(start_routes)) & 
            (df['OPS'].isin(start_ops)) & 
            (df['구분'] == 'To ICN')
        ].copy()
        
        outbound = df[
            (df['ROUTE'].isin(end_routes)) & 
            (df['OPS'].isin(end_ops)) & 
            (df['구분'] == 'From ICN')
        ].copy()

        if inbound.empty or outbound.empty:
            return []

        local_results = []
        merged = pd.merge(inbound.assign(k=1), outbound.assign(k=1), on='k', suffixes=('_IN', '_OUT'))
        
        for _, row in merged.iterrows():
            arr = time_to_minutes(row['STA_IN'])
            dep = time_to_minutes(row['STD_OUT'])
            
            if arr is not None and dep is not None:
                diff = dep - arr
                if diff < 0: diff += 1440
                status = 'Connected' if min_limit <= diff <= max_limit else 'Disconnect'
                
                flt_in = f"{row['OPS_IN']}{row['FLT NO_IN']}"
                flt_out = f"{row['OPS_OUT']}{row['FLT NO_OUT']}"

                local_results.append({
                    'Direction': direction_label,
                    'Inbound_Route': row['ROUTE_IN'],
                    'Outbound_Route': row['ROUTE_OUT'],
                    'Inbound_OPS': row['OPS_IN'], 'Outbound_OPS': row['OPS_OUT'],
                    'Inbound_Flt_No': flt_in, 'Outbound_Flt_No': flt_out,
                    'From': row['ORGN_IN'], 
                    'Via': 'ICN', 
                    'To': row['DEST_OUT'],
                    'Inbound_Flight': f"[{flt_in}] {row['ORGN_IN']}->{row['DEST_IN']} (Arr {row['STA_IN']})",
                    'Outbound_Flight': f"[{flt_out}] {row['ORGN_OUT']}->{row['DEST_OUT']} (Dep {row['STD_OUT']})",
                    'Hub_Arr_Time': row['STA_IN'], 'Hub_Dep_Time': row['STD_OUT'],
                    'Arr_Min': arr, 'Dep_Min': dep,
                    'Arr_Hour': arr / 60.0, 
                    'Dep_Hour': dep / 60.0,
                    'Conn_Min': diff, 'Status': status
                })
        return local_results

    results.extend(analyze_one_direction(group_a_routes, group_a_ops, group_b_routes, group_b_ops, "Group A -> Group B"))

    is_same_group = set(group_a_routes) == set(group_b_routes) and set(group_a_ops) == set(group_b_ops)
    if not is_same_group:
        results.extend(analyze_one_direction(group_b_routes, group_b_ops, group_a_routes, group_a_ops, "Group B -> Group A"))

    cols = ['Direction', 'Inbound_Route', 'Outbound_Route', 'Inbound_OPS', 'Outbound_OPS', 'Inbound_Flt_No', 'Outbound_Flt_No', 'From', 'Via', 'To', 'Inbound_Flight', 'Outbound_Flight', 'Hub_Arr_Time', 'Hub_Dep_Time', 'Arr_Min', 'Dep_Min', 'Arr_Hour', 'Dep_Hour', 'Conn_Min', 'Status']
    if not results: return pd.DataFrame(columns=cols)
    return pd.DataFrame(results)[cols]


# --- 비교 분석 함수 ---
def compare_schedules(df1, df2, min_limit, max_limit, 
                      group_a_routes, group_a_ops, 
                      group_b_routes, group_b_ops):
    """두 스케줄의 연결 분석 결과를 비교"""
    
    # 각 스케줄 분석
    result1 = analyze_connections_flexible(df1, min_limit, max_limit, 
                                           group_a_routes, group_a_ops, 
                                           group_b_routes, group_b_ops)
    result2 = analyze_connections_flexible(df2, min_limit, max_limit, 
                                           group_a_routes, group_a_ops, 
                                           group_b_routes, group_b_ops)
    
    # 연결 쌍 식별을 위한 키 생성
    def create_connection_key(row):
        return f"{row['Inbound_Flt_No']}_{row['Outbound_Flt_No']}_{row['From']}_{row['To']}"
    
    if not result1.empty:
        result1['Connection_Key'] = result1.apply(create_connection_key, axis=1)
    else:
        result1['Connection_Key'] = []
        
    if not result2.empty:
        result2['Connection_Key'] = result2.apply(create_connection_key, axis=1)
    else:
        result2['Connection_Key'] = []
    
    # Connected 상태만 추출
    conn1 = set(result1[result1['Status'] == 'Connected']['Connection_Key'].tolist())
    conn2 = set(result2[result2['Status'] == 'Connected']['Connection_Key'].tolist())
    
    # 차이 분석
    only_in_1 = conn1 - conn2  # 스케줄1에만 있는 연결
    only_in_2 = conn2 - conn1  # 스케줄2에만 있는 연결
    common = conn1 & conn2     # 공통 연결
    
    # 상세 데이터프레임 생성
    lost_connections = result1[
        (result1['Connection_Key'].isin(only_in_1)) & 
        (result1['Status'] == 'Connected')
    ].copy()
    lost_connections['Change_Type'] = '🔴 스케줄2에서 사라짐'
    
    new_connections = result2[
        (result2['Connection_Key'].isin(only_in_2)) & 
        (result2['Status'] == 'Connected')
    ].copy()
    new_connections['Change_Type'] = '🟢 스케줄2에서 새로 생김'
    
    # 공통 연결의 시간 변화 분석
    common_df1 = result1[
        (result1['Connection_Key'].isin(common)) & 
        (result1['Status'] == 'Connected')
    ][['Connection_Key', 'Conn_Min', 'Hub_Arr_Time', 'Hub_Dep_Time']].copy()
    common_df1.columns = ['Connection_Key', 'Conn_Min_1', 'Arr_Time_1', 'Dep_Time_1']
    
    common_df2 = result2[
        (result2['Connection_Key'].isin(common)) & 
        (result2['Status'] == 'Connected')
    ][['Connection_Key', 'Conn_Min', 'Hub_Arr_Time', 'Hub_Dep_Time']].copy()
    common_df2.columns = ['Connection_Key', 'Conn_Min_2', 'Arr_Time_2', 'Dep_Time_2']
    
    time_changes = pd.merge(common_df1, common_df2, on='Connection_Key')
    time_changes['Time_Diff'] = time_changes['Conn_Min_2'] - time_changes['Conn_Min_1']
    time_changes = time_changes[time_changes['Time_Diff'] != 0]  # 변화 있는 것만
    
    return {
        'result1': result1,
        'result2': result2,
        'lost_connections': lost_connections,
        'new_connections': new_connections,
        'time_changes': time_changes,
        'stats': {
            'total_conn_1': len(conn1),
            'total_conn_2': len(conn2),
            'lost': len(only_in_1),
            'new': len(only_in_2),
            'common': len(common),
            'time_changed': len(time_changes)
        }
    }


def compare_flights(df1, df2):
    """두 스케줄의 항공편 자체를 비교"""
    
    def create_flight_key(row):
        return f"{row['OPS']}{row['FLT NO']}_{row['ORGN']}_{row['DEST']}"
    
    df1_copy = df1.copy()
    df2_copy = df2.copy()
    
    df1_copy['Flight_Key'] = df1_copy.apply(create_flight_key, axis=1)
    df2_copy['Flight_Key'] = df2_copy.apply(create_flight_key, axis=1)
    
    flights1 = set(df1_copy['Flight_Key'].tolist())
    flights2 = set(df2_copy['Flight_Key'].tolist())
    
    only_in_1 = flights1 - flights2
    only_in_2 = flights2 - flights1
    common = flights1 & flights2
    
    # 삭제된 항공편
    removed_flights = df1_copy[df1_copy['Flight_Key'].isin(only_in_1)].copy()
    removed_flights['Change_Type'] = '🔴 삭제됨'
    
    # 신규 항공편
    added_flights = df2_copy[df2_copy['Flight_Key'].isin(only_in_2)].copy()
    added_flights['Change_Type'] = '🟢 신규'
    
    # 시간 변경된 항공편
    common_df1 = df1_copy[df1_copy['Flight_Key'].isin(common)][['Flight_Key', 'STD', 'STA', 'OPS', 'FLT NO', 'ORGN', 'DEST', 'ROUTE', '구분']].copy()
    common_df2 = df2_copy[df2_copy['Flight_Key'].isin(common)][['Flight_Key', 'STD', 'STA']].copy()
    
    merged = pd.merge(common_df1, common_df2, on='Flight_Key', suffixes=('_OLD', '_NEW'))
    time_changed = merged[
        (merged['STD_OLD'] != merged['STD_NEW']) | 
        (merged['STA_OLD'] != merged['STA_NEW'])
    ].copy()
    time_changed['Change_Type'] = '🟡 시간 변경'
    
    return {
        'removed': removed_flights,
        'added': added_flights,
        'time_changed': time_changed,
        'stats': {
            'total_1': len(flights1),
            'total_2': len(flights2),
            'removed': len(only_in_1),
            'added': len(only_in_2),
            'common': len(common),
            'time_changed': len(time_changed)
        }
    }


# ==================== 단일 스케줄 분석 모드 ====================
if analysis_mode == "단일 스케줄 분석":
    st.sidebar.header("⚙️ 분석 설정")
    uploaded_file = st.sidebar.file_uploader("📂 데이터 파일 (CSV)", type="csv")

    if uploaded_file is not None:
        try:
            df = load_data(uploaded_file)
            st.sidebar.success(f"✅ 파일 로드: {len(df)}건")
            
            all_routes = sorted(df['ROUTE'].unique().tolist())
            all_ops = sorted(df['OPS'].unique().tolist())
            
            st.sidebar.markdown("---")
            st.sidebar.subheader("📌 노선 그룹 매칭")
            
            default_route_a = [all_routes[0]] if all_routes else None
            if "미주노선" in all_routes:
                default_route_a = ["미주노선"]
                
            routes_a = st.sidebar.multiselect("그룹 A 노선 선택", all_routes, default=default_route_a, key='ra')
            ops_a = st.sidebar.multiselect("그룹 A 항공사 선택", all_ops, default=all_ops, key='oa')
            
            st.sidebar.markdown("⬇️ ⬆️")
            
            default_route_b = [all_routes[1]] if len(all_routes) > 1 else all_routes
            if "동남아노선" in all_routes and "미주노선" in all_routes:
                 default_route_b = ["동남아노선"]

            routes_b = st.sidebar.multiselect("그룹 B 노선 선택", all_routes, default=default_route_b, key='rb')
            ops_b = st.sidebar.multiselect("그룹 B 항공사 선택", all_ops, default=all_ops, key='ob')
            
            st.sidebar.markdown("---")
            min_mct = st.sidebar.number_input("Min CT (분)", 0, 300, 60, 5)
            max_ct = st.sidebar.number_input("Max CT (분)", 60, 2880, 300, 60)
            
            if st.button("🚀 분석 시작", type="primary"):
                if not routes_a or not routes_b:
                    st.error("그룹 노선을 선택해주세요.")
                else:
                    with st.spinner("분석 중..."):
                        result_df = analyze_connections_flexible(df, min_mct, max_ct, routes_a, ops_a, routes_b, ops_b)
                        st.session_state['analysis_result'] = result_df
                        st.session_state['analysis_done'] = True
                        st.session_state['group_names'] = (", ".join(routes_a), ", ".join(routes_b))

            if 'analysis_done' in st.session_state and st.session_state['analysis_done']:
                result_df = st.session_state['analysis_result']
                g_name_a, g_name_b = st.session_state.get('group_names', ("A", "B"))
                
                if result_df.empty:
                    st.warning("조건에 맞는 연결편이 없습니다.")
                else:
                    tab1, tab2, tab3 = st.tabs(["📊 결과 요약", "📋 상세 리스트", "✈️ 공항별 심층 분석"])
                    
                    with tab1:
                        st.info(f"💡 **분석 기준**: [{g_name_a}] ↔ [{g_name_b}]")
                        
                        st.markdown("#### 1️⃣ 노선/항공사별 통합 연결 상세")
                        
                        combined_summary = result_df.groupby([
                            'Inbound_Route', 'Inbound_OPS', 
                            'Outbound_Route', 'Outbound_OPS', 
                            'Status'
                        ]).size().unstack(fill_value=0)
                        
                        if 'Connected' not in combined_summary.columns:
                            combined_summary['Connected'] = 0
                        if 'Disconnect' not in combined_summary.columns:
                            combined_summary['Disconnect'] = 0
                            
                        combined_summary['Total'] = combined_summary['Connected'] + combined_summary['Disconnect']
                        combined_summary = combined_summary.sort_values(by='Connected', ascending=False)
                        
                        st.dataframe(combined_summary, use_container_width=True)
                        
                        st.markdown("---")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("##### 2️⃣ 전체 방향별 합계")
                            st.dataframe(result_df.groupby(['Direction', 'Status']).size().unstack(fill_value=0), use_container_width=True)
                        with col2:
                            st.markdown("##### 3️⃣ 평균 연결 시간 (Connected 기준)")
                            connected = result_df[result_df['Status']=='Connected']
                            if not connected.empty:
                                st.dataframe(connected.groupby('Direction')['Conn_Min'].mean().round(1), use_container_width=True)

                    with tab2:
                        st.markdown("#### 상세 연결 리스트")
                        status_filter = st.multiselect("상태 필터", ['Connected', 'Disconnect'], default=['Connected'], key='sf')
                        view_df = result_df[result_df['Status'].isin(status_filter)].sort_values(['Direction', 'Conn_Min'])
                        st.dataframe(view_df, use_container_width=True, hide_index=True)
                        csv = view_df.to_csv(index=False).encode('utf-8-sig')
                        st.download_button("💾 CSV 다운로드", csv, "connection_analysis.csv", "text/csv")

                    with tab3:
                        st.markdown("### 🏙️ 공항 기준 연결성 분석")
                        
                        src_a = result_df[result_df['Direction'] == 'Group A -> Group B']['From'].unique()
                        dst_a = result_df[result_df['Direction'] == 'Group B -> Group A']['To'].unique()
                        
                        candidates = set(src_a) | set(dst_a)
                        if 'ICN' in candidates: candidates.remove('ICN')
                        airport_list = sorted(list(candidates))
                        
                        if not airport_list:
                            st.info("차트를 그릴 수 있는 공항 데이터가 없습니다.")
                        else:
                            st.markdown(f"**그룹 A ({g_name_a}) 소속 공항 선택**")
                            selected_airport = st.selectbox("📍 공항 선택", airport_list)
                            connected_data = result_df[result_df['Status']=='Connected']
                            
                            c1, c2 = st.columns(2)
                            
                            with c1:
                                st.markdown(f"#### 🛫 {selected_airport} → 그룹 B")
                                out_df = connected_data[
                                    (connected_data['Direction'] == 'Group A -> Group B') & 
                                    (connected_data['From'] == selected_airport)
                                ].sort_values('Conn_Min')
                                
                                if out_df.empty:
                                    st.info("연결편 없음")
                                else:
                                    base_chart = alt.Chart(out_df).mark_circle(size=120).encode(
                                        x=alt.X('To', title='도착지 (그룹 B)'),
                                        y=alt.Y('Conn_Min', title='연결 시간(분)'),
                                        color=alt.Color('Inbound_Flt_No', title='ICN 도착편명', legend=alt.Legend(orient='bottom')),
                                        tooltip=['To', 'Conn_Min', 'Inbound_Flt_No', 'Outbound_Flt_No', 'Hub_Arr_Time', 'Hub_Dep_Time']
                                    ).properties(height=350, title="목적지별 연결 시간 분포").interactive()
                                    st.altair_chart(base_chart, use_container_width=True)
                                    
                                    st.markdown("##### ⏱️ Hub 출/도착 시간 분포 (24h)")
                                    time_chart = alt.Chart(out_df).mark_circle(size=100).encode(
                                        x=alt.X('Arr_Hour', title='ICN 도착 시간 (시)', scale=alt.Scale(domain=[0, 24], nice=False)),
                                        y=alt.Y('Dep_Hour', title='ICN 출발 시간 (시)', scale=alt.Scale(domain=[0, 24], nice=False)),
                                        color=alt.Color('Inbound_Flt_No', legend=None),
                                        tooltip=[
                                            alt.Tooltip('To', title='도착지'),
                                            alt.Tooltip('Inbound_Flt_No', title='ICN 도착편명'),
                                            alt.Tooltip('Hub_Arr_Time', title='ICN 도착시간'),
                                            alt.Tooltip('Outbound_Flt_No', title='ICN 출발편명'),
                                            alt.Tooltip('Hub_Dep_Time', title='ICN 출발시간'),
                                            alt.Tooltip('Conn_Min', title='연결시간(분)')
                                        ]
                                    ).properties(height=350).interactive()
                                    st.altair_chart(time_chart, use_container_width=True)

                            with c2:
                                st.markdown(f"#### 🛬 그룹 B → {selected_airport}")
                                in_df = connected_data[
                                    (connected_data['Direction'] == 'Group B -> Group A') & 
                                    (connected_data['To'] == selected_airport)
                                ].sort_values('Conn_Min')
                                
                                if in_df.empty:
                                    st.info("연결편 없음")
                                else:
                                    base_chart = alt.Chart(in_df).mark_circle(size=120).encode(
                                        x=alt.X('From', title='출발지 (그룹 B)'),
                                        y=alt.Y('Conn_Min', title='연결 시간(분)'),
                                        color=alt.Color('Outbound_Flt_No', title='ICN 출발편명', legend=alt.Legend(orient='bottom')),
                                        tooltip=['From', 'Conn_Min', 'Inbound_Flt_No', 'Outbound_Flt_No', 'Hub_Arr_Time', 'Hub_Dep_Time']
                                    ).properties(height=350, title="출발지별 연결 시간 분포").interactive()
                                    st.altair_chart(base_chart, use_container_width=True)
                                    
                                    st.markdown("##### ⏱️ Hub 출/도착 시간 분포 (24h)")
                                    time_chart = alt.Chart(in_df).mark_circle(size=100).encode(
                                        x=alt.X('Arr_Hour', title='ICN 도착 시간 (시)', scale=alt.Scale(domain=[0, 24], nice=False)),
                                        y=alt.Y('Dep_Hour', title='ICN 출발 시간 (시)', scale=alt.Scale(domain=[0, 24], nice=False)),
                                        color=alt.Color('Outbound_Flt_No', legend=None),
                                        tooltip=[
                                            alt.Tooltip('From', title='출발지'),
                                            alt.Tooltip('Inbound_Flt_No', title='ICN 도착편명'),
                                            alt.Tooltip('Hub_Arr_Time', title='ICN 도착시간'),
                                            alt.Tooltip('Outbound_Flt_No', title='ICN 출발편명'),
                                            alt.Tooltip('Hub_Dep_Time', title='ICN 출발시간'),
                                            alt.Tooltip('Conn_Min', title='연결시간(분)')
                                        ]
                                    ).properties(height=350).interactive()
                                    st.altair_chart(time_chart, use_container_width=True)

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
    else:
        if 'analysis_done' in st.session_state:
            del st.session_state['analysis_done']
            del st.session_state['analysis_result']
        st.info("👈 파일을 업로드하고 분석을 시작하세요.")


# ==================== 두 스케줄 비교 분석 모드 ====================
elif analysis_mode == "두 스케줄 비교 분석":
    st.sidebar.header("⚙️ 비교 분석 설정")
    
    st.sidebar.markdown("### 📁 스케줄 파일 업로드")
    file1 = st.sidebar.file_uploader("📂 스케줄 1 (기준/Before)", type="csv", key="file1")
    file2 = st.sidebar.file_uploader("📂 스케줄 2 (비교/After)", type="csv", key="file2")
    
    if file1 is not None and file2 is not None:
        try:
            df1 = load_data(file1)
            df2 = load_data(file2)
            
            st.sidebar.success(f"✅ 스케줄 1: {len(df1)}건")
            st.sidebar.success(f"✅ 스케줄 2: {len(df2)}건")
            
            # 두 파일의 노선/항공사 통합
            all_routes = sorted(set(df1['ROUTE'].unique().tolist() + df2['ROUTE'].unique().tolist()))
            all_ops = sorted(set(df1['OPS'].unique().tolist() + df2['OPS'].unique().tolist()))
            
            st.sidebar.markdown("---")
            st.sidebar.subheader("📌 노선 그룹 매칭")
            
            default_route_a = [all_routes[0]] if all_routes else None
            if "미주노선" in all_routes:
                default_route_a = ["미주노선"]
                
            routes_a = st.sidebar.multiselect("그룹 A 노선 선택", all_routes, default=default_route_a, key='cmp_ra')
            ops_a = st.sidebar.multiselect("그룹 A 항공사 선택", all_ops, default=all_ops, key='cmp_oa')
            
            st.sidebar.markdown("⬇️ ⬆️")
            
            default_route_b = [all_routes[1]] if len(all_routes) > 1 else all_routes
            if "동남아노선" in all_routes and "미주노선" in all_routes:
                default_route_b = ["동남아노선"]

            routes_b = st.sidebar.multiselect("그룹 B 노선 선택", all_routes, default=default_route_b, key='cmp_rb')
            ops_b = st.sidebar.multiselect("그룹 B 항공사 선택", all_ops, default=all_ops, key='cmp_ob')
            
            st.sidebar.markdown("---")
            min_mct = st.sidebar.number_input("Min CT (분)", 0, 300, 60, 5, key='cmp_min')
            max_ct = st.sidebar.number_input("Max CT (분)", 60, 2880, 300, 60, key='cmp_max')
            
            if st.button("🔍 비교 분석 시작", type="primary"):
                if not routes_a or not routes_b:
                    st.error("그룹 노선을 선택해주세요.")
                else:
                    with st.spinner("비교 분석 중..."):
                        # 연결 비교
                        conn_comparison = compare_schedules(
                            df1, df2, min_mct, max_ct,
                            routes_a, ops_a, routes_b, ops_b
                        )
                        # 항공편 비교
                        flight_comparison = compare_flights(df1, df2)
                        
                        st.session_state['conn_comparison'] = conn_comparison
                        st.session_state['flight_comparison'] = flight_comparison
                        st.session_state['comparison_done'] = True
                        st.session_state['cmp_group_names'] = (", ".join(routes_a), ", ".join(routes_b))
            
            if 'comparison_done' in st.session_state and st.session_state['comparison_done']:
                conn_cmp = st.session_state['conn_comparison']
                flt_cmp = st.session_state['flight_comparison']
                g_name_a, g_name_b = st.session_state.get('cmp_group_names', ("A", "B"))
                
                tab1, tab2, tab3, tab4 = st.tabs([
                    "📊 비교 요약", 
                    "✈️ 항공편 변경", 
                    "🔗 연결 변경", 
                    "⏱️ 시간 변경 상세"
                ])
                
                with tab1:
                    st.markdown("## 📊 스케줄 비교 요약")
                    st.info(f"💡 **분석 기준**: [{g_name_a}] ↔ [{g_name_b}]")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("### ✈️ 항공편 변경 요약")
                        flt_stats = flt_cmp['stats']
                        
                        m1, m2, m3 = st.columns(3)
                        m1.metric("스케줄 1 항공편", flt_stats['total_1'])
                        m2.metric("스케줄 2 항공편", flt_stats['total_2'])
                        m3.metric("차이", flt_stats['total_2'] - flt_stats['total_1'], 
                                 delta_color="normal")
                        
                        st.markdown("#### 변경 내역")
                        change_data = pd.DataFrame({
                            '구분': ['🔴 삭제된 항공편', '🟢 신규 항공편', '🟡 시간 변경'],
                            '건수': [flt_stats['removed'], flt_stats['added'], flt_stats['time_changed']]
                        })
                        st.dataframe(change_data, hide_index=True, use_container_width=True)
                    
                    with col2:
                        st.markdown("### 🔗 연결 변경 요약")
                        conn_stats = conn_cmp['stats']
                        
                        m1, m2, m3 = st.columns(3)
                        m1.metric("스케줄 1 연결", conn_stats['total_conn_1'])
                        m2.metric("스케줄 2 연결", conn_stats['total_conn_2'])
                        m3.metric("차이", conn_stats['total_conn_2'] - conn_stats['total_conn_1'],
                                 delta_color="normal")
                        
                        st.markdown("#### 변경 내역")
                        conn_change_data = pd.DataFrame({
                            '구분': ['🔴 사라진 연결', '🟢 새로운 연결', '🟡 시간 변경'],
                            '건수': [conn_stats['lost'], conn_stats['new'], conn_stats['time_changed']]
                        })
                        st.dataframe(conn_change_data, hide_index=True, use_container_width=True)
                    
                    # 시각화
                    st.markdown("---")
                    st.markdown("### 📈 변경 시각화")
                    
                    viz_col1, viz_col2 = st.columns(2)
                    
                    with viz_col1:
                        # 항공편 변경 차트
                        flt_chart_data = pd.DataFrame({
                            'Category': ['삭제', '신규', '시간변경'],
                            'Count': [flt_stats['removed'], flt_stats['added'], flt_stats['time_changed']],
                            'Type': ['항공편'] * 3
                        })
                        
                        chart = alt.Chart(flt_chart_data).mark_bar().encode(
                            x=alt.X('Category', title='변경 유형', sort=['삭제', '신규', '시간변경']),
                            y=alt.Y('Count', title='건수'),
                            color=alt.Color('Category', scale=alt.Scale(
                                domain=['삭제', '신규', '시간변경'],
                                range=['#ff6b6b', '#51cf66', '#ffd43b']
                            ), legend=None)
                        ).properties(title='항공편 변경', height=250)
                        st.altair_chart(chart, use_container_width=True)
                    
                    with viz_col2:
                        # 연결 변경 차트
                        conn_chart_data = pd.DataFrame({
                            'Category': ['사라짐', '새로생김', '시간변경'],
                            'Count': [conn_stats['lost'], conn_stats['new'], conn_stats['time_changed']],
                            'Type': ['연결'] * 3
                        })
                        
                        chart = alt.Chart(conn_chart_data).mark_bar().encode(
                            x=alt.X('Category', title='변경 유형', sort=['사라짐', '새로생김', '시간변경']),
                            y=alt.Y('Count', title='건수'),
                            color=alt.Color('Category', scale=alt.Scale(
                                domain=['사라짐', '새로생김', '시간변경'],
                                range=['#ff6b6b', '#51cf66', '#ffd43b']
                            ), legend=None)
                        ).properties(title='연결 변경', height=250)
                        st.altair_chart(chart, use_container_width=True)
                
                with tab2:
                    st.markdown("## ✈️ 항공편 변경 상세")
                    
                    sub_tab1, sub_tab2, sub_tab3 = st.tabs(["🔴 삭제된 항공편", "🟢 신규 항공편", "🟡 시간 변경"])
                    
                    with sub_tab1:
                        if flt_cmp['removed'].empty:
                            st.info("삭제된 항공편이 없습니다.")
                        else:
                            st.dataframe(
                                flt_cmp['removed'][['OPS', 'FLT NO', 'ORGN', 'DEST', 'STD', 'STA', 'ROUTE', '구분']],
                                hide_index=True, use_container_width=True
                            )
                            csv = flt_cmp['removed'].to_csv(index=False).encode('utf-8-sig')
                            st.download_button("💾 삭제 항공편 CSV", csv, "removed_flights.csv", "text/csv")
                    
                    with sub_tab2:
                        if flt_cmp['added'].empty:
                            st.info("신규 항공편이 없습니다.")
                        else:
                            st.dataframe(
                                flt_cmp['added'][['OPS', 'FLT NO', 'ORGN', 'DEST', 'STD', 'STA', 'ROUTE', '구분']],
                                hide_index=True, use_container_width=True
                            )
                            csv = flt_cmp['added'].to_csv(index=False).encode('utf-8-sig')
                            st.download_button("💾 신규 항공편 CSV", csv, "added_flights.csv", "text/csv")
                    
                    with sub_tab3:
                        if flt_cmp['time_changed'].empty:
                            st.info("시간이 변경된 항공편이 없습니다.")
                        else:
                            display_cols = ['OPS', 'FLT NO', 'ORGN', 'DEST', 'ROUTE', '구분', 
                                          'STD_OLD', 'STD_NEW', 'STA_OLD', 'STA_NEW']
                            st.dataframe(
                                flt_cmp['time_changed'][display_cols],
                                hide_index=True, use_container_width=True
                            )
                            csv = flt_cmp['time_changed'].to_csv(index=False).encode('utf-8-sig')
                            st.download_button("💾 시간변경 항공편 CSV", csv, "time_changed_flights.csv", "text/csv")
                
                with tab3:
                    st.markdown("## 🔗 연결 변경 상세")
                    
                    sub_tab1, sub_tab2 = st.tabs(["🔴 사라진 연결", "🟢 새로운 연결"])
                    
                    with sub_tab1:
                        lost = conn_cmp['lost_connections']
                        if lost.empty:
                            st.info("사라진 연결이 없습니다.")
                        else:
                            st.markdown(f"**총 {len(lost)}건의 연결이 스케줄 2에서 사라졌습니다.**")
                            display_cols = ['Direction', 'From', 'Via', 'To', 
                                          'Inbound_Flt_No', 'Outbound_Flt_No',
                                          'Hub_Arr_Time', 'Hub_Dep_Time', 'Conn_Min']
                            st.dataframe(lost[display_cols], hide_index=True, use_container_width=True)
                            csv = lost.to_csv(index=False).encode('utf-8-sig')
                            st.download_button("💾 사라진 연결 CSV", csv, "lost_connections.csv", "text/csv")
                    
                    with sub_tab2:
                        new = conn_cmp['new_connections']
                        if new.empty:
                            st.info("새로운 연결이 없습니다.")
                        else:
                            st.markdown(f"**총 {len(new)}건의 연결이 스케줄 2에서 새로 생겼습니다.**")
                            display_cols = ['Direction', 'From', 'Via', 'To', 
                                          'Inbound_Flt_No', 'Outbound_Flt_No',
                                          'Hub_Arr_Time', 'Hub_Dep_Time', 'Conn_Min']
                            st.dataframe(new[display_cols], hide_index=True, use_container_width=True)
                            csv = new.to_csv(index=False).encode('utf-8-sig')
                            st.download_button("💾 새로운 연결 CSV", csv, "new_connections.csv", "text/csv")
                
                with tab4:
                    st.markdown("## ⏱️ 연결 시간 변경 상세")
                    
                    time_changes = conn_cmp['time_changes']
                    
                    if time_changes.empty:
                        st.info("연결 시간이 변경된 항목이 없습니다.")
                    else:
                        st.markdown(f"**총 {len(time_changes)}건의 연결에서 시간이 변경되었습니다.**")
                        
                        # 필터
                        filter_col1, filter_col2 = st.columns(2)
                        with filter_col1:
                            show_increased = st.checkbox("⬆️ 연결시간 증가", value=True)
                        with filter_col2:
                            show_decreased = st.checkbox("⬇️ 연결시간 감소", value=True)
                        
                        filtered = time_changes.copy()
                        if not show_increased:
                            filtered = filtered[filtered['Time_Diff'] <= 0]
                        if not show_decreased:
                            filtered = filtered[filtered['Time_Diff'] >= 0]
                        
                        # 정렬
                        filtered = filtered.sort_values('Time_Diff', ascending=False)
                        
                        # 표시
                        display_df = filtered.copy()
                        display_df['변화'] = display_df['Time_Diff'].apply(
                            lambda x: f"⬆️ +{x}분" if x > 0 else f"⬇️ {x}분"
                        )
                        
                        st.dataframe(
                            display_df[['Connection_Key', 'Arr_Time_1', 'Arr_Time_2', 
                                       'Dep_Time_1', 'Dep_Time_2', 'Conn_Min_1', 'Conn_Min_2', '변화']],
                            hide_index=True, use_container_width=True
                        )
                        
                        # 시각화
                        st.markdown("### 📈 연결 시간 변화 분포")
                        
                        hist_chart = alt.Chart(time_changes).mark_bar().encode(
                            x=alt.X('Time_Diff:Q', bin=alt.Bin(maxbins=20), title='시간 변화 (분)'),
                            y=alt.Y('count()', title='건수'),
                            color=alt.condition(
                                alt.datum.Time_Diff > 0,
                                alt.value('#51cf66'),  # 증가: 녹색
                                alt.value('#ff6b6b')   # 감소: 빨강
                            )
                        ).properties(height=300, title='연결 시간 변화 분포')
                        st.altair_chart(hist_chart, use_container_width=True)
                        
                        csv = time_changes.to_csv(index=False).encode('utf-8-sig')
                        st.download_button("💾 시간 변경 CSV", csv, "time_changes.csv", "text/csv")
                        
        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
            import traceback
            st.code(traceback.format_exc())
    else:
        if 'comparison_done' in st.session_state:
            del st.session_state['comparison_done']
        st.info("👈 두 개의 스케줄 파일을 업로드하고 비교 분석을 시작하세요.")
        
        st.markdown("""
        ### 📌 비교 분석 기능 안내
        
        두 스케줄 파일을 비교하여 다음을 분석합니다:
        
        1. **항공편 변경**
           - 삭제된 항공편 (스케줄 1에만 존재)
           - 신규 항공편 (스케줄 2에만 존재)
           - 시간이 변경된 항공편
        
        2. **연결 변경**
           - 사라진 연결 (스케줄 1에서는 연결되었으나 2에서는 안됨)
           - 새로운 연결 (스케줄 2에서 새로 가능해진 연결)
           - 연결 시간 변화 (동일 연결의 MCT 변화)
        
        3. **시각화**
           - 변경 요약 차트
           - 연결 시간 변화 분포
        """)