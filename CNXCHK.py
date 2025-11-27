import streamlit as st
import pandas as pd

# 페이지 기본 설정
st.set_page_config(page_title="항공편 연결 분석기 v2", layout="wide")

st.title("✈️ 항공사별 연결편(Connection) 분석 앱")
st.markdown("""
왼쪽 사이드바에서 **연결 시간 기준(MCT)**을 설정하고 분석 버튼을 눌러보세요.  
기준에 따라 **Connected**와 **Disconnect**로 자동 분류됩니다.
""")

# --- 사이드바: 설정 메뉴 구성 ---
st.sidebar.header("⚙️ 분석 설정")

# 1. 최소 연결 시간 (Min MCT) 설정
min_mct = st.sidebar.number_input(
    "최소 연결 시간 (분)", 
    min_value=0, 
    max_value=300, 
    value=45, 
    step=5,
    help="이 시간보다 짧으면 환승 불가(Disconnect)로 처리됩니다."
)

# 2. 최대 연결 시간 (Max CT) 설정
max_ct = st.sidebar.number_input(
    "최대 연결 시간 (분)", 
    min_value=60, 
    max_value=2880, # 48시간
    value=1440,     # 24시간
    step=60,
    help="이 시간보다 길면 연결 불가(Disconnect)로 처리됩니다."
)

st.sidebar.markdown("---")
st.sidebar.info(f"현재 기준: **{min_mct}분** 이상 ~ **{max_ct}분** 이하")

# --- 데이터 처리 함수 ---

@st.cache_data
def load_data(file):
    return pd.read_csv(file)

def time_to_minutes(t_str):
    try:
        h, m = map(int, t_str.split(':'))
        return h * 60 + m
    except:
        return None

def analyze_connections(df, min_limit, max_limit):
    results = []
    
    # 진행률 표시줄
    progress_text = "데이터 분석 중..."
    my_bar = st.progress(0, text=progress_text)
    
    ops_groups = df.groupby('OPS')
    total_groups = len(ops_groups)
    
    for i, (ops, group) in enumerate(ops_groups):
        # 1. US -> ASIA
        us_out = group[group['구분'] == 'US OUT']
        asia_in = group[group['구분'] == 'ASIA IN']
        
        if not us_out.empty and not asia_in.empty:
            merged = pd.merge(us_out.assign(k=1), asia_in.assign(k=1), on='k', suffixes=('_ARR', '_DEP'))
            for _, row in merged.iterrows():
                arr = time_to_minutes(row['STA_ARR'])
                dep = time_to_minutes(row['STD_DEP'])
                
                if arr is not None and dep is not None:
                    diff = dep - arr
                    if diff < 0: diff += 1440 # 다음날 연결
                    
                    # 설정한 min/max 값에 따라 상태 결정
                    status = 'Connected' if min_limit <= diff <= max_limit else 'Disconnect'
                    
                    results.append({
                        'OPS': ops,
                        'Direction': 'US -> ASIA',
                        'Inbound': f"{row['ORGN_ARR']}->{row['DESTINATION_ARR']}",
                        'Outbound': f"{row['ORGN_DEP']}->{row['DESTINATION_DEP']}",
                        'Hub_Arr_Time': row['STA_ARR'],
                        'Hub_Dep_Time': row['STD_DEP'],
                        'Conn_Min': diff,
                        'Status': status
                    })

        # 2. ASIA -> US
        asia_out = group[group['구분'] == 'ASIA OUT']
        us_in = group[group['구분'] == 'US IN']
        
        if not asia_out.empty and not us_in.empty:
            merged = pd.merge(asia_out.assign(k=1), us_in.assign(k=1), on='k', suffixes=('_ARR', '_DEP'))
            for _, row in merged.iterrows():
                arr = time_to_minutes(row['STA_ARR'])
                dep = time_to_minutes(row['STD_DEP'])
                
                if arr is not None and dep is not None:
                    diff = dep - arr
                    if diff < 0: diff += 1440
                    
                    # 설정한 min/max 값에 따라 상태 결정
                    status = 'Connected' if min_limit <= diff <= max_limit else 'Disconnect'
                    
                    results.append({
                        'OPS': ops,
                        'Direction': 'ASIA -> US',
                        'Inbound': f"{row['ORGN_ARR']}->{row['DESTINATION_ARR']}",
                        'Outbound': f"{row['ORGN_DEP']}->{row['DESTINATION_DEP']}",
                        'Hub_Arr_Time': row['STA_ARR'],
                        'Hub_Dep_Time': row['STD_DEP'],
                        'Conn_Min': diff,
                        'Status': status
                    })
        
        # 진행률 업데이트
        my_bar.progress((i + 1) / total_groups, text=progress_text)
        
    my_bar.empty() # 완료 후 진행바 제거
    return pd.DataFrame(results)

# --- 메인 화면 로직 ---

uploaded_file = st.file_uploader("📂 데이터 파일 업로드 (CSV)", type="csv")

if uploaded_file is not None:
    df = load_data(uploaded_file)
    st.write(f"✅ 파일 로드 완료: 총 {len(df)}개 운항편")
    
    # 분석 버튼
    if st.button("🚀 분석 시작"):
        result_df = analyze_connections(df, min_mct, max_ct)
        
        # 1. 요약 통계 보여주기
        st.subheader("📊 분석 결과 요약")
        
        # Pivot Table로 Connected / Disconnect 개수 집계
        summary = result_df.groupby(['OPS', 'Direction', 'Status']).size().unstack(fill_value=0)
        
        # 보기 좋게 색상 입히기 (선택사항)
        st.dataframe(summary, use_container_width=True)
        
        # 2. 상세 데이터 필터링 및 다운로드
        st.subheader("📋 상세 리스트 확인")
        
        col1, col2 = st.columns(2)
        with col1:
            status_filter = st.multiselect(
                "상태(Status) 필터", 
                options=['Connected', 'Disconnect'], 
                default=['Connected', 'Disconnect']
            )
        with col2:
            ops_filter = st.multiselect(
                "항공사(OPS) 필터",
                options=result_df['OPS'].unique(),
                default=result_df['OPS'].unique()
            )
            
        # 필터 적용
        filtered_df = result_df[
            (result_df['Status'].isin(status_filter)) & 
            (result_df['OPS'].isin(ops_filter))
        ]
        
        # 시간 순으로 정렬하여 표시
        filtered_df = filtered_df.sort_values(by=['OPS', 'Direction', 'Conn_Min'])
        
        st.dataframe(filtered_df, use_container_width=True)
        
        # CSV 다운로드 버튼
        csv_data = filtered_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="💾 결과 CSV 다운로드",
            data=csv_data,
            file_name='connection_analysis_v2.csv',
            mime='text/csv'
        )

elif uploaded_file is None:
    st.info("데이터 파일을 업로드하면 분석 설정 메뉴가 활성화됩니다.")