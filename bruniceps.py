#!/usr/bin/env python3

import subprocess
import os
import shutil
import yaml
import uuid
from pathlib import Path

CONFIG_FILE = 'bruniceps.yaml'

ARIA2C = "aria2c -s16 -x16 -k1M --seed-time=0 --file-allocation=none"
FFMPEG = "ffmpeg -hide_banner"

ENCODING_PROFILES = {
    'av1': ['-map', '0', '-c:v', 'libsvtav1', '-crf', '32', '-c:a', 'aac', '-ac', '2', '-c:s', 'copy'],
    'original': None
}

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def file_exists_with_basename(directory: Path, base_name: str) -> bool:
    return any(f.stem == base_name for f in directory.iterdir() if f.is_file())


def download_source(source_url, base_download_dir, task_id):
    task_dir = Path(base_download_dir) / task_id
    ensure_dir(task_dir)
    print(f"Downloading: {source_url} to {task_dir}")

    subprocess.run(ARIA2C.split() + [
        '--dir=' + str(task_dir),
        #'--summary-interval=0',
        #'--show-console-readout=false',
        '--auto-file-renaming=false',
        '--allow-overwrite=true',
        source_url
    ], check=True)

    files = list(task_dir.iterdir())
    if not files:
        raise FileNotFoundError("No files downloaded")

    latest_file = max(files, key=lambda f: f.stat().st_mtime)
    return latest_file


def encode_video(input_path: str, output_path: str, profile: str, task_id: str):
    print(f"[{task_id}] Encoding: {input_path} -> {output_path} with profile {profile}")
    encoding_args = ENCODING_PROFILES.get(profile)
    if not encoding_args:
        shutil.copy(input_path, output_path)
    else:
        subprocess.run(FFMPEG.split() + ['-i', input_path] + encoding_args + [output_path], check=True)


def process_episode(ep, full_name, target_dir, downloaded_dir, encoded_dir):
    task_id = str(uuid.uuid4())
    suffix = ep['suffix']
    source = ep['source']
    encoding = ep.get('encoding', 'av1')
    format_ext = ep.get('format')  # could be None

    base_filename = f"{full_name} {suffix}"

    if file_exists_with_basename(target_dir, base_filename):
        print(f"[{task_id}] Skipping {base_filename}, already exists in {target_dir}.")
        return

    print(f"[{task_id}] Downloading episode to: {downloaded_dir}")
    input_file = download_source(source, downloaded_dir, task_id)

    output_ext = format_ext if format_ext else input_file.suffix.lstrip('.')
    output_encoded = encoded_dir / f"{input_file.stem}_encoded.{output_ext}"
    final_output_path = target_dir / f"{base_filename}.{output_ext}"

    encode_video(str(input_file), str(output_encoded), profile=encoding, task_id=task_id)

    ensure_dir(target_dir)
    shutil.move(str(output_encoded), str(final_output_path))
    print(f"[{task_id}] Moved to {final_output_path}")

    input_file.unlink()
    try:
        task_dir = input_file.parent
        task_dir.rmdir()
    except Exception:
        pass


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

    clean_tmp_dirs(encoded_dir)


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'sync':
        sync()
    else:
        print("Usage: bruniceps sync")


if __name__ == '__main__':
    main()

