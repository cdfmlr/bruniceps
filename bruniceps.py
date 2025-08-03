import subprocess
import toml
import os
import shutil
from pathlib import Path

CONFIG_PATH = 'config.toml'
DOWNLOAD_DIR = 'downloads'
ENCODED_DIR = 'encoded'


def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return toml.load(f)


def download_torrent(torrent_file: str):
    print(f"Downloading: {torrent_file}")
    subprocess.run(['aria2c', '--dir=' + DOWNLOAD_DIR, torrent_file], check=True)


def encode_video(input_path: str, output_path: str, codec: str = 'libx264'):
    print(f"Encoding: {input_path} -> {output_path} with codec {codec}")
    subprocess.run(['ffmpeg', '-i', input_path, '-c:v', codec, output_path], check=True)


def move_file(source: str, destination: str):
    print(f"Moving: {source} -> {destination}")
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.move(source, destination)


def process_videos(config):
    for entry in config['media']:
        source_pattern = os.path.join(DOWNLOAD_DIR, entry['source'])
        output_encoded = os.path.join(ENCODED_DIR, entry['encoded_name'])
        final_destination = entry['destination']

        encode_video(source_pattern, output_encoded, entry.get('codec', 'libx264'))
        move_file(output_encoded, final_destination)


def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(ENCODED_DIR, exist_ok=True)
    config = load_config()

    # Simulate download - replace this with actual torrent file path if needed
    if 'torrents' in config:
        for torrent in config['torrents']:
            download_torrent(torrent)

    process_videos(config)


if __name__ == '__main__':
    main()

