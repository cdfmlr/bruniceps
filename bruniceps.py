#!/usr/bin/env python3

import subprocess
import os
import shutil
import yaml  # python3 -m pip install pyyaml
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict

CONFIG_FILE = 'bruniceps.yaml'

@dataclass
class Episode:
    key: str
    source: str
    encoding: str = 'av1'
    format: Optional[str] = None

@dataclass
class MediaEntry:
    key: str
    title: str
    episodes: List[Episode]
    media_type: str

@dataclass
class Catalog:
    base_dir: str

@dataclass
class MetaConfig:
    tmp_dir: str
    aria2c_cmd: str
    ffmpeg_cmd: str
    encoding_profiles: Dict[str, Optional[str]]
    catalogs: Dict[str, Catalog]

ARIA2C = None
FFMPEG = None
ENCODING_PROFILES = {}

def parse_config(config: Dict) -> (MetaConfig, List[MediaEntry]):
    global ARIA2C, FFMPEG, ENCODING_PROFILES

    meta_raw = config.get('_meta_', {})
    catalogs = {k: Catalog(**v) for k, v in meta_raw.get('catalogs', {}).items()}

    encoding_profiles = {}
    for item in meta_raw.get('encoding_profiles', []):
        encoding_profiles.update(item)

    meta = MetaConfig(
        tmp_dir=meta_raw['tmp_dir'],
        aria2c_cmd=meta_raw['aria2c_cmd'],
        ffmpeg_cmd=meta_raw['ffmpeg_cmd'],
        encoding_profiles=encoding_profiles,
        catalogs=catalogs
    )

    ARIA2C = meta.aria2c_cmd
    FFMPEG = meta.ffmpeg_cmd
    ENCODING_PROFILES = {
        k: None if v is None else v.split() for k, v in meta.encoding_profiles.items()
    }

    entries = []
    for media_type, media_items in config.items():
        if media_type.startswith('_') or media_type not in meta.catalogs:
            continue
        for key, val in media_items.items():
            episodes_raw = val.get('episodes') or []
            episodes = [Episode(**ep) for ep in episodes_raw]
            entries.append(MediaEntry(key=key, title=val['title'], episodes=episodes, media_type=media_type))

    return meta, entries

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
        '--auto-file-renaming=false',
        '--allow-overwrite=true',
        #'--summary-interval=0',
        #'--show-console-readout=false',
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

def process_episode(entry: MediaEntry, ep: Episode, target_dir: Path, downloaded_dir: Path, encoded_dir: Path):
    task_id = f"{entry.key}_{ep.key}"
    base_filename = f"{entry.title} {ep.key}"

    if file_exists_with_basename(target_dir, base_filename):
        print(f"[{task_id}] Skipping {base_filename}, already exists in {target_dir}.")
        return

    print(f"[{task_id}] Downloading episode {base_filename} to: {downloaded_dir}")
    input_file = download_source(ep.source, downloaded_dir, task_id)

    output_ext = ep.format if ep.format else input_file.suffix.lstrip('.')
    output_encoded = encoded_dir / f"{input_file.stem}_encoded.{output_ext}"
    final_output_path = target_dir / f"{base_filename}.{output_ext}"

    encode_video(str(input_file), str(output_encoded), profile=ep.encoding, task_id=task_id)

    ensure_dir(target_dir)
    shutil.move(str(output_encoded), str(final_output_path))
    print(f"[{task_id}] Moved to {final_output_path}")

    input_file.unlink()
    try:
        input_file.parent.rmdir()
    except Exception:
        pass

def process_all_entries(entries: List[MediaEntry], catalogs: Dict[str, Catalog], downloaded_dir: Path, encoded_dir: Path):
    for entry in entries:
        base_dir = Path(catalogs[entry.media_type].base_dir)
        target_dir = base_dir / entry.title
        ensure_dir(target_dir)

        for ep in entry.episodes:
            process_episode(entry, ep, target_dir, downloaded_dir, encoded_dir)

def clean_tmp_dirs(*dirs):
    for d in dirs:
        print(f"Cleaning {d}")
        shutil.rmtree(d, ignore_errors=True)

def sync():
    global config
    config = load_config()
    meta, entries = parse_config(config)

    tmp_dir = Path(meta.tmp_dir)
    downloaded_dir = tmp_dir / 'downloaded'
    encoded_dir = tmp_dir / 'encoded'

    ensure_dir(downloaded_dir)
    ensure_dir(encoded_dir)

    process_all_entries(entries, meta.catalogs, downloaded_dir, encoded_dir)

    clean_tmp_dirs(encoded_dir)

def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'sync':
        sync()
    else:
        print("Usage: bruniceps sync")

if __name__ == '__main__':
    main()

