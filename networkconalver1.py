import streamlit as st
import pandas as pd
import altair as alt

# 페이지 기본 설정
st.set_page_config(page_title="항공편 연결 분석기 v18", layout="wide")

st.title("✈️ 항공사 간 연결편 분석 앱")
st.markdown("""
**원하는 노선(Route)을 선택하여 상호 간의 환승 연결성을 분석합니다.  
예: `미주` ↔ `동남아` 연결뿐만 아니라, `동남아` ↔ `동남아` 같은 **지역 내 연결**도 분석 가능합니다.
""")

# --- [NOTICE] 데이터 작성 가이드 ---
with st.expander("📢 [필독] 데이터 파일(CSV) 작성 양식 가이드", expanded=False):
    st.markdown("""
    
    ##### 1. 필수 컬럼
    * **SEASON**: 시즌 (예: S26)
    * **FLT NO**: 편명 (예: 081)
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

# --- 데이터 로드 함수 (수정됨) ---
@st.cache_data
def load_data(file):
    # BOM(Byte Order Mark)이 포함된 utf-8-sig도 지원하여 호환성 강화
    encodings = ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr']
    for enc in encodings:
        try:
            file.seek(0)
            df = pd.read_csv(file, encoding=enc)
            
            # 1. 컬럼명 공백 제거 (예: " ROUTE " -> "ROUTE")
            df.columns = df.columns.str.strip()
            
            # 2. 컬럼명 통일 (DESTINATION -> DEST)
            # 분석 로직은 'DEST'를 기준으로 작성되었으므로, DESTINATION이 들어오면 이름을 변경함
            if 'DESTINATION' in df.columns:
                df.rename(columns={'DESTINATION': 'DEST'}, inplace=True)

            # 3. 필수 컬럼 체크 (이제 DEST로 통일된 상태에서 검사)
            required = ['OPS', 'FLT NO', '구분', 'STD', 'STA', 'ORGN', 'DEST', 'ROUTE']
            
            # 하나라도 누락되면 다음 인코딩 시도
            if not all(col in df.columns for col in required):
                continue
            
            # 4. 데이터 전처리 (문자열 변환)
            for col in ['구분', 'FLT NO', 'ROUTE', 'OPS', 'ORGN', 'DEST']:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip()
                    
            return df
        except:
            continue
    # 모든 시도가 실패했을 때 에러 메시지
    raise ValueError("파일을 읽을 수 없습니다. 인코딩 문제이거나 필수 컬럼(ROUTE, DEST, FLT NO 등)이 누락되었습니다.")

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
    
    # 헬퍼 함수: 특정 방향(Start Group -> End Group) 분석
    def analyze_one_direction(start_routes, start_ops, end_routes, end_ops, direction_label):
        # 1. Start Group (To ICN)
        inbound = df[
            (df['ROUTE'].isin(start_routes)) & 
            (df['OPS'].isin(start_ops)) & 
            (df['구분'] == 'To ICN')
        ].copy()
        
        # 2. End Group (From ICN)
        outbound = df[
            (df['ROUTE'].isin(end_routes)) & 
            (df['OPS'].isin(end_ops)) & 
            (df['구분'] == 'From ICN')
        ].copy()

        if inbound.empty or outbound.empty:
            return []

        local_results = []
        # Cross Join
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
                    'To': row['DEST_OUT'], # DEST 컬럼 사용
                    'Inbound_Flight': f"[{flt_in}] {row['ORGN_IN']}->{row['DEST_IN']} (Arr {row['STA_IN']})",
                    'Outbound_Flight': f"[{flt_out}] {row['ORGN_OUT']}->{row['DEST_OUT']} (Dep {row['STD_OUT']})",
                    'Hub_Arr_Time': row['STA_IN'], 'Hub_Dep_Time': row['STD_OUT'],
                    'Conn_Min': diff, 'Status': status
                })
        return local_results

    # 1. 방향 A -> B
    results.extend(analyze_one_direction(
        group_a_routes, group_a_ops, 
        group_b_routes, group_b_ops, 
        direction_label="Group A -> Group B"
    ))

    # 2. 방향 B -> A (그룹이 다를 때만 수행)
    is_same_group = set(group_a_routes) == set(group_b_routes) and set(group_a_ops) == set(group_b_ops)
    
    if not is_same_group:
        results.extend(analyze_one_direction(
            group_b_routes, group_b_ops, 
            group_a_routes, group_a_ops, 
            direction_label="Group B -> Group A"
        ))

    cols = ['Direction', 'Inbound_Route', 'Outbound_Route', 'Inbound_OPS', 'Outbound_OPS', 'Inbound_Flt_No', 'Outbound_Flt_No', 'From', 'Via', 'To', 'Inbound_Flight', 'Outbound_Flight', 'Hub_Arr_Time', 'Hub_Dep_Time', 'Conn_Min', 'Status']
    if not results: return pd.DataFrame(columns=cols)
    return pd.DataFrame(results)[cols]

# --- 메인 화면 로직 ---
st.sidebar.header("⚙️ 분석 설정")
uploaded_file = st.sidebar.file_uploader("📂 데이터 파일 (CSV)", type="csv")

if uploaded_file is not None:
    try:
        df = load_data(uploaded_file)
        st.sidebar.success(f"✅ 파일 로드: {len(df)}건")
        
        # 필터 목록 생성
        all_routes = sorted(df['ROUTE'].unique().tolist())
        all_ops = sorted(df['OPS'].unique().tolist())
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("📌 노선 그룹 매칭")
        
        # --- 그룹 A 설정 ---
        st.sidebar.markdown("**[그룹 A] 설정** (예: 미주노선)")
        # 기본값 설정: 리스트가 비어있지 않다면 첫 번째 값을 선택
        default_route_a = [all_routes[0]] if all_routes else None
        routes_a = st.sidebar.multiselect("그룹 A 노선 선택", all_routes, default=default_route_a, key='ra')
        ops_a = st.sidebar.multiselect("그룹 A 항공사 선택", all_ops, default=all_ops, key='oa')
        
        st.sidebar.markdown("⬇️ ⬆️ **상호 연결 분석**")
        
        # --- 그룹 B 설정 ---
        st.sidebar.markdown("**[그룹 B] 설정** (예: 동남아노선)")
        # 기본값 설정: 리스트 길이가 2 이상이면 두 번째 값을, 아니면 전체 선택 등 유연하게
        default_route_b = [all_routes[1]] if len(all_routes) > 1 else all_routes
        routes_b = st.sidebar.multiselect("그룹 B 노선 선택", all_routes, default=default_route_b, key='rb')
        ops_b = st.sidebar.multiselect("그룹 B 항공사 선택", all_ops, default=all_ops, key='ob')
        
        st.sidebar.markdown("---")
        min_mct = st.sidebar.number_input("Min CT (분)", 0, 300, 45, 5)
        max_ct = st.sidebar.number_input("Max CT (분)", 60, 2880, 1440, 60)
        
        if st.button("🚀 분석 시작", type="primary"):
            if not routes_a or not routes_b:
                st.error("그룹 A와 그룹 B의 노선을 최소 하나 이상 선택해주세요.")
            else:
                with st.spinner("데이터 분석 중..."):
                    result_df = analyze_connections_flexible(
                        df, min_mct, max_ct, 
                        routes_a, ops_a, 
                        routes_b, ops_b
                    )
                    st.session_state['analysis_result'] = result_df
                    st.session_state['analysis_done'] = True
                    # 그룹 이름 저장 (UI 표시용)
                    st.session_state['group_names'] = (
                        ", ".join(routes_a),
                        ", ".join(routes_b)
                    )

        if 'analysis_done' in st.session_state and st.session_state['analysis_done']:
            result_df = st.session_state['analysis_result']
            g_name_a, g_name_b = st.session_state.get('group_names', ("A", "B"))
            
            if result_df.empty:
                st.warning("조건에 맞는 연결편이 없습니다.")
            else:
                tab1, tab2, tab3 = st.tabs(["📊 결과 요약", "📋 상세 리스트", "✈️ 공항별 심층 분석"])
                
                with tab1:
                    st.info(f"💡 **분석 기준**: [그룹 A: {g_name_a}] ↔ [그룹 B: {g_name_b}]")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("##### 방향별 연결 건수")
                        st.dataframe(result_df.groupby(['Direction', 'Status']).size().unstack(fill_value=0), use_container_width=True)
                    with col2:
                        st.markdown("##### 평균 연결 시간 (분)")
                        connected = result_df[result_df['Status']=='Connected']
                        if not connected.empty:
                            st.dataframe(connected.groupby('Direction')['Conn_Min'].mean().round(1), use_container_width=True)

                with tab2:
                    st.markdown("#### 상세 연결 리스트")
                    status_filter = st.multiselect("상태 필터", ['Connected', 'Disconnect'], default=['Connected'], key='sf')
                    view_df = result_df[result_df['Status'].isin(status_filter)].sort_values(['Direction', 'Conn_Min'])
                    st.dataframe(view_df, use_container_width=True, hide_index=True)
                    csv = view_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("💾 결과 CSV 다운로드", csv, "connection_analysis.csv", "text/csv")

                with tab3:
                    st.markdown("### 🏙️ 공항 기준 연결성 분석")
                    
                    # 공항 추출 로직: 결과 데이터에 존재하는 공항들 중 ICN 제외
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
                        
                        # Chart 1: Group A -> Group B
                        with c1:
                            st.markdown(f"#### 🛫 {selected_airport} → 그룹 B")
                            out_df = connected_data[
                                (connected_data['Direction'] == 'Group A -> Group B') & 
                                (connected_data['From'] == selected_airport)
                            ].sort_values('Conn_Min')
                            
                            if out_df.empty:
                                st.info("연결편 없음")
                            else:
                                chart_out = alt.Chart(out_df).mark_circle(size=120).encode(
                                    x=alt.X('To', title='도착지 (그룹 B)'),
                                    y=alt.Y('Conn_Min', title='연결 시간(분)'),
                                    color=alt.Color('Inbound_Flt_No', title='ICN 도착편명', legend=alt.Legend(orient='bottom')),
                                    tooltip=['To', 'Conn_Min', 'Inbound_Flt_No', 'Outbound_Flt_No']
                                ).properties(height=400).interactive()
                                st.altair_chart(chart_out, use_container_width=True)

                        # Chart 2: Group B -> Group A
                        with c2:
                            st.markdown(f"#### 🛬 그룹 B → {selected_airport}")
                            in_df = connected_data[
                                (connected_data['Direction'] == 'Group B -> Group A') & 
                                (connected_data['To'] == selected_airport)
                            ].sort_values('Conn_Min')
                            
                            if in_df.empty:
                                st.info("연결편 없음")
                            else:
                                chart_in = alt.Chart(in_df).mark_circle(size=120).encode(
                                    x=alt.X('From', title='출발지 (그룹 B)'),
                                    y=alt.Y('Conn_Min', title='연결 시간(분)'),
                                    color=alt.Color('Outbound_Flt_No', title='ICN 출발편명', legend=alt.Legend(orient='bottom')),
                                    tooltip=['From', 'Conn_Min', 'Inbound_Flt_No', 'Outbound_Flt_No']
                                ).properties(height=400).interactive()
                                st.altair_chart(chart_in, use_container_width=True)

    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
else:
    if 'analysis_done' in st.session_state:
        del st.session_state['analysis_done']
        del st.session_state['analysis_result']
    st.info("👈 파일을 업로드하고 분석을 시작하세요.")