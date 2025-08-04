#!/usr/bin/env python3

import subprocess
import os
import shutil
import yaml  # python3 -m pip install pyyaml
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict
import uuid
import sys
import os

DEFAULT_CONFIG_FILE = 'bruniceps.yaml'

@dataclass
class Episode:
    key: str
    source: str
    encoding: str = 'av1'
    format: Optional[str] = None

@dataclass
class Series:
    key: str
    title: str
    catalog: str
    episodes: List[Episode]

@dataclass
class Catalog:
    key: str
    base_dir: str

@dataclass
class MetaConfig:
    tmp_dir: str
    aria2c_cmd: str
    ffmpeg_cmd: str
    encoding_profiles: Dict[str, Optional[str]]
    catalogs: Dict[str, Catalog]

def parse_config(config: Dict) -> (MetaConfig, List[Series]):
    meta_raw = config.get('meta', {})
    catalogs_raw = meta_raw.get('catalogs', {})
    catalogs = {
        k: Catalog(key=k, base_dir=v['base_dir'])
        for k, v in catalogs_raw.items()
    }

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

    series_list = []
    for key, val in config.get('series', {}).items():
        episodes_raw = val.get('episodes') or []
        episodes = [Episode(**ep) for ep in episodes_raw]
        series_list.append(Series(key=key, title=val['title'], catalog=val['catalog'], episodes=episodes))

    return meta, series_list

def load_config(path=None):
    config_path = path or os.environ.get("BRUNICEPS_CONFIG", DEFAULT_CONFIG_FILE)
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def file_exists_with_basename(directory: Path, base_name: str) -> bool:
    return any(f.stem == base_name for f in directory.iterdir() if f.is_file())

def download_source(source_url, base_download_dir, task_id, aria2c_cmd):
    task_dir = Path(base_download_dir) / str(uuid.uuid4())
    ensure_dir(task_dir)
    print(f"Downloading: {source_url} to {task_dir}")

    subprocess.run(aria2c_cmd.split() + [
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

def encode_video(input_path: str, output_path: str, profile: str, task_id: str, ffmpeg_cmd: str, encoding_profiles: Dict[str, Optional[str]]):
    print(f"[{task_id}] Encoding: {input_path} -> {output_path} with profile {profile}")
    encoding_args = encoding_profiles.get(profile)
    if not encoding_args:
        shutil.copy(input_path, output_path)
    else:
        subprocess.run(ffmpeg_cmd.split() + ['-i', input_path] + encoding_args.split() + [output_path], check=True)

def process_episode(series: Series, ep: Episode, catalog: Catalog, downloaded_dir: Path, encoded_dir: Path, meta: MetaConfig):
    task_id = f"{series.key}_{ep.key}"
    base_filename = f"{series.title} {ep.key}"

    target_dir = Path(catalog.base_dir) / series.title
    ensure_dir(target_dir)

    if file_exists_with_basename(target_dir, base_filename):
        print(f"[{task_id}] Skipping {base_filename}, already exists in {target_dir}.")
        return

    input_file = download_source(ep.source, downloaded_dir, task_id, meta.aria2c_cmd)
    output_ext = ep.format if ep.format else input_file.suffix.lstrip('.')
    output_encoded = encoded_dir / f"{input_file.stem}_encoded.{output_ext}"
    final_output_path = target_dir / f"{base_filename}.{output_ext}"

    encode_video(str(input_file), str(output_encoded), ep.encoding, task_id, meta.ffmpeg_cmd, meta.encoding_profiles)

    shutil.move(str(output_encoded), str(final_output_path))
    print(f"[{task_id}] Moved to {final_output_path}")

    input_file.unlink()
    try:
        input_file.parent.rmdir()
    except Exception:
        pass

def process_all_series(series_list: List[Series], meta: MetaConfig, downloaded_dir: Path, encoded_dir: Path):
    for series in series_list:
        catalog = meta.catalogs[series.catalog]
        for ep in series.episodes:
            process_episode(series, ep, catalog, downloaded_dir, encoded_dir, meta)

def clean_tmp_dirs(*dirs):
    for d in dirs:
        print(f"Cleaning {d}")
        shutil.rmtree(d, ignore_errors=True)

def sync(config_path=None):
    config = load_config(config_path)
    meta, series_list = parse_config(config)

    tmp_dir = Path(meta.tmp_dir)
    downloaded_dir = tmp_dir / 'downloaded'
    encoded_dir = tmp_dir / 'encoded'

    ensure_dir(downloaded_dir)
    ensure_dir(encoded_dir)

    process_all_series(series_list, meta, downloaded_dir, encoded_dir)

    clean_tmp_dirs(encoded_dir)

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("sync", nargs='?', help="Sync the series")
    parser.add_argument("-c", "--config", help="Path to config file")
    args = parser.parse_args()

    if args.sync == "sync":
        sync(args.config)
    else:
        print("Usage: bruniceps sync [-c CONFIG_FILE]")

if __name__ == '__main__':
    main()

