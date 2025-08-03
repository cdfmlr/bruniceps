import subprocess
import os
import shutil
import yaml
from pathlib import Path

CONFIG_FILE = 'bruniceps.yaml'


def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def file_exists(path):
    return Path(path).exists()


def download_magnet(magnet_link, output_dir):
    print(f"Downloading: {magnet_link}")
    subprocess.run(['aria2c', '--dir=' + output_dir, magnet_link], check=True)


def encode_video(input_path: str, output_path: str, codec: str):
    print(f"Encoding: {input_path} -> {output_path} with codec {codec}")
    subprocess.run(['ffmpeg', '-i', input_path, '-c:v', codec, output_path], check=True)


def process_episode(ep, full_name, target_dir, downloaded_dir, encoded_dir):
    suffix = ep['suffix']
    source = ep['source']
    encoding = ep.get('encoding', 'av1')
    format_ext = ep.get('format', None)

    encoded_filename = f"{full_name} {suffix}"
    output_file_ext = format_ext if format_ext else 'mkv'
    final_output_path = target_dir / f"{encoded_filename}.{output_file_ext}"

    if file_exists(final_output_path):
        print(f"Skipping {final_output_path}, already exists.")
        return

    print(f"Downloading episode to: {downloaded_dir}")
    download_magnet(source, str(downloaded_dir))

    downloaded_files = sorted(downloaded_dir.glob('*'), key=os.path.getmtime, reverse=True)
    if not downloaded_files:
        print("Download failed or no file found.")
        return
    input_file = downloaded_files[0]

    output_ext = format_ext if format_ext else input_file.suffix[1:]
    output_encoded = encoded_dir / f"{input_file.stem}_encoded.{output_ext}"

    if encoding == 'original':
        shutil.copy(input_file, output_encoded)
    else:
        encode_video(str(input_file), str(output_encoded), codec='libaom-av1')

    ensure_dir(target_dir)
    shutil.move(str(output_encoded), str(final_output_path))
    print(f"Moved to {final_output_path}")

    input_file.unlink()


def process_media_entries(entries, media_root, downloaded_dir, encoded_dir):
    for key, show in entries.items():
        full_name = show['FullName']
        target_dir = media_root / full_name
        ensure_dir(target_dir)

        episodes = show.get('Episodes') or show.get('Episodeds', [])
        for ep in episodes:
            process_episode(ep, full_name, target_dir, downloaded_dir, encoded_dir)


def clean_tmp_dirs(*dirs):
    for d in dirs:
        print(f"Cleaning {d}")
        shutil.rmtree(d, ignore_errors=True)


def sync():
    config = load_config()
    tmp_dir = Path(config['tmpDir'])
    tv_dir = Path(config['tvDir'])
    movie_dir = Path(config['movieDir'])
    downloaded_dir = tmp_dir / 'downloaded'
    encoded_dir = tmp_dir / 'encoded'

    ensure_dir(downloaded_dir)
    ensure_dir(encoded_dir)

    process_media_entries(config.get('tv', {}), tv_dir, downloaded_dir, encoded_dir)
    process_media_entries(config.get('movie', {}), movie_dir, downloaded_dir, encoded_dir)

    clean_tmp_dirs(downloaded_dir, encoded_dir)


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'sync':
        sync()
    else:
        print("Usage: bruniceps sync")


if __name__ == '__main__':
    main()

