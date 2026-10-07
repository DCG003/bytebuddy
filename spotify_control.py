import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os

from env_loader import cargar_env

cargar_env()

# Configuración de autenticación (debes registrar tu app en Spotify)
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:8080")
SCOPE = 'user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-read-private user-top-read'

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET,
    redirect_uri=SPOTIPY_REDIRECT_URI,
    scope=SCOPE
))

def get_current_track():
    """Devuelve información de la canción actual y su icono."""
    current = sp.current_playback()
    if current and current.get('item'):
        track = current['item']
        name = track['name']
        artists = ', '.join([a['name'] for a in track['artists']])
        album_img = track['album']['images'][0]['url'] if track['album']['images'] else None
        return {
            'name': name,
            'artists': artists,
            'album_img': album_img,
            'is_playing': current['is_playing']
        }
    return None

def next_track():
    """Pasa a la siguiente canción."""
    sp.next_track()
    return get_current_track()

def previous_track():
    """Vuelve a la canción anterior."""
    sp.previous_track()
    return get_current_track()

def play_pause():
    """Alterna entre reproducir y pausar."""
    current = sp.current_playback()
    if current and current['is_playing']:
        sp.pause_playback()
    else:
        sp.start_playback()
    return get_current_track()

def get_user_playlists():
    """Devuelve las playlists del usuario."""
    playlists = sp.current_user_playlists()
    playlist_data = []
    if playlists:
        for playlist in playlists['items']:
            playlist_data.append({
                'id': playlist['id'],
                'name': playlist['name'],
                'image': playlist['images'][0]['url'] if playlist['images'] else None
            })
    return playlist_data

def play_track(track_uri):
    """Reproduce una canción específica."""
    sp.start_playback(uris=[track_uri])
    return get_current_track()

def get_recommendations(song_name):
    """
    Busca una canción y obtiene recomendaciones usando una estrategia de semillas robusta.
    """
    if not song_name:
        return {"error": "No se proporcionó un nombre de canción."}

    # 1. Buscar la canción
    results = sp.search(q=f"track:{song_name}", type='track', limit=1)
    if not results['tracks']['items']:
        return {"error": f"No se encontró la canción '{song_name}'."}
    track = results['tracks']['items'][0]
    
    # 2. Recopilar todas las semillas posibles
    seed_tracks = [track['id']]
    all_artist_ids = [artist['id'] for artist in track['artists']]
    seed_genres = []
    if all_artist_ids:
        try:
            main_artist_info = sp.artist(all_artist_ids[0])
            seed_genres = main_artist_info.get('genres', [])
        except Exception:
            pass # Si falla, continuamos sin géneros

    # 3. Probar combinaciones de semillas de más a menos específica
    recommendations = None
    seed_combos = [
        {'seed_tracks': seed_tracks, 'seed_artists': all_artist_ids[:2], 'seed_genres': seed_genres[:2]},
        {'seed_tracks': seed_tracks, 'seed_artists': all_artist_ids[:4]},
        {'seed_tracks': seed_tracks, 'seed_genres': seed_genres[:4]},
        {'seed_tracks': seed_tracks},
    ]

    for seeds in seed_combos:
        try:
            # Limpiar semillas vacías y asegurar el límite de 5
            valid_seeds = {k: v for k, v in seeds.items() if v}
            total_seed_count = sum(len(v) for v in valid_seeds.values())
            
            if total_seed_count > 5:
                if 'seed_artists' in valid_seeds:
                    # Ajustar artistas para no superar el límite
                    max_artists = 5 - len(valid_seeds.get('seed_tracks', [])) - len(valid_seeds.get('seed_genres', []))
                    valid_seeds['seed_artists'] = valid_seeds['seed_artists'][:max_artists]
            
            if not any(valid_seeds.values()): continue
            
            result = sp.recommendations(**valid_seeds, limit=10)
            if result and result['tracks']:
                recommendations = result
                break # Salir en cuanto encontremos un resultado válido
        except Exception:
            continue # Si hay un error con una combinación, probar la siguiente

    if not recommendations or not recommendations['tracks']:
        return {"error": f"No se pudieron obtener recomendaciones para '{song_name}'."}

    # 4. Formatear y añadir a la cola
    recommended_songs = [f"{t['name']} - {', '.join([a['name'] for a in t['artists']])}" for t in recommendations['tracks']]
    queue_status = add_songs_to_queue(recommended_songs)
    
    return {
        "recommendations": recommended_songs,
        "queue_status": queue_status.get("status")
    }


def add_songs_to_queue(song_list):
    """
    Busca una lista de canciones y las añade a la cola de reproducción.
    """
    if not isinstance(song_list, list) or not song_list:
        return {"error": "Se necesita una lista de canciones."}

    added_count = 0
    not_found = []

    for song_query in song_list:
        try:
            results = sp.search(q=song_query, type='track', limit=1)
            if results['tracks']['items']:
                track_uri = results['tracks']['items'][0]['uri']
                sp.add_to_queue(track_uri)
                added_count += 1
            else:
                not_found.append(song_query)
        except Exception as e:
            not_found.append(f"{song_query} (Error: {e})")
    
    message = f"Se han añadido {added_count} de {len(song_list)} canciones a la cola."
    if not_found:
        message += " No se encontraron las siguientes: " + ", ".join(not_found)
        
    return {"status": message}


