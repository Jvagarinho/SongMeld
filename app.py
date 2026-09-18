import json
import os
import sys
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.track import Track
from services.spotify import SpotifyService
from services.json_import import JsonImportService
from services.merger import PlaylistMerger, DuplicateGroup

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
    if "spotify_service" not in st.session_state:
        client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
        redirect_uri = os.environ.get("SPOTIFY_REDIRECT_URI", "http://localhost:8501")
        st.session_state.spotify_service = SpotifyService(client_id, redirect_uri=redirect_uri)


def handle_oauth_callback():
    query_params = st.query_params
    code = query_params.get("code", None)

    if code:
        spotify = st.session_state.spotify_service
        success = spotify.handle_callback(code)
        if success:
            st.query_params.clear()
            st.rerun()
        else:
            st.error("Erro ao autenticar com Spotify. Tente novamente.")


def render_sidebar():
    with st.sidebar:
        st.markdown("## ⚙️ Configuração")
        st.markdown("---")

        spotify = st.session_state.spotify_service

        if spotify.is_configured():
            st.markdown("### 👤 Conta Spotify")
            if spotify.is_user_authenticated():
                st.success("✅ Autenticado com Spotify")
                if st.button("🔓 Desconectar", use_container_width=True):
                    spotify.logout()
                    st.rerun()
            else:
                if st.button("🔑 Ligar com Spotify", type="primary", use_container_width=True):
                    auth_url = spotify.get_auth_url()
                    st.markdown(f"[Clique aqui para autenticar]({auth_url})")
                st.caption("Para aceder a playlists do Spotify")

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
                icon = "🎵" if data.get("type") == "spotify" else "📄"
                st.write(f"{icon} {name} ({len(data['tracks'])} tracks)")

        st.markdown("---")
        st.caption("SongMeld v1.0")


def render_add_playlist():
    st.markdown("## ➕ Adicionar Playlist")

    spotify = st.session_state.spotify_service
    tabs = ["📄 JSON"]

    if spotify.is_configured():
        tabs.insert(0, "🎵 Spotify")

    tab_objects = st.tabs(tabs)

    tab_idx = 0

    if spotify.is_configured():
        with tab_objects[0]:
            st.markdown("### Playlist Spotify")

            if spotify.is_user_authenticated():
                st.success("✅ Conectado ao Spotify")

                user_playlists = spotify.get_user_playlists()
                if user_playlists:
                    playlist_options = {
                        f"{p['name']} ({p['tracks_total']} tracks)":
                            p for p in user_playlists
                    }
                    selected = st.selectbox(
                        "Selecionar playlist",
                        options=list(playlist_options.keys()),
                        key="user_playlist_select",
                    )

                    if st.button("Adicionar Playlist Selecionada", type="primary", key="add_user_playlist"):
                        if selected:
                            playlist_data = playlist_options[selected]
                            with st.spinner(f"A carregar {playlist_data['name']}..."):
                                tracks = spotify.get_playlist_tracks(
                                    playlist_data["url"],
                                    playlist_data["name"],
                                    use_user_auth=True,
                                )

                            name = playlist_data["name"]
                            if name in st.session_state.playlists:
                                counter = 2
                                base_name = name
                                while name in st.session_state.playlists:
                                    name = f"{base_name} ({counter})"
                                    counter += 1

                            st.session_state.playlists[name] = {
                                "type": "spotify",
                                "url": playlist_data["url"],
                                "tracks": tracks,
                            }
                            update_all_tracks()
                            st.success(f"✅ {name} adicionada ({len(tracks)} tracks)")
                            st.rerun()
                else:
                    st.info("Nenhuma playlist encontrada na sua conta Spotify.")
            else:
                st.info("Liga-te ao Spotify no sidebar para aceder às tuas playlists.")
                url = st.text_input(
                    "Ou cola o link de uma playlist pública",
                    placeholder="https://open.spotify.com/playlist/...",
                    key="spotify_url",
                )
                playlist_name = st.text_input(
                    "Nome (opcional)",
                    placeholder="Ex: Rock Classics",
                    key="spotify_name",
                )

                if url and st.button("Adicionar por URL", type="primary", key="add_spotify_url"):
                    try:
                        with st.spinner("A carregar playlist do Spotify..."):
                            tracks = spotify.get_playlist_tracks(url, playlist_name or "")
                            if not playlist_name:
                                info = spotify.get_playlist_info(url)
                                playlist_name = info["name"]

                        if playlist_name in st.session_state.playlists:
                            counter = 2
                            base_name = playlist_name
                            while playlist_name in st.session_state.playlists:
                                playlist_name = f"{base_name} ({counter})"
                                counter += 1

                        st.session_state.playlists[playlist_name] = {
                            "type": "spotify",
                            "url": url,
                            "tracks": tracks,
                        }
                        update_all_tracks()
                        st.success(f"✅ {playlist_name} adicionada ({len(tracks)} tracks)")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Erro: {e}")

        tab_idx = 1

    with tab_objects[tab_idx]:
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
        icon = "🎵" if data.get("type") == "spotify" else "📄"
        col1, col2, col3 = st.columns([4, 2, 1])
        with col1:
            st.markdown(f"**{icon} {name}**")
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
    handle_oauth_callback()
    render_sidebar()

    st.markdown("# 🎵 SongMeld")
    st.markdown("Junta playlists do Spotify e JSON, remove duplicatas e exporta o resultado.")

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
