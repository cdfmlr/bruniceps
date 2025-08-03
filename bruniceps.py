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


def sync():
    config = load_config()
    tmp_dir = Path(config['tmpDir'])
    tv_dir = Path(config['tvDir'])
    movie_dir = Path(config['movieDir'])
    downloaded_dir = tmp_dir / 'downloaded'
    encoded_dir = tmp_dir / 'encoded'

    ensure_dir(downloaded_dir)
    ensure_dir(encoded_dir)

    def handle_entries(entries, media_root):
        for key, show in entries.items():
            full_name = show['FullName']
            target_dir = media_root / full_name
            ensure_dir(target_dir)

            episodes = show.get('Episodes') or show.get('Episodeds', [])  # typo fallback
            for ep in episodes:
                suffix = ep['suffix']
                source = ep['source']
                encoding = ep.get('encoding', 'av1')
                format_ext = ep.get('format', None)

                # Filename before encoding (assumes aria2 saves with default name)
                encoded_filename = f"{full_name} {suffix}"
                output_file_ext = format_ext if format_ext else 'mkv'  # fallback
                final_output_path = target_dir / f"{encoded_filename}.{output_file_ext}"

                if file_exists(final_output_path):
                    print(f"Skipping {final_output_path}, already exists.")
                    continue

                # Download to downloaded_dir
                print(f"Downloading episode to: {downloaded_dir}")
                download_magnet(source, str(downloaded_dir))

                # Find the downloaded file
                downloaded_files = sorted(downloaded_dir.glob('*'), key=os.path.getmtime, reverse=True)
                if not downloaded_files:
                    print("Download failed or no file found.")
                    continue
                input_file = downloaded_files[0]  # assume most recent is the one

                # Set encoded output path
                output_ext = format_ext if format_ext else input_file.suffix[1:]
                output_encoded = encoded_dir / f"{input_file.stem}_encoded.{output_ext}"

                # Encode or copy
                if encoding == 'original':
                    shutil.copy(input_file, output_encoded)
                else:
                    encode_video(str(input_file), str(output_encoded), codec='libaom-av1')

                # Move to final destination
                ensure_dir(target_dir)
                shutil.move(str(output_encoded), str(final_output_path))
                print(f"Moved to {final_output_path}")

                # Clean downloaded file
                input_file.unlink()

    handle_entries(config.get('tv', {}), tv_dir)
    handle_entries(config.get('movie', {}), movie_dir)

    print("Cleaning temporary directories")
    shutil.rmtree(downloaded_dir, ignore_errors=True)
    shutil.rmtree(encoded_dir, ignore_errors=True)


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'sync':
        sync()
    else:
        print("Usage: bruniceps sync")


if __name__ == '__main__':
    main()

