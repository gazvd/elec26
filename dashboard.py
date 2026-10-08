import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import folium
from streamlit_folium import folium_static
import numpy as np

# Configuração da página
st.set_page_config(page_title="Dashboard Eleições Recife", layout="wide")

# --- SISTEMA DE SENHA ---
def check_password():
    """Verifica se o usuário digitou a senha correta."""
    if st.session_state.get("password_correct", False):
        return True

    st.markdown("### 🔒 Acesso Restrito")
    st.text_input("Digite a senha para acessar o painel:", type="password", key="password")
    
    # Obter senha dos secrets de forma segura (com fallback)
    correct_password = "demokratia"
    try:
        if "password" in st.secrets:
            correct_password = st.secrets["password"]
    except Exception:
        pass

    user_password = st.session_state.get("password", "")
    if user_password and user_password == correct_password:
        st.session_state["password_correct"] = True
        st.rerun()
    elif user_password:
        st.error("Senha incorreta. Tente novamente.")
    return False

if not check_password():
    st.stop() # Para o código aqui se não tiver a senha

st.title("📊 Dashboard de Resultados Eleitorais - Recife")

@st.cache_data
def load_data():
    # 1. Carregar estatísticas e votos (recife.zip)
    df_estatisticas = pd.read_csv('estatisticas_votacaorecife.csv')
    df_votos = pd.read_csv('recife.zip')
    
    # 2. Carregar a base consolidada de seções e locais (de_para_secoes_bairros.csv)
    # Contém todas as seções mapeadas, coordenadas tratadas e bairros padronizados
    df_de_para = pd.read_csv('de_para_secoes_bairros.csv')
    df_locais = pd.read_csv('locais_votacao_recife.csv')
    
    # Garantir identificador unificado local_id
    if 'local_id' not in df_de_para.columns:
        df_de_para['local_id'] = df_de_para['zona'].astype(str) + '_' + df_de_para['codigo_local'].astype(str)
    
    # Remover colunas duplicadas antes da mesclagem
    df_votos = df_votos.drop(columns=['latitude', 'longitude', 'bairro'], errors='ignore')
    df_estatisticas = df_estatisticas.drop(columns=['latitude', 'longitude', 'bairro'], errors='ignore')
    
    # Otimização de tipos para economizar memória (essencial para o limite de 1 GB do Streamlit Cloud)
    for col in ['ano', 'turno', 'zona', 'secao']:
        df_votos[col] = df_votos[col].astype('int16')
        df_estatisticas[col] = df_estatisticas[col].astype('int16')
    df_votos['total_votos'] = df_votos['total_votos'].astype('int32')
    
    # Mesclagem direta e leve (1 único merge)
    df_votos = df_votos.merge(df_de_para, on=['zona', 'secao'], how='left')
    df_estatisticas = df_estatisticas.merge(df_de_para, on=['zona', 'secao'], how='left')
    
    # Tratar eventuais nulos
    df_votos['bairro'] = df_votos['bairro'].fillna('Desconhecido')
    df_estatisticas['bairro'] = df_estatisticas['bairro'].fillna('Desconhecido')
    df_votos['nome_local'] = df_votos['nome_local'].fillna('Local Histórico / Extinto')
    df_estatisticas['nome_local'] = df_estatisticas['nome_local'].fillna('Local Histórico / Extinto')
    df_votos['codigo_local'] = df_votos['codigo_local'].fillna(0).astype(int)
    df_estatisticas['codigo_local'] = df_estatisticas['codigo_local'].fillna(0).astype(int)
    df_votos['local_id'] = df_votos['local_id'].fillna(df_votos['zona'].astype(str) + '_0')
    df_estatisticas['local_id'] = df_estatisticas['local_id'].fillna(df_estatisticas['zona'].astype(str) + '_0')
    df_votos['endereco'] = df_votos['endereco'].fillna('')
    df_estatisticas['endereco'] = df_estatisticas['endereco'].fillna('')
    
    # Downcast para categorias economizando mais de 250 MB de RAM
    for c in ['cargo', 'sigla_partido', 'bairro', 'nome_local']:
        df_votos[c] = df_votos[c].astype('category')
    
    # 3. Carregar Bairros Shapefile
    bairros_gdf = gpd.read_file('Bairros/Bairros_Recife/bairros-polygon.shp')
    if bairros_gdf.crs != "EPSG:4326":
        bairros_gdf = bairros_gdf.to_crs("EPSG:4326")
    bairro_col = 'bairro_nom'
    
    return df_votos, df_estatisticas, bairros_gdf, bairro_col, df_locais

try:
    with st.spinner("Carregando e processando dados espaciais..."):
        df_votos, df_estatisticas, bairros_gdf, bairro_col, df_locais = load_data()
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.stop()

# --- FILTROS ---
st.sidebar.header("Filtros Obrigatórios")
anos_disp = sorted(df_votos['ano'].dropna().unique())
ano_sel = st.sidebar.selectbox("Ano", anos_disp, index=len(anos_disp)-1)

turnos_disp = sorted(df_votos[df_votos['ano'] == ano_sel]['turno'].dropna().unique())
turno_sel = st.sidebar.selectbox("Turno", turnos_disp)

cargos_disp = sorted(df_votos[(df_votos['ano'] == ano_sel) & (df_votos['turno'] == turno_sel)]['cargo'].dropna().unique())
cargo_sel = st.sidebar.selectbox("Cargo", cargos_disp)

st.sidebar.header("Filtros Opcionais")
# Filtrar para alimentar as dropdowns dinamicamente (em cascata)
mask_base = (df_votos['ano'] == ano_sel) & (df_votos['turno'] == turno_sel) & (df_votos['cargo'] == cargo_sel)
df_base = df_votos[mask_base]

partidos_disp = ["Todos"] + sorted(df_base['sigla_partido'].dropna().unique())
partido_sel = st.sidebar.selectbox("Partido", partidos_disp)

zonas_disp = ["Todas"] + sorted(df_base['zona'].dropna().unique())
zona_sel = st.sidebar.selectbox("Zona Eleitoral", zonas_disp)

df_base_z = df_base if zona_sel == "Todas" else df_base[df_base['zona'] == zona_sel]
bairros_disp = ["Todos"] + sorted(df_base_z['bairro'].dropna().astype(str).unique())
bairro_sel = st.sidebar.selectbox("Bairro", bairros_disp)

df_base_b = df_base_z if bairro_sel == "Todos" else df_base_z[df_base_z['bairro'] == bairro_sel]
locais_validos = df_base_b[df_base_b['codigo_local'] > 0][['local_id', 'nome_local', 'codigo_local', 'zona']].drop_duplicates().sort_values('nome_local')

mapa_locais = {
    f"{r['nome_local']} (Local {int(r['codigo_local'])} - Z{int(r['zona'])})": r['local_id']
    for _, r in locais_validos.iterrows()
}
opcoes_locais = ["Todos"] + list(mapa_locais.keys())
local_sel = st.sidebar.selectbox("Colégio / Local de Votação", opcoes_locais)

df_base_l = df_base_b
sel_local_id = None
if local_sel != "Todos":
    sel_local_id = mapa_locais.get(local_sel)
    if sel_local_id:
        df_base_l = df_base_b[df_base_b['local_id'] == sel_local_id]

secoes_disp = ["Todas"] + sorted(df_base_l['secao'].dropna().astype(int).unique())
secao_sel = st.sidebar.selectbox("Seção Eleitoral", secoes_disp)

st.sidebar.header("Visualização do Mapa")
nivel_agregacao = st.sidebar.radio("Agrupar dados por:", ["Colégio (Seções)", "Bairro", "Zona"])

# --- APLICAÇÃO DOS FILTROS FINAIS ---
mask_est = (df_estatisticas['ano'] == ano_sel) & (df_estatisticas['turno'] == turno_sel) & (df_estatisticas['cargo'] == cargo_sel)
if zona_sel != "Todas": mask_est &= (df_estatisticas['zona'] == zona_sel)
if bairro_sel != "Todos": mask_est &= (df_estatisticas['bairro'] == bairro_sel)
if sel_local_id is not None: mask_est &= (df_estatisticas['local_id'] == sel_local_id)
if secao_sel != "Todas": mask_est &= (df_estatisticas['secao'] == secao_sel)
df_est_filtrado = df_estatisticas[mask_est]

mask_vot = mask_base.copy()
if partido_sel != "Todos": mask_vot &= (df_votos['sigla_partido'] == partido_sel)
if zona_sel != "Todas": mask_vot &= (df_votos['zona'] == zona_sel)
if bairro_sel != "Todos": mask_vot &= (df_votos['bairro'] == bairro_sel)
if sel_local_id is not None: mask_vot &= (df_votos['local_id'] == sel_local_id)
if secao_sel != "Todas": mask_vot &= (df_votos['secao'] == secao_sel)
df_votos_filtrado = df_votos[mask_vot]

# --- CARDS DE KPI ---
st.markdown("### Resumo Geral (filtros aplicados)")

# Para evitar dupla contagem, agregamos por zona/secao
df_kpi = df_est_filtrado.drop_duplicates(subset=['zona', 'secao'])

total_aptos = df_kpi['aptos'].sum()
total_comparecimento = df_kpi['comparecimento'].sum()
total_abstencoes = df_kpi['abstencoes'].sum()
total_brancos = df_kpi['votos_brancos'].sum()
total_nulos = df_kpi['votos_nulos'].sum()

# Adequação para cargos proporcionais (Vereador, Dep. Estadual, Dep. Federal)
if cargo_sel.lower() in ['vereador', 'deputado estadual', 'deputado federal']:
    # A base de candidatos (recife.zip) contém apenas Votos Nominais.
    # Ocultamos os votos de legenda no KPI para bater exatamente com a soma da tabela.
    total_validos = df_kpi['votos_nominais'].sum()
    label_kpi_votos = "Votos Nominais"
else:
    # Majoritários não possuem legenda
    total_validos = df_kpi['votos_nominais'].sum() + df_kpi['votos_legenda'].sum()
    label_kpi_votos = "Votos Válidos"

votos_partido = df_votos_filtrado['total_votos'].sum()

pct_abstencao = (total_abstencoes / total_aptos * 100) if total_aptos > 0 else 0
pct_validos = (total_validos / total_comparecimento * 100) if total_comparecimento > 0 else 0
pct_nulos = (total_nulos / total_comparecimento * 100) if total_comparecimento > 0 else 0
pct_brancos = (total_brancos / total_comparecimento * 100) if total_comparecimento > 0 else 0

col1, col2, col3, col4, col5 = st.columns(5)
if partido_sel != "Todos":
    col1.metric(f"Votos ({partido_sel})", f"{votos_partido:,}".replace(",", "."))
else:
    col1.metric(label_kpi_votos, f"{total_validos:,}".replace(",", "."))

col2.metric("Abstenção", f"{total_abstencoes:,}".replace(",", "."), f"{pct_abstencao:.1f}%".replace(".", ","), delta_color="inverse")
col3.metric("Comparecimento", f"{total_comparecimento:,}".replace(",", "."))
col4.metric("Votos Nulos", f"{total_nulos:,}".replace(",", "."), f"{pct_nulos:.1f}%".replace(".", ","), delta_color="off")
col5.metric("Votos Brancos", f"{total_brancos:,}".replace(",", "."), f"{pct_brancos:.1f}%".replace(".", ","), delta_color="off")

st.divider()

# --- MAPA ---
st.markdown(f"### Mapa de Resultados por {nivel_agregacao}")

m = folium.Map(location=[-8.047562, -34.877003], zoom_start=12, tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', attr='Tiles &copy; Esri')

partidos_cores = {
    'PSB': '#ffd700', 'PT': '#ff0000', 'DEM': '#0000ff', 'PSDB': '#00008b',
    'PSOL': '#ff8c00', 'PODE': '#008000', 'MDB': '#00ff00', 'CIDADANIA': '#ff1493',
    'REPUBLICANOS': '#00ced1', 'PDT': '#ff4500', 'PL': '#000080', 'PP': '#4682b4',
    'PROS': '#ff69b4', 'PRTB': '#8b4513', 'PSC': '#2e8b57', 'PSL': '#191970',
    'PTB': '#000000', 'PV': '#32cd32', 'REDE': '#00fa9a', 'SOLIDARIEDADE': '#ffa500',
    'NOVO': '#ff8c00', 'UP': '#ff0000', 'PSTU': '#ff0000', 'PCB': '#ff0000', 'PCO': '#ff0000'
}

def get_color(partido):
    if pd.isna(partido):
        return '#cccccc'
    return partidos_cores.get(partido, '#888888')

if len(df_votos_filtrado) > 0:
    if nivel_agregacao == "Bairro":
        agg_bairro = df_votos_filtrado.groupby(['bairro', 'sigla_partido'])['total_votos'].sum().reset_index()
        bairros_map = bairros_gdf.copy()
        
        if partido_sel == "Todos":
            idx_venc = agg_bairro.groupby('bairro')['total_votos'].idxmax()
            venc_bairro = agg_bairro.loc[idx_venc]
            bairros_map = bairros_map.merge(venc_bairro, left_on=bairro_col, right_on='bairro', how='inner')
            
            folium.GeoJson(
                bairros_map,
                style_function=lambda feature: {
                    'fillColor': get_color(feature['properties'].get('sigla_partido')),
                    'color': 'black', 'weight': 1, 'fillOpacity': 0.6
                },
                tooltip=folium.GeoJsonTooltip(fields=[bairro_col, 'sigla_partido', 'total_votos'],
                                              aliases=['Bairro', 'Partido Vencedor', 'Votos'])
            ).add_to(m)
        else:
            bairros_map = bairros_map.merge(agg_bairro, left_on=bairro_col, right_on='bairro', how='inner')
            folium.GeoJson(
                bairros_map,
                style_function=lambda feature: {
                    'fillColor': get_color(partido_sel),
                    'color': 'black', 'weight': 1, 'fillOpacity': 0.6
                },
                tooltip=folium.GeoJsonTooltip(fields=[bairro_col, 'sigla_partido', 'total_votos'],
                                              aliases=['Bairro', 'Partido', 'Votos'])
            ).add_to(m)

    elif nivel_agregacao == "Zona":
        # Descobrir a zona predominante de cada bairro para agrupar as geometrias de forma limpa
        bairro_zona = df_votos_filtrado.groupby(['bairro', 'zona'])['total_votos'].sum().reset_index()
        if len(bairro_zona) > 0:
            idx_bz = bairro_zona.groupby('bairro')['total_votos'].idxmax()
            bairro_pred_zona = bairro_zona.loc[idx_bz, ['bairro', 'zona']]
            
            # Mesclar a zona predominante no shapefile dos bairros e fazer dissolve (agrupar polígonos)
            bairros_map = bairros_gdf.merge(bairro_pred_zona, left_on=bairro_col, right_on='bairro', how='inner')
            zonas_poly = bairros_map.dissolve(by='zona').reset_index()
            
            agg_zona = df_votos_filtrado.groupby(['zona', 'sigla_partido'])['total_votos'].sum().reset_index()
            
            if partido_sel == "Todos":
                idx_venc = agg_zona.groupby('zona')['total_votos'].idxmax()
                venc_zona = agg_zona.loc[idx_venc]
                zonas_poly = zonas_poly.merge(venc_zona, on='zona', how='inner')
                
                folium.GeoJson(
                    zonas_poly,
                    style_function=lambda feature: {
                        'fillColor': get_color(feature['properties'].get('sigla_partido')),
                        'color': 'black', 'weight': 1.5, 'fillOpacity': 0.6
                    },
                    tooltip=folium.GeoJsonTooltip(fields=['zona', 'sigla_partido', 'total_votos'],
                                                  aliases=['Zona Eleitoral', 'Partido Vencedor', 'Votos'])
                ).add_to(m)
            else:
                zonas_poly = zonas_poly.merge(agg_zona, on='zona', how='inner')
                folium.GeoJson(
                    zonas_poly,
                    style_function=lambda feature: {
                        'fillColor': get_color(partido_sel),
                        'color': 'black', 'weight': 1.5, 'fillOpacity': 0.6
                    },
                    tooltip=folium.GeoJsonTooltip(fields=['zona', 'sigla_partido', 'total_votos'],
                                                  aliases=['Zona Eleitoral', 'Partido', 'Votos'])
                ).add_to(m)

    else:
        # Colégio / Local de Votação
        agg_colegio = df_votos_filtrado.dropna(subset=['latitude', 'longitude']).groupby(
            ['local_id', 'nome_local', 'codigo_local', 'endereco', 'latitude', 'longitude', 'zona', 'bairro', 'sigla_partido'])['total_votos'].sum().reset_index()
        
        if len(agg_colegio) > 0:
            if partido_sel == "Todos":
                idx_venc = agg_colegio.groupby('local_id')['total_votos'].idxmax()
                venc_colegio = agg_colegio.loc[idx_venc].copy()
                
                # Prepara os top 5 partidos mais votados por local
                top_partidos = agg_colegio.sort_values(['local_id', 'total_votos'], ascending=[True, False]).groupby('local_id').head(5)
                dict_resultados = {}
                for lid, group in top_partidos.groupby('local_id'):
                    dict_resultados[lid] = group[['sigla_partido', 'total_votos']].to_dict('records')
                venc_colegio['resultados'] = venc_colegio['local_id'].map(dict_resultados)
                
                for _, row in venc_colegio.iterrows():
                    res_str = "<br>".join([f"<b>{r['sigla_partido']}</b>: {r['total_votos']:,}".replace(",", ".") for r in (row['resultados'] or [])])
                    end_str = f"<br><small>{row['endereco']}</small>" if row['endereco'] else ""
                    cod_str = f" (Local {int(row['codigo_local'])})" if row['codigo_local'] > 0 else ""
                    popup_html = f"<b>{row['nome_local']}{cod_str}</b><br><b>Bairro:</b> {row['bairro']}<br><b>Zona:</b> {row['zona']}{end_str}<hr>{res_str}"
                    
                    folium.CircleMarker(
                        location=[row['latitude'], row['longitude']],
                        radius=6, popup=folium.Popup(popup_html, max_width=280),
                        tooltip=f"{row['nome_local']} (Z{row['zona']})",
                        color='white', weight=1, fill=True,
                        fillColor=get_color(row['sigla_partido']), fillOpacity=0.9
                    ).add_to(m)
            else:
                max_votos = agg_colegio['total_votos'].max()
                for _, row in agg_colegio.iterrows():
                    raio = 5 + (row['total_votos'] / max_votos * 10) if max_votos > 0 else 5
                    end_str = f"<br><small>{row['endereco']}</small>" if row['endereco'] else ""
                    cod_str = f" (Local {int(row['codigo_local'])})" if row['codigo_local'] > 0 else ""
                    popup_html = f"<b>{row['nome_local']}{cod_str}</b><br><b>Bairro:</b> {row['bairro']}<br><b>Zona:</b> {row['zona']}{end_str}<hr><b>{row['sigla_partido']}</b>: {row['total_votos']:,} votos".replace(",", ".")
                    
                    folium.CircleMarker(
                        location=[row['latitude'], row['longitude']],
                        radius=raio,
                        popup=folium.Popup(popup_html, max_width=280),
                        tooltip=f"{row['nome_local']} - Votos: {row['total_votos']:,}".replace(",", "."),
                        color='white', weight=1, fill=True,
                        fillColor=get_color(row['sigla_partido']), fillOpacity=0.9
                    ).add_to(m)
else:
    st.warning("Nenhum dado encontrado para os filtros selecionados.")

from streamlit_folium import st_folium

map_data = st_folium(m, width=1000, height=600, returned_objects=["last_active_drawing", "last_object_clicked"])

st.markdown("### 📋 Detalhamento dos Dados")

df_table = df_votos_filtrado.copy()
filtro_clique = None
nome_clique = None
secoes_informativo = None

if map_data:
    if map_data.get("last_active_drawing"):
        props = map_data["last_active_drawing"].get("properties", {})
        if nivel_agregacao == "Bairro" and bairro_col in props:
            filtro_clique = props[bairro_col]
            nome_clique = filtro_clique
            df_table = df_table[df_table['bairro'] == filtro_clique]
        elif nivel_agregacao == "Zona" and "zona" in props:
            filtro_clique = props["zona"]
            nome_clique = f"Zona {filtro_clique}"
            df_table = df_table[df_table['zona'] == filtro_clique]
    
    if map_data.get("last_object_clicked") and nivel_agregacao == "Colégio (Seções)":
        lat_click = map_data["last_object_clicked"].get("lat")
        lng_click = map_data["last_object_clicked"].get("lng")
        if lat_click and lng_click:
            # Encontrar o colégio mais próximo do clique
            df_table['dist'] = (df_table['latitude'] - lat_click)**2 + (df_table['longitude'] - lng_click)**2
            if not df_table.empty:
                idx_min = df_table['dist'].idxmin()
                if df_table.loc[idx_min, 'dist'] < 0.0001: # Tolerância para o clique
                    filtro_clique = df_table.loc[idx_min, 'local_id']
                    nome_col_clique = df_table.loc[idx_min, 'nome_local']
                    cod_col_clique = df_table.loc[idx_min, 'codigo_local']
                    bairro_col_nome = df_table.loc[idx_min, 'bairro']
                    zona_col_nome = df_table.loc[idx_min, 'zona']
                    nome_clique = nome_col_clique
                    
                    df_colegio = df_table[df_table['local_id'] == filtro_clique]
                    
                    # Buscar todas as seções desse local (preferência para df_locais oficial se codigo_local > 0)
                    if cod_col_clique > 0:
                        secoes_list = sorted(df_locais[(df_locais['zona'] == zona_col_nome) & (df_locais['codigo_local'] == cod_col_clique)]['secao'].dropna().astype(int).unique())
                    else:
                        secoes_list = sorted(df_est_filtrado[df_est_filtrado['local_id'] == filtro_clique]['secao'].dropna().astype(int).unique())
                    
                    secoes_str = ", ".join([str(int(s)) for s in secoes_list])
                    cod_str = f" (Local {int(cod_col_clique)})" if cod_col_clique > 0 else ""
                    
                    secoes_informativo = f"🏫 **{nome_col_clique}{cod_str}** (Zona {zona_col_nome} - Bairro {bairro_col_nome})<br>📍 **Seções vinculadas a este local:** {secoes_str}"
                    df_table = df_colegio
            df_table = df_table.drop(columns=['dist'], errors='ignore')

if secoes_informativo:
    st.info(secoes_informativo)

if nivel_agregacao == "Bairro":
    if filtro_clique:
        st.success(f"Mostrando consolidado de votos por partido no Bairro: **{filtro_clique}**")
    else:
        st.info("Mostrando consolidado geral da cidade. Clique em um Bairro no mapa para ver os dados isolados dele!")
elif nivel_agregacao == "Zona":
    if filtro_clique:
        st.success(f"Mostrando consolidado de votos por partido na Zona Eleitoral: **{filtro_clique}**")
    else:
        st.info("Mostrando consolidado geral da cidade. Clique em uma Zona no mapa para ver os dados isolados dela!")
else:
    if nome_clique:
        st.success(f"Mostrando consolidado de votos por partido no Local de Votação: **{nome_clique}**")
    else:
        st.info("Mostrando consolidado geral. Clique em um Colégio (círculo) no mapa para ver as seções que compõem aquele local e filtrar os dados!")

# Focar na soma de votos do partido para o que está visível (seja cidade inteira ou a região clicada)
df_show = df_table.groupby('sigla_partido')['total_votos'].sum().reset_index()
df_show = df_show.rename(columns={'sigla_partido': 'Partido', 'total_votos': 'Total de Votos'})
df_show = df_show.sort_values(by='Total de Votos', ascending=False)

# Adicionar percentual
total_scope = df_show['Total de Votos'].sum()
df_show['% do Válido Local'] = (df_show['Total de Votos'] / total_scope * 100).apply(lambda x: f"{x:.2f}%".replace('.', ',')) if total_scope > 0 else "0,00%"

# Formatar o total de votos com separador de milhar (padrão brasileiro)
df_show['Total de Votos'] = df_show['Total de Votos'].apply(lambda x: f"{x:,.0f}".replace(",", "."))

# Criar a linha de TOTAL
linha_total = pd.DataFrame([{
    'Partido': '🛑 TOTAL VÁLIDOS',
    'Total de Votos': f"{total_scope:,.0f}".replace(",", "."),
    '% do Válido Local': '100,00%'
}])

# Anexar a linha de total no início do dataframe
df_show = pd.concat([linha_total, df_show], ignore_index=True)

# Ajustar o índice para começar em 1 (ou você pode omitir o índice visualmente)
df_show.index = range(1, len(df_show) + 1)

st.dataframe(df_show, use_container_width=True)
