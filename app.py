import json
import os
import sys
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.track import Track
from services.json_import import JsonImportService
from services.merger import PlaylistMerger, DuplicateGroup
from services.artwork import ArtworkService

st.set_page_config(
    page_title="SongMeld",
    page_icon="🎵",
    layout="wide",
)


def init_session_state():
    if "playlists" not in st.session_state:
        st.session_state.playlists = {}
    if "all_tracks" not in st.session_state:
        st.session_state.all_tracks = []
    if "merger" not in st.session_state:
        st.session_state.merger = PlaylistMerger()


def render_sidebar():
    with st.sidebar:
        st.markdown("## ⚙️ Configuração")
        st.markdown("---")

        st.markdown("### 🎯 Threshold de Duplicados")
        threshold = st.slider(
            "Sensibilidade (%)",
            min_value=50,
            max_value=100,
            value=85,
            step=5,
            help="Quanto maior, mais estrita é a comparação de duplicatas",
        )
        st.session_state.merger = PlaylistMerger(similarity_threshold=threshold)

        st.markdown("---")
        st.markdown("### 📊 Estatísticas")
        total = len(st.session_state.all_tracks)
        st.metric("Total de Músicas", total)

        if st.session_state.playlists:
            st.markdown("**Playlists:**")
            for name, data in st.session_state.playlists.items():
                st.write(f"📄 {name} ({len(data['tracks'])} tracks)")

        st.markdown("---")
        st.caption("SongMeld v1.0")


def render_add_playlist():
    st.markdown("## ➕ Adicionar Playlist")

    st.markdown("### Ficheiro JSON")
    st.caption("Importa playlists exportadas do Nuclear ou de outros players")

    uploaded = st.file_uploader(
        "Carregar ficheiro JSON",
        type=["json"],
        key="json_upload",
    )
    json_name = st.text_input(
        "Nome (opcional)",
        placeholder="Ex: Minhas Favoritas",
        key="json_name",
    )

    if uploaded and st.button("Adicionar JSON", type="primary", key="add_json"):
        try:
            content = uploaded.read().decode("utf-8")
            name = json_name or uploaded.name.replace(".json", "")

            if name in st.session_state.playlists:
                counter = 2
                base_name = name
                while name in st.session_state.playlists:
                    name = f"{base_name} ({counter})"
                    counter += 1

            tracks = JsonImportService.import_from_file(content, name)

            st.session_state.playlists[name] = {
                "type": "json",
                "filename": uploaded.name,
                "tracks": tracks,
            }
            update_all_tracks()
            st.success(f"✅ {name} adicionada ({len(tracks)} tracks)")
            st.rerun()

        except Exception as e:
            st.error(f"Erro: {e}")


def update_all_tracks():
    all_tracks = []
    for name, data in st.session_state.playlists.items():
        all_tracks.extend(data["tracks"])
    st.session_state.all_tracks = all_tracks


def render_playlists():
    if not st.session_state.playlists:
        return

    st.markdown("## 📋 Playlists Adicionadas")

    for name, data in list(st.session_state.playlists.items()):
        col1, col2, col3 = st.columns([4, 2, 1])
        with col1:
            st.markdown(f"**📄 {name}**")
        with col2:
            st.caption(f"{len(data['tracks'])} tracks")
        with col3:
            if st.button("🗑️", key=f"remove_{name}"):
                del st.session_state.playlists[name]
                update_all_tracks()
                st.rerun()


def render_duplicates():
    if not st.session_state.all_tracks:
        return

    st.markdown("## 🔍 Análise de Duplicatas")

    merger = st.session_state.merger
    duplicates = merger.find_duplicates(st.session_state.all_tracks)

    if not duplicates:
        st.success("✅ Nenhuma duplicata encontrada!")
        return

    st.warning(f"⚠️ {len(duplicates)} duplicatas encontradas")

    merged_preview = merger.merge(st.session_state.all_tracks)
    stats = merger.get_stats(st.session_state.all_tracks, merged_preview)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Antes", stats["total_before"])
    with col2:
        st.metric("Depois", stats["total_after"])
    with col3:
        st.metric("Removidas", stats["removed"])

    st.markdown("---")
    st.markdown("### Duplicatas Encontradas")

    for i, dup in enumerate(duplicates):
        with st.expander(
            f"🔄 {dup.artist} - {dup.title} ({len(dup.tracks)} versões)",
            expanded=False,
        ):
            st.write("**Fontes:**")
            for j, track in enumerate(dup.tracks):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(
                        f"• {track.artist} - {track.title} "
                        f"(`{track.source_playlist}` | {track.platform})"
                    )
                with col2:
                    if st.checkbox(
                        "Manter",
                        key=f"keep_{i}_{j}",
                        value=(j == 0),
                    ):
                        if j not in dup.keep_indices:
                            dup.keep_indices.append(j)
                    else:
                        if j in dup.keep_indices:
                            dup.keep_indices.remove(j)


def render_merge_result():
    if not st.session_state.all_tracks:
        return

    st.markdown("## 🎯 Resultado Final")

    merger = st.session_state.merger
    duplicates = merger.find_duplicates(st.session_state.all_tracks)
    merged = merger.merge(st.session_state.all_tracks, duplicates)
    stats = merger.get_stats(st.session_state.all_tracks, merged)

    st.markdown("### Resumo")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Original", stats["total_before"])
    with col2:
        st.metric("Total Final", stats["total_after"])
    with col3:
        st.metric("Duplicatas Removidas", stats["removed"])
    with col4:
        removed_pct = (
            (stats["removed"] / stats["total_before"] * 100)
            if stats["total_before"] > 0
            else 0
        )
        st.metric("% Removido", f"{removed_pct:.1f}%")

    st.markdown("### Origens")
    for source, count in stats["sources"].items():
        st.write(f"• **{source}**: {count} tracks")

    st.markdown("---")
    st.markdown("### Preview das Músicas")

    if merged:
        preview_data = []
        for t in merged:
            preview_data.append(
                {
                    "Artista": t.artist,
                    "Música": t.title,
                    "Álbum": t.album,
                    "Duração": t.display_duration,
                    "Fonte": t.source_playlist,
                    "Plataforma": t.platform,
                }
            )
        st.dataframe(preview_data, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma música na playlist mesclada.")

    st.markdown("---")

    playlist_name = st.text_input(
        "Nome da Playlist Mesclada",
        value="Playlist Mesclada",
        key="export_name",
    )

    tracks_without_artwork = sum(1 for t in merged if not t.thumbnail)
    if tracks_without_artwork > 0:
        if st.button(
            f"🖼️ Buscar Miniaturas ({tracks_without_artwork} músicas sem imagem)",
            use_container_width=True,
        ):
            with st.spinner("A buscar miniaturas do iTunes..."):
                progress = st.progress(0)
                found = 0
                for i, track in enumerate(merged):
                    if not track.thumbnail:
                        artwork = ArtworkService.get_artwork(track.artist, track.title)
                        if artwork:
                            track.thumbnail = artwork
                            found += 1
                    progress.progress((i + 1) / len(merged))
                progress.empty()
                st.session_state.all_tracks = [
                    t for name, data in st.session_state.playlists.items()
                    for t in data["tracks"]
                ]
                st.success(f"✅ {found} miniaturas encontradas")
                st.rerun()

    if st.button("📥 Exportar JSON", type="primary", use_container_width=True):
        if not merged:
            st.error("Nenhuma música para exportar")
            return

        json_str = JsonImportService.export_to_json(
            tracks=merged,
            playlist_name=playlist_name,
            source_playlists=list(
                set(t.source_playlist for t in merged)
            ),
        )

        st.download_button(
            label="⬇️ Descarregar JSON",
            data=json_str,
            file_name=f"{playlist_name.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )


def main():
    init_session_state()
    render_sidebar()

    st.markdown("# 🎵 SongMeld")
    st.markdown("Junta playlists JSON, remove duplicatas e exporta o resultado.")

    st.markdown("---")

    render_add_playlist()

    if st.session_state.playlists:
        st.markdown("---")
        render_playlists()
        st.markdown("---")
        render_duplicates()
        st.markdown("---")
        render_merge_result()


if __name__ == "__main__":
    main()
